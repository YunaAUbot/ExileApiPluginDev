"""Pure helpers for the ExileAPI development MCP.

Keeping file generation separate from the MCP transport makes its safety rules
and templates independently testable.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PLUGIN_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")


def validate_plugin_name(name: str) -> str:
    if not PLUGIN_NAME_RE.fullmatch(name):
        raise ValueError("plugin_name must start with a letter and contain only letters, numbers, '.', '_' or '-'.")
    return name


def csharp_identifier(name: str) -> str:
    """Convert a permitted plugin name to a valid C# namespace/type fragment."""
    validate_plugin_name(name)
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def scaffold_plugin(generated_root: Path, plugin_name: str, description: str, overwrite: bool = False) -> dict[str, str]:
    """Write a minimal source-only plugin below a caller-supplied safe root."""
    name = validate_plugin_name(plugin_name)
    identifier = csharp_identifier(name)
    project_dir = (generated_root / name).resolve()
    generated_root = generated_root.resolve()
    if generated_root not in project_dir.parents:
        raise ValueError("Generated project path escapes the configured plugin root.")
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
''',
        encoding="utf-8",
    )
    (project_dir / f"{name}.cs").write_text(
        f'''using ExileCore;
using ExileCore.PoEMemory;
using ExileCore.Shared.Interfaces;
using ExileCore.Shared.Nodes;

namespace {identifier};

public sealed class {identifier}Settings : ISettings
{{
    public ToggleNode Enable {{ get; set; }} = new(true);
}}

public sealed class {identifier}Plugin : BaseSettingsPlugin<{identifier}Settings>
{{
    public override bool Initialise() => true;
    public override void AreaChange(AreaInstance area) {{ }}
    public override void Render() {{ }}
}}
''',
        encoding="utf-8",
    )
    (project_dir / "README.md").write_text(f"# {name}\n\n{description.strip()}\n", encoding="utf-8")
    return {"created": str(project_dir), "project": f"{name}.csproj", "source": f"{name}.cs"}


def create_plugin_workspace(
    workspace_root: Path, source_root: Path, plugin_name: str, description: str
) -> dict[str, str]:
    """Create an independent local Git repository and link it into ExileAPI source plugins."""
    name = validate_plugin_name(plugin_name)
    workspace_root = workspace_root.resolve()
    source_root = source_root.resolve()
    workspace = (workspace_root / name).resolve()
    source_link = source_root / name
    if workspace_root not in workspace.parents:
        raise ValueError("Workspace path escapes the configured workspace root.")
    source_root.mkdir(parents=True, exist_ok=True)
    if workspace.exists():
        raise ValueError(f"Workspace already exists: {workspace}")
    if source_link.exists() or source_link.is_symlink():
        raise ValueError(f"ExileAPI source entry already exists: {source_link}")

    result = scaffold_plugin(workspace_root, name, description)
    git_init = subprocess.run(["git", "init", "-b", "main", str(workspace)], text=True, capture_output=True, check=False)
    if git_init.returncode != 0:
        raise RuntimeError(f"Could not initialise Git repository: {git_init.stderr.strip()}")
    subprocess.run(["git", "-C", str(workspace), "config", "user.name", "yuna"], text=True, capture_output=True, check=False)
    subprocess.run(["git", "-C", str(workspace), "config", "user.email", "yuna@auron.cloud"], text=True, capture_output=True, check=False)
    source_link.symlink_to(workspace, target_is_directory=True)
    return result | {"workspace": str(workspace), "source_link": str(source_link), "git_repository": str(workspace / ".git")}


def read_tail(path: Path, max_lines: int) -> str:
    if not 1 <= max_lines <= 1_000:
        raise ValueError("max_lines must be between 1 and 1000.")
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
