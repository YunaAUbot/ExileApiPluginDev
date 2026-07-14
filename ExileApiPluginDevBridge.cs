using ExileCore;
using ExileCore.PoEMemory;
using ExileCore.Shared.Interfaces;
using ExileCore.Shared.Nodes;
using System;
using System.IO;
using System.Text.Json;

namespace ExileApiPluginDevBridge;

/// <summary>
/// Read-only companion that confirms a successful ExileAPI Build/Reload to the MCP.
/// It intentionally has no process-control, input, memory-write, or code-evaluation capability.
/// </summary>
public sealed class BridgeSettings : ISettings
{
    public ToggleNode Enable { get; set; } = new(true);
    public TextNode StatusFilePath { get; set; } = new TextNode(@"Z:\home\auron\ExileApiPluginDev\runtime-status.json");
}

public sealed class BridgePlugin : BaseSettingsPlugin<BridgeSettings>
{
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
}
