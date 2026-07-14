using ExileCore;
using ExileCore.PoEMemory;
using ExileCore.Shared.Interfaces;
using ExileCore.Shared.Nodes;

namespace ExileApiPluginDevBridge;

/// <summary>
/// Reserved in-process companion for a future read-only MCP telemetry bridge.
/// It intentionally has no process-control, input, memory-write, or code-evaluation capability.
/// </summary>
public sealed class BridgeSettings : ISettings
{
    public ToggleNode Enable { get; set; } = new(false);
}

public sealed class BridgePlugin : BaseSettingsPlugin<BridgeSettings>
{
    public override bool Initialise()
    {
        Name = "ExileAPI Plugin Dev Bridge";
        return true;
    }

    public override void AreaChange(AreaInstance area)
    {
    }

    public override void Render()
    {
    }
}
