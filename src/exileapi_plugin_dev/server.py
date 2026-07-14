"""A deliberately constrained MCP server for ExileAPI plugin development.

The MCP server helps an agent create source projects, inspect the installed API,
and prepare ExileAPI's own Build/Reload workflow. It does not attach to Path of Exile, expose DevTree's runtime
C# evaluator, or modify compiled-plugin directories.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from exileapi_plugin_dev.core import create_plugin_workspace, read_tail

# server.py -> exileapi_plugin_dev -> src -> repository root
SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXILEAPI_ROOT = Path.home() / "ExileApi-Compiled"
WORKSPACE_ROOT = Path.home() / "ExileApiPlugins"

mcp = FastMCP(
    "ExileAPI Plugin Development",
    instructions=(
        "Use this server to inspect an ExileAPI installation, scaffold source-only "
        "plugins, and prepare the in-game Build/Reload workflow. Do not treat it as a game automation API."
    ),
)


def _exileapi_root(value: str | None) -> Path:
    root = Path(value).expanduser().resolve() if value else DEFAULT_EXILEAPI_ROOT
    required = ("ExileCore.dll", "GameOffsets.dll")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Not an ExileAPI package directory: {root} (missing {', '.join(missing)})")
    return root


@mcp.tool()
def discover_environment(exileapi_root: str | None = None) -> str:
    """Report local ExileAPI references and the source-plugin link used by ExileAPI Build/Reload."""
    root = _exileapi_root(exileapi_root)
    references = ["ExileCore.dll", "GameOffsets.dll", "ItemFilterLibrary.dll"]
    return json.dumps(
        {
            "exileapi_root": str(root),
            "references": {name: (root / name).is_file() for name in references},
            "source_link": str(root / "Plugins" / "Source" / SERVER_ROOT.name),
            "workspace_root": str(WORKSPACE_ROOT),
            "build_workflow": "Use ExileAPI's in-game Build/Reload button; this MCP does not invoke dotnet.",
            "safety": "No game-process inspection, input, memory writes, or arbitrary C# evaluation is exposed.",
        },
        indent=2,
    )


@mcp.tool()
def scaffold_plugin(plugin_name: str, description: str) -> str:
    """Create a local Git repository and ExileAPI source symlink for a new source-only plugin."""
    root = _exileapi_root(None)
    return json.dumps(create_plugin_workspace(WORKSPACE_ROOT, root / "Plugins" / "Source", plugin_name, description), indent=2)


@mcp.tool()
def prepare_reload() -> str:
    """Check that the linked ExileAPI source plugin is ready for an in-game Build/Reload."""
    project = SERVER_ROOT / "ExileApiPluginDevBridge.csproj"
    result = subprocess.run(["git", "status", "--short"], cwd=SERVER_ROOT, text=True, capture_output=True, check=False)
    return json.dumps(
        {
            "bridge_project": str(project),
            "bridge_project_exists": project.is_file(),
            "errors_file": str(SERVER_ROOT / "Errors.txt"),
            "git_status": result.stdout,
            "next_step": "Use ExileAPI's in-game Build/Reload button.",
        },
        indent=2,
    )


@mcp.tool()
def read_last_build_errors(max_lines: int = 200) -> str:
    """Read the newest bounded portion of ExileAPI's Errors.txt after an in-game build."""
    error_log = SERVER_ROOT / "Errors.txt"
    modified_at = (
        datetime.fromtimestamp(error_log.stat().st_mtime, timezone.utc).isoformat() if error_log.is_file() else None
    )
    return json.dumps(
        {
            "path": str(error_log),
            "exists": error_log.is_file(),
            "modified_at": modified_at,
            "content": read_tail(error_log, max_lines),
            "note": "Errors.txt can remain unchanged after a successful ExileAPI build; compare modified_at with the last Build/Reload time.",
        },
        indent=2,
    )


@mcp.tool()
def read_runtime_status() -> str:
    """Read the read-only status file written by the enabled ExileAPI bridge after Build/Reload."""
    status_file = SERVER_ROOT / "runtime-status.json"
    modified_at = (
        datetime.fromtimestamp(status_file.stat().st_mtime, timezone.utc).isoformat() if status_file.is_file() else None
    )
    return json.dumps(
        {
            "path": str(status_file),
            "exists": status_file.is_file(),
            "modified_at": modified_at,
            "content": read_tail(status_file, 200),
            "expected": "Run ExileAPI Build/Reload with ExileAPI Plugin Dev Bridge enabled.",
        },
        indent=2,
    )


@mcp.tool()
def read_game_snapshot(section: str | None = None, max_characters: int = 60000) -> str:
    """Read a manually captured, read-only ExileAPI game snapshot or one shortcut section."""
    if not 1_000 <= max_characters <= 500_000:
        raise ValueError("max_characters must be between 1000 and 500000.")
    snapshot_file = SERVER_ROOT / "game-snapshot.json"
    if not snapshot_file.is_file():
        return json.dumps({"path": str(snapshot_file), "exists": False, "expected": "Press Capture snapshot in the bridge plugin menu."}, indent=2)
    try:
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return json.dumps({"path": str(snapshot_file), "exists": True, "error": f"Invalid JSON: {error.msg}"}, indent=2)
    if section:
        shortcuts = snapshot.get("shortcuts", {})
        if section not in shortcuts:
            return json.dumps({"path": str(snapshot_file), "exists": True, "available_sections": sorted(shortcuts), "error": "Unknown section."}, indent=2)
        snapshot = {"schemaVersion": snapshot.get("schemaVersion"), "capturedAtUtc": snapshot.get("capturedAtUtc"), "section": section, "data": shortcuts[section]}
    content = json.dumps(snapshot, indent=2, ensure_ascii=False)
    return json.dumps(
        {
            "path": str(snapshot_file),
            "modified_at": datetime.fromtimestamp(snapshot_file.stat().st_mtime, timezone.utc).isoformat(),
            "content": content[:max_characters],
            "truncated": len(content) > max_characters,
        },
        indent=2,
    )
@mcp.tool()
def find_plugin_examples(query: str, max_results: int = 20) -> str:
    """Find relevant local ExileAPI C# examples and return the exApiTools plugin catalogue link."""
    if not query.strip():
        raise ValueError("query must not be empty.")
    if not 1 <= max_results <= 100:
        raise ValueError("max_results must be between 1 and 100.")
    source_root = _exileapi_root(None) / "Plugins" / "Source"
    matches: list[dict[str, object]] = []
    needle = query.casefold()
    for path in source_root.rglob("*"):
        if len(matches) >= max_results or not path.is_file() or path.suffix.lower() not in {".cs", ".csproj", ".md"}:
            continue
        if any(part in {".git", "bin", "obj"} for part in path.parts):
            continue
        try:
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if needle in line.casefold():
                    matches.append({"path": str(path), "line": line_number, "snippet": line.strip()[:300]})
                    break
        except OSError:
            continue
    return json.dumps(
        {
            "query": query,
            "local_source_root": str(source_root),
            "matches": matches,
            "catalogue": "https://github.com/orgs/exApiTools/repositories",
            "note": "The catalogue is the recommended external source for additional maintained ExileAPI plugin examples.",
        },
        indent=2,
    )
def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
