"""A deliberately constrained MCP server for ExileAPI plugin development.

The MCP server helps an agent create source projects, inspect the installed API,
and run builds.  It does not attach to Path of Exile, expose DevTree's runtime
C# evaluator, or modify compiled-plugin directories.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SERVER_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXILEAPI_ROOT = Path.home() / "ExileApi-Compiled"
GENERATED_ROOT = SERVER_ROOT / "generated-plugins"

mcp = FastMCP(
    "ExileAPI Plugin Development",
    instructions=(
        "Use this server to inspect an ExileAPI installation, scaffold source-only "
        "plugins, and run local builds. Do not treat it as a game automation API."
    ),
)


def _safe_plugin_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", name):
        raise ValueError("plugin_name must start with a letter and contain only letters, numbers, '.', '_' or '-'.")
    return name


def _exileapi_root(value: str | None) -> Path:
    root = Path(value).expanduser().resolve() if value else DEFAULT_EXILEAPI_ROOT
    required = ("ExileCore.dll", "GameOffsets.dll")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Not an ExileAPI package directory: {root} (missing {', '.join(missing)})")
    return root


def _generated_project(plugin_name: str) -> Path:
    return (GENERATED_ROOT / _safe_plugin_name(plugin_name)).resolve()


def _run(command: list[str], cwd: Path, timeout: int = 120) -> dict[str, object]:
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return {"ok": False, "error": f"Command not found: {command[0]}", "command": command}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s", "command": command}
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "command": command,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
    }


@mcp.tool()
def discover_environment(exileapi_root: str | None = None) -> str:
    """Report the local ExileAPI references and whether the .NET build tool is available."""
    root = _exileapi_root(exileapi_root)
    references = ["ExileCore.dll", "GameOffsets.dll", "ItemFilterLibrary.dll"]
    return json.dumps(
        {
            "exileapi_root": str(root),
            "references": {name: (root / name).is_file() for name in references},
            "source_link": str(root / "Plugins" / "Source" / SERVER_ROOT.name),
            "dotnet": shutil.which("dotnet"),
            "generated_plugins_root": str(GENERATED_ROOT),
            "safety": "No game-process inspection, input, memory writes, or arbitrary C# evaluation is exposed.",
        },
        indent=2,
    )


@mcp.tool()
def scaffold_plugin(plugin_name: str, description: str, overwrite: bool = False) -> str:
    """Create a minimal source-only ExileAPI plugin under generated-plugins/."""
    name = _safe_plugin_name(plugin_name)
    project_dir = _generated_project(name)
    if project_dir.exists() and not overwrite:
        raise ValueError(f"Project already exists: {project_dir}. Set overwrite=true to replace the generated files.")
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{name}.csproj").write_text(
        f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0-windows</TargetFramework>
    <OutputType>Library</OutputType>
    <UseWindowsForms>true</UseWindowsForms>
    <PlatformTarget>x64</PlatformTarget>
    <LangVersion>latest</LangVersion>
    <DebugType>embedded</DebugType>
    <PathMap>$(MSBuildProjectDirectory)=$(MSBuildProjectName)</PathMap>
    <EmbedAllSources>true</EmbedAllSources>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="ExileCore"><HintPath>$(exapiPackage)\\ExileCore.dll</HintPath><Private>False</Private></Reference>
    <Reference Include="GameOffsets"><HintPath>$(exapiPackage)\\GameOffsets.dll</HintPath><Private>False</Private></Reference>
  </ItemGroup>
</Project>
''', encoding="utf-8")
    (project_dir / f"{name}.cs").write_text(
        f'''using ExileCore;
using ExileCore.PoEMemory;
using ExileCore.Shared.Interfaces;

namespace {name};

public sealed class {name}Settings : ISettings
{{
    public bool Enable {{ get; set; }} = true;
}}

public sealed class {name}Plugin : BaseSettingsPlugin<{name}Settings>
{{
    public override bool Initialise() => true;
    public override void AreaChange(AreaInstance area) {{ }}
    public override void Render() {{ }}
}}
''', encoding="utf-8")
    (project_dir / "README.md").write_text(f"# {name}\n\n{description.strip()}\n", encoding="utf-8")
    return json.dumps({"created": str(project_dir), "project": f"{name}.csproj", "source": f"{name}.cs"}, indent=2)


@mcp.tool()
def build_plugin(plugin_name: str, exileapi_root: str | None = None) -> str:
    """Build a previously scaffolded plugin using the local ExileAPI DLL references."""
    root = _exileapi_root(exileapi_root)
    project_dir = _generated_project(plugin_name)
    project = project_dir / f"{_safe_plugin_name(plugin_name)}.csproj"
    if not project.is_file():
        raise ValueError(f"No generated plugin project found at {project}")
    return json.dumps(_run(["dotnet", "build", str(project), f"-p:exapiPackage={root}"], project_dir), indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
