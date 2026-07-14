# ExileAPI Plugin Dev MCP

An MCP server that gives coding agents a bounded development workflow for ExileAPI plugins. The repository also contains a disabled-by-default ExileAPI companion plugin reserved for a future read-only telemetry bridge.

## Scope

- Detect local ExileAPI compiler references.
- Scaffold source-only C# plugin projects below `generated-plugins/`.
- Build generated projects with the local ExileAPI package directory.

It deliberately does **not** expose DevTree's dynamic C# evaluator, read or write process memory, or send game input. The current companion plugin has no IPC surface; a future runtime bridge must be separately reviewed and read-only.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/exileapi-plugin-dev
```

The repository is linked into ExileAPI source plugins at:

`~/ExileApi-Compiled/Plugins/Source/ExileApiPluginDev -> ~/ExileApiPluginDev`

`dotnet` and a Windows-compatible .NET 10 SDK are required to build generated ExileAPI projects.
