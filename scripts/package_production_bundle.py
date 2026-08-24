#!/usr/bin/env python3
"""Build an installable production lihi marketplace without changing sources."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Sequence, Tuple


PLUGIN_NAME = "lihi"
MARKETPLACE_NAME = "lihi"
PLUGIN_SELECTOR = "lihi@lihi"
DISPLAY_NAME = "lihi"
MCP_NAME = "lihi"
PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
DEVELOP_ORIGIN = "https://app.lihidev.com"

SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)
PLUGIN_ROOTS = (
    Path("plugins/codex/lihi"),
    Path("plugins/claude/lihi"),
)
PLUGIN_MANIFESTS = (
    Path("plugins/codex/lihi/.codex-plugin/plugin.json"),
    Path("plugins/claude/lihi/.claude-plugin/plugin.json"),
)
MARKETPLACE_MANIFESTS = (
    Path(".agents/plugins/marketplace.json"),
    Path(".claude-plugin/marketplace.json"),
)
INCLUDED_PATHS = (
    Path(".agents"),
    Path(".claude-plugin"),
    *PLUGIN_ROOTS,
    Path("README.md"),
    Path("README.zh-TW.md"),
)
RUNTIME_ENDPOINT_FILES = (
    Path("plugins/codex/lihi/.mcp.json"),
    Path("plugins/codex/lihi/skills/lihi-shorten/agents/openai.yaml"),
    Path("plugins/codex/lihi/skills/lihi-account/agents/openai.yaml"),
    Path("plugins/codex/lihi/skills/lihi-switch-group/agents/openai.yaml"),
    Path("plugins/codex/lihi/skills/lihi-switch-domain/agents/openai.yaml"),
    Path("plugins/claude/lihi/.mcp.json"),
)

SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
BRAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])lihi(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


class PackagingError(RuntimeError):
    """Raised when the source tree cannot produce a production package."""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackagingError("Cannot read JSON file {0}: {1}".format(path, exc))
    if not isinstance(value, dict):
        raise PackagingError("Expected a JSON object in {0}".format(path))
    return value


def semantic_version_core(version: object, manifest: Path) -> str:
    if not isinstance(version, str):
        raise PackagingError("Missing string version in {0}".format(manifest))
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise PackagingError(
            "Invalid semantic version {0!r} in {1}".format(version, manifest)
        )
    return ".".join(match.groups())


def release_version(repo_root: Path) -> str:
    versions = set()
    for relative_path in PLUGIN_MANIFESTS:
        path = repo_root / relative_path
        manifest = read_json(path)
        manifest_version = manifest.get("version")
        version_core = semantic_version_core(manifest_version, path)
        if manifest_version != version_core:
            raise PackagingError(
                "Production manifests must use plain major.minor.patch "
                "versions without build metadata: {0}".format(path)
            )
        versions.add(version_core)
    if len(versions) != 1:
        raise PackagingError(
            "Codex and Claude manifests must share one major.minor.patch version"
        )
    return versions.pop()


def marketplace_plugin(marketplace: dict, path: Path) -> dict:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise PackagingError("Expected exactly one plugin entry in {0}".format(path))
    plugin = plugins[0]
    if not isinstance(plugin, dict) or plugin.get("name") != PLUGIN_NAME:
        raise PackagingError("Marketplace plugin must be production lihi: {0}".format(path))
    return plugin


def marketplace_source_path(plugin: dict, codex: bool) -> object:
    source = plugin.get("source")
    if codex:
        if not isinstance(source, dict):
            return None
        return source.get("path")
    return source


def validate_mcp(path: Path) -> None:
    config = read_json(path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or list(servers) != [MCP_NAME]:
        raise PackagingError("Expected one production lihi MCP server in {0}".format(path))
    server = servers[MCP_NAME]
    if not isinstance(server, dict) or server.get("url") != PRODUCTION_ENDPOINT:
        raise PackagingError("Production MCP endpoint is invalid in {0}".format(path))


def validate_source_bundle(repo_root: Path) -> str:
    version = release_version(repo_root)
    expected_sources = (
        "./plugins/codex/lihi",
        "./plugins/claude/lihi",
    )
    for index, relative_path in enumerate(MARKETPLACE_MANIFESTS):
        path = repo_root / relative_path
        marketplace = read_json(path)
        if marketplace.get("name") != MARKETPLACE_NAME:
            raise PackagingError("Marketplace must be production lihi: {0}".format(path))
        plugin = marketplace_plugin(marketplace, path)
        if marketplace_source_path(plugin, codex=index == 0) != expected_sources[index]:
            raise PackagingError("Marketplace source is invalid: {0}".format(path))
        interface = marketplace.get("interface")
        display_name = (
            interface.get("displayName")
            if index == 0 and isinstance(interface, dict)
            else plugin.get("displayName")
        )
        if display_name != DISPLAY_NAME:
            raise PackagingError("Marketplace display name is invalid: {0}".format(path))

    for index, relative_path in enumerate(PLUGIN_MANIFESTS):
        path = repo_root / relative_path
        manifest = read_json(path)
        interface = manifest.get("interface")
        display_name = (
            interface.get("displayName")
            if index == 0 and isinstance(interface, dict)
            else manifest.get("displayName")
        )
        if manifest.get("name") != PLUGIN_NAME or display_name != DISPLAY_NAME:
            raise PackagingError("Plugin manifest must be production lihi: {0}".format(path))

    for plugin_root in PLUGIN_ROOTS:
        root = repo_root / plugin_root
        if root.is_symlink() or not root.is_dir():
            raise PackagingError("Production plugin root is missing: {0}".format(root))
        validate_mcp(root / ".mcp.json")
        skills_root = root / "skills"
        actual_skills = {
            path.name
            for path in skills_root.iterdir()
            if path.is_dir() and not path.is_symlink()
        }
        if actual_skills != set(SKILLS):
            raise PackagingError(
                "Production skill set is invalid in {0}: {1!r}".format(
                    skills_root,
                    tuple(sorted(actual_skills)),
                )
            )
        for skill_name in SKILLS:
            skill_path = skills_root / skill_name / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8")
            if "\nname: {0}\n".format(skill_name) not in content:
                raise PackagingError("Production skill identity is invalid: {0}".format(skill_path))

    for relative_path in RUNTIME_ENDPOINT_FILES:
        path = repo_root / relative_path
        content = path.read_text(encoding="utf-8")
        if PRODUCTION_ENDPOINT not in content or DEVELOP_ORIGIN in content:
            raise PackagingError("Runtime endpoint is not production-only: {0}".format(path))

    codex_skills = repo_root / "plugins/codex/lihi/skills"
    for skill_name in SKILLS:
        metadata_path = codex_skills / skill_name / "agents/openai.yaml"
        metadata = metadata_path.read_text(encoding="utf-8")
        if (
            "$" + skill_name not in metadata
            or 'value: "lihi"' not in metadata
            or PRODUCTION_ENDPOINT not in metadata
        ):
            raise PackagingError("Codex production dependency is invalid: {0}".format(metadata_path))

    detector = codex_skills / "lihi-shorten/scripts/detect_urls.py"
    if not detector.stat().st_mode & 0o111:
        raise PackagingError("Production detector must remain executable: {0}".format(detector))
    return version


def ignored_path(_directory: str, names: Sequence[str]) -> Sequence[str]:
    return [
        name
        for name in names
        if name == "__pycache__"
        or name == ".DS_Store"
        or name.endswith((".pyc", ".pyo"))
    ]


def copy_distribution_files(repo_root: Path, staging_root: Path) -> None:
    for relative_path in INCLUDED_PATHS:
        source = repo_root / relative_path
        target = staging_root / relative_path
        if source.is_symlink() or not source.exists():
            raise PackagingError("Required distribution path is missing: {0}".format(source))
        if source.is_dir():
            for candidate in source.rglob("*"):
                if candidate.is_symlink():
                    raise PackagingError(
                        "Symbolic links are not allowed in production packages: "
                        "{0}".format(candidate)
                    )
                if candidate.is_dir():
                    continue
                if not candidate.is_file() or not stat.S_ISREG(
                    candidate.stat().st_mode
                ):
                    raise PackagingError(
                        "Only regular files are allowed in production packages: "
                        "{0}".format(candidate)
                    )
            shutil.copytree(
                str(source),
                str(target),
                copy_function=shutil.copy2,
                ignore=ignored_path,
            )
        elif source.is_file() and stat.S_ISREG(source.stat().st_mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))
        else:
            raise PackagingError("Distribution path is not a regular file: {0}".format(source))


def iter_text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".yaml", ".yml"}:
            yield path


def validate_staged_package(staging_root: Path, version: str) -> None:
    if validate_source_bundle(staging_root) != version:
        raise PackagingError("Staged production version changed")
    for path in iter_text_files(staging_root):
        content = path.read_text(encoding="utf-8")
        for match in BRAND_PATTERN.finditer(content):
            if match.group(0) != "lihi":
                raise PackagingError("Brand must be lowercase lihi: {0}".format(path))
        if DEVELOP_ORIGIN in content or "lihi-dev" in content:
            raise PackagingError("Develop identity found in production package: {0}".format(path))

    source_detector = staging_root / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
    if not source_detector.stat().st_mode & 0o111:
        raise PackagingError("Packaged detector must remain executable")


def publish_package(staging_root: Path, output_dir: Path, version: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "lihi-agent-{0}".format(version)
    if target.is_symlink() or target.exists():
        raise PackagingError("Production package output already exists: {0}".format(target))
    try:
        with tempfile.TemporaryDirectory(
            prefix=".lihi-agent-production-",
            dir=str(output_dir),
        ) as temporary:
            candidate = Path(temporary) / target.name
            shutil.copytree(str(staging_root), str(candidate), copy_function=shutil.copy2)
            validate_staged_package(candidate, version)
            if target.is_symlink() or target.exists():
                raise PackagingError("Production package output appeared during build: {0}".format(target))
            os.replace(str(candidate), str(target))
    except OSError as exc:
        raise PackagingError("Cannot publish production package {0}: {1}".format(target, exc))
    return target


def package_production_bundle(repo_root: Path, output_dir: Path) -> Tuple[Path, str]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    version = validate_source_bundle(repo_root)
    with tempfile.TemporaryDirectory(prefix="lihi-agent-production-") as temporary:
        staging_root = Path(temporary) / "package"
        staging_root.mkdir()
        copy_distribution_files(repo_root, staging_root)
        validate_staged_package(staging_root, version)
        package_path = publish_package(staging_root, output_dir, version)
    return package_path, version


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        package_path, version = package_production_bundle(repo_root, args.output_dir)
    except (OSError, PackagingError, UnicodeError, ValueError) as exc:
        raise SystemExit("error: {0}".format(exc))
    print("Created: {0}".format(package_path))
    print("Version: {0}".format(version))
    print("Plugin: {0}".format(PLUGIN_SELECTOR))
    print("MCP endpoint: {0}".format(PRODUCTION_ENDPOINT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
