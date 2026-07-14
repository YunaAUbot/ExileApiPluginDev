# ExileAPI Plugin Dev MCP

An MCP server that gives coding agents a bounded development workflow for ExileAPI plugins. The repository also contains a disabled-by-default ExileAPI companion plugin reserved for a future read-only telemetry bridge.

## Scope

- Detect local ExileAPI compiler references.
- Create an independent Git repository under `~/ExileApiPlugins/<PluginName>` and link it into `Plugins/Source/<PluginName>`.
- Prepare the linked source tree for ExileAPI's in-game **Build/Reload** action.
- Read the resulting bounded `Errors.txt` output.

It deliberately does **not** expose DevTree's dynamic C# evaluator, read or write process memory, or send game input. The current companion plugin has no IPC surface; a future runtime bridge must be separately reviewed and read-only.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/exileapi-plugin-dev
```

The repository is linked into ExileAPI source plugins at:

`~/ExileApi-Compiled/Plugins/Source/ExileApiPluginDev -> ~/ExileApiPluginDev`

ExileAPI owns compilation and reload. Use its in-game **Build/Reload** button after source changes; no Linux build worker is required.
`Errors.txt` may be retained after a successful build, so the MCP also reports its modification time.

The enabled bridge writes a small read-only `runtime-status.json` after successful initialisation and area changes. Its default path matches the existing `Z:` mount used by ExileAPI on this machine; it can be changed in the plugin settings.
