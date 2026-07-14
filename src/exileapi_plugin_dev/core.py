"""Pure helpers for the ExileAPI development MCP.

Keeping file generation separate from the MCP transport makes its safety rules
and templates independently testable.
"""

from __future__ import annotations

import re
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


def read_tail(path: Path, max_lines: int) -> str:
    if not 1 <= max_lines <= 1_000:
        raise ValueError("max_lines must be between 1 and 1000.")
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
