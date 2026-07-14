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
from exileapi_plugin_dev.snapshot_archive import filter_entries, load_or_build_index, read_member, select_entries, top_level_summary

# server.py -> exileapi_plugin_dev -> src -> repository root
SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXILEAPI_ROOT = Path.home() / "ExileApi-Compiled"
WORKSPACE_ROOT = Path.home() / "ExileApiPlugins"
SNAPSHOT_ROOT = DEFAULT_EXILEAPI_ROOT / "snapshots"
SNAPSHOT_INDEX_ROOT = SERVER_ROOT / ".snapshot-index"
BRIDGE_CAPTURE_REQUEST = SERVER_ROOT / "capture-request.json"
BRIDGE_CAPTURE_PROFILES = {
    "Overview": "All DevTree shortcuts with the bridge's configured limits.",
    "Player": "Player only; depth 8, 5,000 nodes, 500 collection entries.",
    "PlayerInventory": "PlayerInventory and PlayerInventory.Items; depth 10, 5,000 nodes, 1,000 collection entries.",
    "UIHover": "UIHover only; depth 10, 3,000 nodes, 1,000 collection entries.",
    "IngameUI": "IngameUI only; depth 8, 5,000 nodes, 500 collection entries.",
    "Custom": "Only supplied shortcut names, with the bridge's configured limits.",
}
BRIDGE_SHORTCUTS = {
    "GameController", "TheGame", "Player", "IngameState", "IngameUI",
    "IngameState.Data", "IngameState.Data.ServerData", "PlayerInventory",
    "PlayerInventory.Items", "ItemsOnGroundLabels", "UIHover",
}

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
def prepare_game_snapshot_capture(profile: str, custom_sections: list[str] | None = None) -> str:
    """Prepare a bounded bridge capture profile; the user must still press Capture snapshot in-game."""
    matched_profile = next((name for name in BRIDGE_CAPTURE_PROFILES if name.casefold() == profile.strip().casefold()), None)
    if not matched_profile:
        raise ValueError(f"Unknown profile. Available profiles: {', '.join(BRIDGE_CAPTURE_PROFILES)}")
    sections = list(dict.fromkeys(custom_sections or []))
    if matched_profile == "Custom":
        if not sections:
            raise ValueError("Custom requires at least one custom_sections entry.")
        invalid = sorted(set(sections) - BRIDGE_SHORTCUTS)
        if invalid:
            raise ValueError(f"Unknown DevTree shortcuts: {', '.join(invalid)}")
    elif sections:
        raise ValueError("custom_sections is allowed only with the Custom profile.")
    request = {
        "schemaVersion": 1,
        "Profile": matched_profile,
        "Sections": sections,
        "preparedAtUtc": datetime.now(timezone.utc).isoformat(),
    }
    BRIDGE_CAPTURE_REQUEST.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    return json.dumps(
        {
            "request_path": str(BRIDGE_CAPTURE_REQUEST),
            "profile": matched_profile,
            "custom_sections": sections,
            "profile_description": BRIDGE_CAPTURE_PROFILES[matched_profile],
            "safety": "The request only selects bounded, read-only export data. It is consumed only when the user presses Capture snapshot in the enabled bridge plugin.",
            "next_step": "Enable UsePendingMcpCaptureRequest and press Capture snapshot in ExileAPI; the bridge removes this request after a successful export.",
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


def _snapshot_path(snapshot_name: str) -> Path:
    if Path(snapshot_name).name != snapshot_name or not snapshot_name.endswith(".exapisnap"):
        raise ValueError("snapshot_name must be the basename of an .exapisnap file.")
    snapshot = SNAPSHOT_ROOT / snapshot_name
    if not snapshot.is_file():
        raise ValueError(f"Snapshot does not exist: {snapshot_name}")
    return snapshot


@mcp.tool()
def list_core_snapshots() -> str:
    """List ExileAPI's .exapisnap files without reading their multi-gigabyte contents."""
    snapshots = []
    for snapshot in sorted(SNAPSHOT_ROOT.glob("*.exapisnap"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = snapshot.stat()
        snapshots.append(
            {
                "name": snapshot.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "index_cached": (SNAPSHOT_INDEX_ROOT / f"{snapshot.name}.index.json").is_file(),
            }
        )
    return json.dumps({"snapshot_root": str(SNAPSHOT_ROOT), "snapshots": snapshots}, indent=2)


@mcp.tool()
def inspect_core_snapshot(snapshot_name: str, path_prefix: str = "", query: str = "", limit: int = 100) -> str:
    """Build/read a header-only snapshot index and return a bounded table of matching archive paths."""
    snapshot = _snapshot_path(snapshot_name)
    index = load_or_build_index(snapshot, SNAPSHOT_INDEX_ROOT)
    return json.dumps(
        {
            "snapshot": snapshot.name,
            "size": index["size"],
            "entry_count": len(index["entries"]),
            "top_level": top_level_summary(index),
            "matches": select_entries(index, path_prefix, query, limit),
            "note": "Only TAR headers were read; member bodies were skipped with seeks.",
        },
        indent=2,
    )


@mcp.tool()
def find_core_snapshot_paths(
    snapshot_name: str, include_terms: list[str], exclude_terms: list[str] | None = None, limit: int = 100
) -> str:
    """Return only indexed snapshot paths matching all include terms and none of the excluded terms."""
    snapshot = _snapshot_path(snapshot_name)
    index = load_or_build_index(snapshot, SNAPSHOT_INDEX_ROOT)
    return json.dumps(
        {
            "snapshot": snapshot.name,
            "include_terms": include_terms,
            "exclude_terms": exclude_terms or [],
            "matches": filter_entries(index, include_terms, exclude_terms or [], limit),
            "note": "Filtered from the cached TAR table of contents only; no member data was read.",
        },
        indent=2,
    )


@mcp.tool()
def read_core_snapshot_member(snapshot_name: str, path: str, max_bytes: int = 100_000) -> str:
    """Read a bounded byte range from one exact, indexed regular-file path in an ExileAPI snapshot."""
    snapshot = _snapshot_path(snapshot_name)
    index = load_or_build_index(snapshot, SNAPSHOT_INDEX_ROOT)
    data = read_member(snapshot, index, path, max_bytes)
    text = data.decode("utf-8", errors="replace")
    printable = sum(character.isprintable() or character in "\r\n\t" for character in text)
    return json.dumps(
        {
            "snapshot": snapshot.name,
            "path": path,
            "bytes_returned": len(data),
            "likely_text": printable / max(1, len(text)) > 0.9,
            "content": text if printable / max(1, len(text)) > 0.9 else data[:256].hex(),
            "content_encoding": "utf-8" if printable / max(1, len(text)) > 0.9 else "hex-prefix",
        },
        indent=2,
    )
def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
