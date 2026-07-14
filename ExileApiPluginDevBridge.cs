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
    [Menu(null, "Overview, Player, PlayerInventory, UIHover, IngameUI, or Custom")]
    public TextNode CaptureProfile { get; set; } = new TextNode("Overview");
    [Menu(null, "Only used by Custom; comma-separated DevTree shortcuts")]
    public TextNode CustomSnapshotShortcuts { get; set; } = new TextNode("PlayerInventory.Items");
    [Menu(null, "An MCP request here is applied only after the Capture snapshot button is pressed")]
    public TextNode CaptureRequestFilePath { get; set; } = new TextNode(@"Z:\home\auron\ExileApiPluginDev\capture-request.json");
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
    private sealed class CapturePlan
    {
        public CapturePlan(string profile, IEnumerable<string> shortcuts, int maxDepth, int maxNodes, int maxCollectionEntries)
        {
            Profile = profile;
            Shortcuts = shortcuts.ToArray();
            MaxDepth = maxDepth;
            MaxNodes = maxNodes;
            MaxCollectionEntries = maxCollectionEntries;
        }

        public string Profile { get; }
        public string[] Shortcuts { get; }
        public int MaxDepth { get; }
        public int MaxNodes { get; }
        public int MaxCollectionEntries { get; }
    }

    private sealed class CaptureRequest
    {
        public string Profile { get; set; }
        public string[] Sections { get; set; }
    }

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
            var requestPath = Settings.CaptureRequestFilePath.Value;
            var request = ReadCaptureRequest(requestPath);
            var plan = CreateCapturePlan(request?.Profile ?? Settings.CaptureProfile.Value, request?.Sections ?? ParseShortcuts(Settings.CustomSnapshotShortcuts.Value), roots.Keys);
            var capturedRoots = new Dictionary<string, object>();
            var remainingBudgets = new Dictionary<string, int>();
            foreach (var shortcut in plan.Shortcuts)
            {
                var budget = plan.MaxNodes;
                capturedRoots[shortcut] = SnapshotValue(roots[shortcut], 0, ref budget, plan.MaxDepth, plan.MaxCollectionEntries);
                remainingBudgets[shortcut] = Math.Max(0, budget);
            }
            var snapshot = new
            {
                schemaVersion = 1,
                capturedAtUtc = DateTimeOffset.UtcNow,
                profile = plan.Profile,
                limits = new
                {
                    maxDepth = plan.MaxDepth,
                    maxNodes = plan.MaxNodes,
                    maxCollectionEntries = plan.MaxCollectionEntries,
                    maxStringLength = Settings.SnapshotMaxStringLength.Value,
                    includeAddresses = false,
                },
                remainingNodeBudgetByShortcut = remainingBudgets,
                shortcuts = capturedRoots,
            };
            WriteJsonAtomically(Settings.SnapshotFilePath.Value, snapshot);
            if (request != null && !string.IsNullOrWhiteSpace(requestPath)) File.Delete(requestPath);
            WriteStatus($"snapshot_captured:{plan.Profile}");
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

    private CapturePlan CreateCapturePlan(string profile, string[] customShortcuts, ICollection<string> availableShortcuts)
    {
        var normalized = (profile ?? "Overview").Trim();
        var selected = normalized.ToLowerInvariant() switch
        {
            "overview" => availableShortcuts.ToArray(),
            "player" => new[] { "Player" },
            "playerinventory" => new[] { "PlayerInventory", "PlayerInventory.Items" },
            "uihover" => new[] { "UIHover" },
            "ingameui" => new[] { "IngameUI" },
            "custom" => customShortcuts,
            _ => throw new InvalidOperationException($"Unknown capture profile: {normalized}"),
        };
        var invalid = selected.Where(shortcut => !availableShortcuts.Contains(shortcut)).ToArray();
        if (invalid.Length > 0) throw new InvalidOperationException($"Unknown DevTree shortcut(s): {string.Join(", ", invalid)}");
        if (selected.Length == 0) throw new InvalidOperationException("The capture profile selected no shortcuts.");
        return normalized.ToLowerInvariant() switch
        {
            "player" => new CapturePlan("Player", selected, 8, 5000, 500),
            "playerinventory" => new CapturePlan("PlayerInventory", selected, 10, 5000, 1000),
            "uihover" => new CapturePlan("UIHover", selected, 10, 3000, 1000),
            "ingameui" => new CapturePlan("IngameUI", selected, 8, 5000, 500),
            "custom" => new CapturePlan("Custom", selected, Settings.SnapshotMaxDepth.Value, Settings.SnapshotMaxNodes.Value, Settings.SnapshotMaxCollectionEntries.Value),
            _ => new CapturePlan("Overview", selected, Settings.SnapshotMaxDepth.Value, Settings.SnapshotMaxNodes.Value, Settings.SnapshotMaxCollectionEntries.Value),
        };
    }

    private static string[] ParseShortcuts(string value) => (value ?? string.Empty)
        .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.Ordinal)
        .ToArray();

    private static CaptureRequest ReadCaptureRequest(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return null;
        return JsonSerializer.Deserialize<CaptureRequest>(File.ReadAllText(path));
    }

    private object SnapshotValue(object value, int depth, ref int budget, int maxDepth, int maxCollectionEntries)
    {
        if (value == null) return null;
        if (budget-- <= 0) return new Dictionary<string, object> { ["_truncated"] = "node_limit" };
        var type = value.GetType();
        if (value is string text) return text.Length <= Settings.SnapshotMaxStringLength.Value ? text : text[..Settings.SnapshotMaxStringLength.Value] + "…";
        // Native addresses are neither portable nor useful for the MCP.  More
        // importantly, System.Text.Json intentionally refuses to serialize them.
        if (value is IntPtr or UIntPtr) return "<native_pointer>";
        if (value is Type runtimeType) return runtimeType.FullName ?? runtimeType.Name;
        if (value is Delegate callback) return $"<delegate:{callback.Method.Name}>";
        if (type.IsPrimitive || value is decimal or DateTime or DateTimeOffset or Guid or TimeSpan || type.IsEnum) return value;
        if (depth >= maxDepth) return new Dictionary<string, object> { ["_type"] = type.FullName, ["_truncated"] = "depth_limit" };

        if (value is IEnumerable sequence)
        {
            var items = new List<object>();
            var count = 0;
            foreach (var item in sequence)
            {
                if (count++ >= maxCollectionEntries)
                {
                    items.Add(new Dictionary<string, object> { ["_truncated"] = "collection_limit" });
                    break;
                }
                items.Add(SnapshotValue(item, depth + 1, ref budget, maxDepth, maxCollectionEntries));
            }
            return items;
        }

        var result = new Dictionary<string, object> { ["_type"] = type.FullName };
        foreach (var property in type.GetProperties(BindingFlags.Instance | BindingFlags.Public).Take(80))
        {
            if (!property.CanRead || property.GetIndexParameters().Length != 0 || ExcludedProperties.Contains(property.Name)) continue;
            try
            {
                result[property.Name] = SnapshotValue(property.GetValue(value), depth + 1, ref budget, maxDepth, maxCollectionEntries);
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
