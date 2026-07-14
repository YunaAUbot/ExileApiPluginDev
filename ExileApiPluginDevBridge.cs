using ExileCore;
using ExileCore.PoEMemory;
using ExileCore.Shared.Attributes;
using ExileCore.Shared.Interfaces;
using ExileCore.Shared.Nodes;
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ExileApiPluginDevBridge;

/// <summary>
/// Read-only companion that confirms a successful ExileAPI Build/Reload to the MCP.
/// It intentionally has no process-control, input, memory-write, or code-evaluation capability.
/// </summary>
public sealed class BridgeSettings : ISettings
{
    public ToggleNode Enable { get; set; } = new(true);
    public TextNode StatusFilePath { get; set; } = new TextNode(@"Z:\home\auron\ExileApiPluginDev\runtime-status.json");
    public TextNode SnapshotFilePath { get; set; } = new TextNode(@"Z:\home\auron\ExileApiPluginDev\game-snapshot.json");
    public RangeNode<int> SnapshotMaxDepth { get; set; } = new(6, 1, 10);
    public RangeNode<int> SnapshotMaxNodes { get; set; } = new(500, 50, 5000);
    public RangeNode<int> SnapshotMaxCollectionEntries { get; set; } = new(100, 1, 1000);
    public RangeNode<int> SnapshotMaxStringLength { get; set; } = new(512, 32, 4096);

    [System.Text.Json.Serialization.JsonIgnore]
    [Menu("Capture snapshot")]
    public ButtonNode CaptureSnapshotButton { get; set; }

    [System.Text.Json.Serialization.JsonIgnore]
    internal bool CaptureRequested { get; private set; }

    public BridgeSettings()
    {
        CaptureSnapshotButton = new ButtonNode { OnPressed = () => CaptureRequested = true };
    }

    internal bool ConsumeCaptureRequest()
    {
        if (!CaptureRequested) return false;
        CaptureRequested = false;
        return true;
    }
}

public sealed class BridgePlugin : BaseSettingsPlugin<BridgeSettings>
{
    private static readonly HashSet<string> ExcludedProperties = new(StringComparer.Ordinal)
    {
        "Address", "M", "TheGame", "CoreSettings", "Cache", "pCache", "pM", "pTheGame", "OwnerAddress",
    };

    public override bool Initialise()
    {
        Name = "ExileAPI Plugin Dev Bridge";
        WriteStatus("ready");
        return true;
    }

    public override void AreaChange(AreaInstance area)
    {
        WriteStatus("area_changed");
    }

    public override void Render()
    {
        if (Settings.ConsumeCaptureRequest()) CaptureSnapshot();
    }

    private void WriteStatus(string state)
    {
        try
        {
            var path = Settings.StatusFilePath.Value;
            if (string.IsNullOrWhiteSpace(path)) return;
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            var content = JsonSerializer.Serialize(new
            {
                schemaVersion = 1,
                plugin = Name,
                state,
                updatedAtUtc = DateTimeOffset.UtcNow,
            });
            File.WriteAllText(path, content);
        }
        catch
        {
            // A status file must never disrupt ExileAPI's render or reload lifecycle.
        }
    }

    private void CaptureSnapshot()
    {
        try
        {
            var inventory = GameController.IngameState.Data.ServerData.PlayerInventories.FirstOrDefault()?.Inventory;
            var roots = new Dictionary<string, object>
            {
                ["Cache"] = GameController.Cache,
                ["GameController"] = GameController,
                ["TheGame"] = GameController.Game,
                ["Player"] = GameController.Player,
                ["IngameState"] = GameController.IngameState,
                ["IngameUI"] = GameController.IngameState.IngameUi,
                ["IngameState.Data"] = GameController.IngameState.Data,
                ["IngameState.Data.ServerData"] = GameController.IngameState.Data.ServerData,
                ["PlayerInventory"] = inventory,
                ["PlayerInventory.Items"] = inventory?.Items,
                ["ItemsOnGroundLabels"] = GameController.IngameState.IngameUi.ItemsOnGroundLabels,
                ["UIHover"] = GameController.IngameState.UIHover,
            };
            var budget = Settings.SnapshotMaxNodes.Value;
            var capturedRoots = roots.ToDictionary(
                pair => pair.Key,
                pair => SnapshotValue(pair.Value, 0, ref budget));
            var snapshot = new
            {
                schemaVersion = 1,
                capturedAtUtc = DateTimeOffset.UtcNow,
                limits = new
                {
                    maxDepth = Settings.SnapshotMaxDepth.Value,
                    maxNodes = Settings.SnapshotMaxNodes.Value,
                    maxCollectionEntries = Settings.SnapshotMaxCollectionEntries.Value,
                    maxStringLength = Settings.SnapshotMaxStringLength.Value,
                    includeAddresses = false,
                },
                remainingNodeBudget = budget,
                shortcuts = capturedRoots,
            };
            WriteJsonAtomically(Settings.SnapshotFilePath.Value, snapshot);
            WriteStatus("snapshot_captured");
        }
        catch (Exception exception)
        {
            // Keep a bounded diagnostic in the status file.  A reflection export must
            // fail visibly, but it must never disrupt ExileAPI's render loop.
            var detail = exception.Message
                .Replace('\r', ' ')
                .Replace('\n', ' ');
            if (detail.Length > 300) detail = detail[..300];
            WriteStatus($"snapshot_failed:{exception.GetType().Name}:{detail}");
        }
    }

    private object SnapshotValue(object value, int depth, ref int budget)
    {
        if (value == null) return null;
        if (budget-- <= 0) return new Dictionary<string, object> { ["_truncated"] = "node_limit" };
        var type = value.GetType();
        if (value is string text) return text.Length <= Settings.SnapshotMaxStringLength.Value ? text : text[..Settings.SnapshotMaxStringLength.Value] + "…";
        if (type.IsPrimitive || value is decimal or DateTime or DateTimeOffset or Guid or TimeSpan || type.IsEnum) return value;
        if (depth >= Settings.SnapshotMaxDepth.Value) return new Dictionary<string, object> { ["_type"] = type.FullName, ["_truncated"] = "depth_limit" };

        if (value is IEnumerable sequence)
        {
            var items = new List<object>();
            var count = 0;
            foreach (var item in sequence)
            {
                if (count++ >= Settings.SnapshotMaxCollectionEntries.Value)
                {
                    items.Add(new Dictionary<string, object> { ["_truncated"] = "collection_limit" });
                    break;
                }
                items.Add(SnapshotValue(item, depth + 1, ref budget));
            }
            return items;
        }

        var result = new Dictionary<string, object> { ["_type"] = type.FullName };
        foreach (var property in type.GetProperties(BindingFlags.Instance | BindingFlags.Public).Take(80))
        {
            if (!property.CanRead || property.GetIndexParameters().Length != 0 || ExcludedProperties.Contains(property.Name)) continue;
            try
            {
                result[property.Name] = SnapshotValue(property.GetValue(value), depth + 1, ref budget);
            }
            catch (Exception exception)
            {
                result[property.Name] = new Dictionary<string, object> { ["_error"] = exception.GetType().Name };
            }
        }
        return result;
    }

    private static void WriteJsonAtomically(string path, object content)
    {
        if (string.IsNullOrWhiteSpace(path)) return;
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
        var temporaryPath = path + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(content, new JsonSerializerOptions
        {
            WriteIndented = true,
            NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
        }));
        File.Move(temporaryPath, path, true);
    }
}
