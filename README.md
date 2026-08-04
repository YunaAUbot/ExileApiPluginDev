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

## Controller-side verification

The collection-index path resolver is covered by a game-independent .NET test project:

```bash
"${DOTNET_ROOT:-$HOME/.dotnet}/dotnet" test \
  tests/ExileApiPluginDevBridge.Core.Tests/ExileApiPluginDevBridge.Core.Tests.csproj
```

A full bridge build additionally needs the matching `ExileCore.dll` and `GameOffsets.dll` directory:

```bash
"${DOTNET_ROOT:-$HOME/.dotnet}/dotnet" build ExileApiPluginDevBridge.csproj \
  -p:EnableWindowsTargeting=true \
  -p:exapiPackage=/path/to/pinned/exileapi-runtime
```

The main bridge project explicitly excludes `tests/**/*.cs` so ExileAPI's source compiler does not compile xUnit sources or nested test build artifacts.

The repository is linked into ExileAPI source plugins at:

`~/ExileApi-Compiled/Plugins/Source/ExileApiPluginDev -> ~/ExileApiPlugins/ExileApiPluginDev`

ExileAPI owns compilation and reload. Use its in-game **Build/Reload** button after source changes; no Linux build worker is required.
`Errors.txt` may be retained after a successful build, so the MCP also reports its modification time.

The enabled bridge writes a small read-only `runtime-status.json` after successful initialisation and area changes. Its default path matches the existing `Z:` mount used by ExileAPI on this machine; it can be changed in the plugin settings.

For larger diagnostics, use **Capture snapshot** in the bridge's ExileAPI menu. It writes `game-snapshot.json` only when pressed. Defaults are: depth 6, 500 total nodes, 100 collection entries per node, 512 characters per string, and no memory addresses. `read_game_snapshot` reads the frozen result through MCP.

### Finding an unknown live-game struct

Do not add properties or profiles to the bridge merely because an agent does not yet know the required object path. Use the MCP scan loop instead:

1. `begin_game_struct_scan(goal, roots)` prepares one shallow **Discovery** capture for one to three plausible DevTree roots.
2. Let the bridge execute the request, then use `inspect_game_snapshot` and `read_game_snapshot_path` to examine only relevant paths.
3. `continue_game_struct_scan(goal)` follows at most three `depth_limit`/`node_limit` branches with another shallow capture.
4. Repeat until the exact property is evidenced. Only then use a deep `Targeted` capture.

This keeps snapshots small and makes a bridge change an evidence-based exception rather than the normal way to discover data.

## ExileAPI core snapshots

`list_core_snapshots`, `inspect_core_snapshot`, `find_core_snapshot_paths`, and `read_core_snapshot_member` work with ExileAPI's `snapshots/*.exapisnap` files. The indexer reads 512-byte TAR headers and seeks over member bodies; it never extracts or feeds a multi-gigabyte snapshot to the model. `find_core_snapshot_paths` supports required and excluded path terms; read a member only after narrowing it through the indexed path list.
