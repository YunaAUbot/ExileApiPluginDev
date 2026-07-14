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

from exileapi_plugin_dev.core import read_tail, scaffold_plugin as write_plugin_scaffold

# server.py -> exileapi_plugin_dev -> src -> repository root
SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXILEAPI_ROOT = Path.home() / "ExileApi-Compiled"
GENERATED_ROOT = SERVER_ROOT / "generated-plugins"

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
            "generated_plugins_root": str(GENERATED_ROOT),
            "build_workflow": "Use ExileAPI's in-game Build/Reload button; this MCP does not invoke dotnet.",
            "safety": "No game-process inspection, input, memory writes, or arbitrary C# evaluation is exposed.",
        },
        indent=2,
    )


@mcp.tool()
def scaffold_plugin(plugin_name: str, description: str, overwrite: bool = False) -> str:
    """Create a minimal source-only ExileAPI plugin under generated-plugins/."""
    return json.dumps(write_plugin_scaffold(GENERATED_ROOT, plugin_name, description, overwrite), indent=2)


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


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
