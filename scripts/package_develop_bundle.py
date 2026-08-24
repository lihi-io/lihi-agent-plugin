#!/usr/bin/env python3
"""Build an installable lihi develop marketplace without changing source files."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Tuple


PRODUCTION_ORIGIN = "https://app.lihi.io"
DEVELOP_ORIGIN = "https://app.lihidev.com"
PRODUCTION_ENDPOINT = PRODUCTION_ORIGIN + "/mcp/v1/tools"
DEVELOP_ENDPOINT = DEVELOP_ORIGIN + "/mcp/v1/tools"

PRODUCTION_MARKETPLACE_NAME = "lihi"
DEVELOP_MARKETPLACE_NAME = "lihi-dev"
PRODUCTION_PLUGIN_NAME = "lihi"
DEVELOP_PLUGIN_NAME = "lihi-dev"
PRODUCTION_PLUGIN_SELECTOR = (
    PRODUCTION_PLUGIN_NAME + "@" + PRODUCTION_MARKETPLACE_NAME
)
DEVELOP_PLUGIN_SELECTOR = DEVELOP_PLUGIN_NAME + "@" + DEVELOP_MARKETPLACE_NAME
PRODUCTION_DISPLAY_NAME = "lihi"
DEVELOP_DISPLAY_NAME = "lihi (Develop)"
PRODUCTION_MCP_NAME = "lihi"
DEVELOP_MCP_NAME = "lihi-dev"

PRODUCTION_SKILL_NAME = "lihi-shorten"
DEVELOP_SKILL_NAME = "lihi-shorten-dev"
PRODUCTION_ACCOUNT_SKILL_NAME = "lihi-account"
DEVELOP_ACCOUNT_SKILL_NAME = "lihi-account-dev"
PRODUCTION_SWITCH_GROUP_SKILL_NAME = "lihi-switch-group"
DEVELOP_SWITCH_GROUP_SKILL_NAME = "lihi-switch-group-dev"
PRODUCTION_SWITCH_DOMAIN_SKILL_NAME = "lihi-switch-domain"
DEVELOP_SWITCH_DOMAIN_SKILL_NAME = "lihi-switch-domain-dev"

PRODUCTION_PLUGIN_ROOTS = (
    Path("plugins/codex/lihi"),
    Path("plugins/claude/lihi"),
)
DEVELOP_PLUGIN_ROOTS = (
    Path("plugins/codex/lihi-dev"),
    Path("plugins/claude/lihi-dev"),
)
PLUGIN_ROOT_PAIRS = tuple(zip(PRODUCTION_PLUGIN_ROOTS, DEVELOP_PLUGIN_ROOTS))
PLUGIN_MANIFESTS = (
    Path("plugins/codex/lihi/.codex-plugin/plugin.json"),
    Path("plugins/claude/lihi/.claude-plugin/plugin.json"),
)
DEVELOP_PLUGIN_MANIFESTS = (
    Path("plugins/codex/lihi-dev/.codex-plugin/plugin.json"),
    Path("plugins/claude/lihi-dev/.claude-plugin/plugin.json"),
)
MARKETPLACE_MANIFESTS = (
    Path(".agents/plugins/marketplace.json"),
    Path(".claude-plugin/marketplace.json"),
)
INCLUDED_PATHS = (
    Path(".agents"),
    Path(".claude-plugin"),
    *PRODUCTION_PLUGIN_ROOTS,
    Path("README.md"),
    Path("README.zh-TW.md"),
    Path("docs"),
)

SKILL_IDENTITIES = (
    (PRODUCTION_SKILL_NAME, DEVELOP_SKILL_NAME),
    (PRODUCTION_ACCOUNT_SKILL_NAME, DEVELOP_ACCOUNT_SKILL_NAME),
    (
        PRODUCTION_SWITCH_GROUP_SKILL_NAME,
        DEVELOP_SWITCH_GROUP_SKILL_NAME,
    ),
    (
        PRODUCTION_SWITCH_DOMAIN_SKILL_NAME,
        DEVELOP_SWITCH_DOMAIN_SKILL_NAME,
    ),
)
SKILL_PATH_PAIRS = tuple(
    (
        plugin_root / "skills" / production_name,
        plugin_root / "skills" / develop_name,
        production_name,
        develop_name,
    )
    for plugin_root in PRODUCTION_PLUGIN_ROOTS
    for production_name, develop_name in SKILL_IDENTITIES
)
DEVELOP_SKILL_PATHS = tuple(
    develop_root / "skills" / develop_name
    for develop_root in DEVELOP_PLUGIN_ROOTS
    for _production_name, develop_name in SKILL_IDENTITIES
)

SOURCE_RUNTIME_ENDPOINT_FILES = (
    Path("plugins/codex/lihi/.mcp.json"),
    Path("plugins/codex/lihi/skills/lihi-shorten/agents/openai.yaml"),
    Path("plugins/codex/lihi/skills/lihi-account/agents/openai.yaml"),
    Path(
        "plugins/codex/lihi/skills/"
        "lihi-switch-group/agents/openai.yaml"
    ),
    Path(
        "plugins/codex/lihi/skills/"
        "lihi-switch-domain/agents/openai.yaml"
    ),
    Path("plugins/claude/lihi/.mcp.json"),
)
DEVELOP_RUNTIME_ENDPOINT_FILES = (
    Path("plugins/codex/lihi-dev/.mcp.json"),
    Path(
        "plugins/codex/lihi-dev/skills/"
        "lihi-shorten-dev/agents/openai.yaml"
    ),
    Path(
        "plugins/codex/lihi-dev/skills/"
        "lihi-account-dev/agents/openai.yaml"
    ),
    Path(
        "plugins/codex/lihi-dev/skills/"
        "lihi-switch-group-dev/agents/openai.yaml"
    ),
    Path(
        "plugins/codex/lihi-dev/skills/"
        "lihi-switch-domain-dev/agents/openai.yaml"
    ),
    Path("plugins/claude/lihi-dev/.mcp.json"),
)

TEXT_SUFFIXES = {".json", ".md", ".yaml", ".yml"}
PACKAGE_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "openai-platform-packaging.md",
)
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
BRAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])lihi(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
BRAND_RULE = (
    "Always render the brand name exactly as `lihi` in lowercase in every "
    "user-facing message and generated copy"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")


class PackagingError(RuntimeError):
    """Raised when the source tree cannot produce a safe develop package."""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagingError("Cannot read JSON file {0}: {1}".format(path, exc))
    if not isinstance(value, dict):
        raise PackagingError("Expected a JSON object in {0}".format(path))
    return value


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def semantic_version_core(version: object, manifest: Path) -> str:
    if not isinstance(version, str):
        raise PackagingError("Missing string version in {0}".format(manifest))
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise PackagingError(
            "Invalid semantic version {0!r} in {1}".format(version, manifest)
        )
    return ".".join(match.groups())


def build_develop_version(repo_root: Path, build_number: str) -> str:
    normalized_build = str(int(build_number)) if build_number.isdigit() else ""
    if not normalized_build:
        raise PackagingError("build-number must be a non-negative integer")

    version_cores = set()
    for relative_path in PLUGIN_MANIFESTS:
        manifest_path = repo_root / relative_path
        manifest = read_json(manifest_path)
        manifest_version = manifest.get("version")
        version_core = semantic_version_core(manifest_version, manifest_path)
        if manifest_version != version_core:
            raise PackagingError(
                "Production manifests must use plain major.minor.patch "
                "versions without build metadata: {0}".format(manifest_path)
            )
        version_cores.add(version_core)
    if len(version_cores) != 1:
        raise PackagingError(
            "All Codex and Claude manifests must have the same "
            "major.minor.patch version"
        )

    return "{0}-develop.{1}".format(
        version_cores.pop(),
        normalized_build,
    )


def codex_develop_version(version: str) -> str:
    _prefix, separator, build_number = version.rpartition("-develop.")
    if not separator or not build_number.isdigit():
        raise PackagingError(
            "Codex cachebuster requires a generated develop version"
        )
    return "{0}+codex.{1}".format(version, build_number)


def marketplace_plugin(
    marketplace: dict,
    path: Path,
    expected_name: str,
) -> dict:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise PackagingError("Expected plugin entries in {0}".format(path))
    matches = [
        plugin
        for plugin in plugins
        if isinstance(plugin, dict) and plugin.get("name") == expected_name
    ]
    if len(matches) != 1:
        raise PackagingError(
            "Expected exactly one {0!r} plugin entry in {1}".format(
                expected_name,
                path,
            )
        )
    return matches[0]


def validate_marketplace_plugin_names(
    marketplace: dict,
    path: Path,
    expected_names: Tuple[str, ...],
) -> None:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or any(
        not isinstance(plugin, dict) for plugin in plugins
    ):
        raise PackagingError("Expected plugin entries in {0}".format(path))
    actual_names = tuple(plugin.get("name") for plugin in plugins)
    if actual_names != expected_names:
        raise PackagingError(
            "Expected marketplace plugins {0!r} in {1}, got {2!r}".format(
                expected_names,
                path,
                actual_names,
            )
        )


def validate_mcp_server_name(path: Path, expected_name: str) -> None:
    config = read_json(path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or list(servers) != [expected_name]:
        raise PackagingError(
            "Expected only MCP server {0!r} in {1}".format(
                expected_name,
                path,
            )
        )


def marketplace_source_path(plugin: dict, codex: bool) -> object:
    source = plugin.get("source")
    if codex:
        if not isinstance(source, dict):
            return None
        return source.get("path")
    return source


def validate_source_bundle(repo_root: Path) -> None:
    for relative_path in SOURCE_RUNTIME_ENDPOINT_FILES:
        path = repo_root / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PackagingError(
                "Cannot read runtime config {0}: {1}".format(path, exc)
            )
        if PRODUCTION_ENDPOINT not in content or DEVELOP_ENDPOINT in content:
            raise PackagingError(
                "Source runtime config must contain only the production MCP "
                "endpoint: {0}".format(relative_path)
            )

    expected_sources = (
        "./plugins/codex/lihi",
        "./plugins/claude/lihi",
    )
    for index, relative_path in enumerate(MARKETPLACE_MANIFESTS):
        path = repo_root / relative_path
        marketplace = read_json(path)
        if marketplace.get("name") != PRODUCTION_MARKETPLACE_NAME:
            raise PackagingError(
                "Source marketplace must remain production-only: {0}".format(
                    path
                )
            )
        validate_marketplace_plugin_names(
            marketplace,
            path,
            (PRODUCTION_PLUGIN_NAME,),
        )
        plugin = marketplace_plugin(
            marketplace,
            path,
            PRODUCTION_PLUGIN_NAME,
        )
        if marketplace_source_path(plugin, codex=index == 0) != expected_sources[index]:
            raise PackagingError(
                "Source marketplace points at the wrong plugin root: {0}".format(
                    path
                )
            )
        marketplace_interface = marketplace.get("interface")
        if index == 0 and isinstance(marketplace_interface, dict):
            marketplace_display_name = marketplace_interface.get("displayName")
        else:
            marketplace_display_name = plugin.get("displayName")
        if marketplace_display_name != PRODUCTION_DISPLAY_NAME:
            raise PackagingError(
                "Source marketplace has the wrong display name: {0}".format(
                    path
                )
            )

    for index, relative_path in enumerate(PLUGIN_MANIFESTS):
        path = repo_root / relative_path
        manifest = read_json(path)
        interface = manifest.get("interface")
        display_name = (
            interface.get("displayName")
            if index == 0 and isinstance(interface, dict)
            else manifest.get("displayName")
        )
        if (
            manifest.get("name") != PRODUCTION_PLUGIN_NAME
            or display_name != PRODUCTION_DISPLAY_NAME
        ):
            raise PackagingError(
                "Source plugin identity must remain production-only: "
                "{0}".format(path)
            )

    for plugin_root in PRODUCTION_PLUGIN_ROOTS:
        validate_mcp_server_name(
            repo_root / plugin_root / ".mcp.json",
            PRODUCTION_MCP_NAME,
        )
    for develop_root in DEVELOP_PLUGIN_ROOTS:
        if (repo_root / develop_root).exists():
            raise PackagingError(
                "Source plugin roots must remain production-only"
            )

    for (
        source_skill_path,
        develop_skill_path,
        production_skill_name,
        _develop_skill_name,
    ) in SKILL_PATH_PAIRS:
        source_path = repo_root / source_skill_path
        if not source_path.is_dir() or (repo_root / develop_skill_path).exists():
            raise PackagingError(
                "Source skill directories must remain production-only"
            )
        skill_content = (source_path / "SKILL.md").read_text(encoding="utf-8")
        if "\nname: {0}\n".format(production_skill_name) not in skill_content:
            raise PackagingError(
                "Source skill name must remain production-only: {0}".format(
                    source_path
                )
            )

    for skill_name, relative_path in (
        (
            PRODUCTION_SKILL_NAME,
            Path(
                "plugins/codex/lihi/skills/"
                "lihi-shorten/agents/openai.yaml"
            ),
        ),
        (
            PRODUCTION_ACCOUNT_SKILL_NAME,
            Path(
                "plugins/codex/lihi/skills/"
                "lihi-account/agents/openai.yaml"
            ),
        ),
        (
            PRODUCTION_SWITCH_GROUP_SKILL_NAME,
            Path(
                "plugins/codex/lihi/skills/"
                "lihi-switch-group/agents/openai.yaml"
            ),
        ),
        (
            PRODUCTION_SWITCH_DOMAIN_SKILL_NAME,
            Path(
                "plugins/codex/lihi/skills/"
                "lihi-switch-domain/agents/openai.yaml"
            ),
        ),
    ):
        openai_yaml = (repo_root / relative_path).read_text(encoding="utf-8")
        if (
            'value: "{0}"'.format(PRODUCTION_MCP_NAME) not in openai_yaml
            or "${0}".format(skill_name) not in openai_yaml
        ):
            raise PackagingError(
                "Codex source skill metadata must remain production-only"
            )


def copy_distribution_files(repo_root: Path, staging_root: Path) -> None:
    for relative_path in INCLUDED_PATHS:
        source = repo_root / relative_path
        target = staging_root / relative_path
        if not source.exists():
            raise PackagingError(
                "Required package path is missing: {0}".format(source)
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(str(source), str(target), ignore=PACKAGE_IGNORE)
        else:
            shutil.copy2(str(source), str(target))


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def rewrite_develop_origin(staging_root: Path) -> None:
    replacement_count = 0
    for path in iter_text_files(staging_root):
        content = path.read_text(encoding="utf-8")
        replacement_count += content.count(PRODUCTION_ORIGIN)
        updated = content.replace(PRODUCTION_ORIGIN, DEVELOP_ORIGIN)
        if path == staging_root / "README.md":
            updated = updated.replace(
                "The production Streamable HTTP endpoint is:",
                "This develop bundle's Streamable HTTP endpoint is:",
            )
        if path == staging_root / "README.zh-TW.md":
            updated = updated.replace(
                "正式環境 Streamable HTTP 端點為：",
                "此開發版成品的 Streamable HTTP 端點為：",
            )
        if updated != content:
            path.write_text(updated, encoding="utf-8")
    if replacement_count == 0:
        raise PackagingError("No production lihi origin was found to rewrite")


def rename_skill_directories(staging_root: Path) -> None:
    for (
        source_relative_path,
        develop_relative_path,
        _production_skill_name,
        _develop_skill_name,
    ) in SKILL_PATH_PAIRS:
        source_path = staging_root / source_relative_path
        develop_path = staging_root / develop_relative_path
        if not source_path.is_dir() or develop_path.exists():
            raise PackagingError(
                "Cannot isolate develop skill directory: {0}".format(
                    source_path
                )
            )
        source_path.rename(develop_path)


def rewrite_develop_text_identities(staging_root: Path) -> None:
    replacements = (
        (
            "skills/lihi-switch-domain",
            "skills/lihi-switch-domain-dev",
        ),
        (
            "skills/lihi-switch-group",
            "skills/lihi-switch-group-dev",
        ),
        ("skills/lihi-account", "skills/lihi-account-dev"),
        ("skills/lihi-shorten", "skills/lihi-shorten-dev"),
        (
            "`" + PRODUCTION_SWITCH_DOMAIN_SKILL_NAME + "`",
            "`" + DEVELOP_SWITCH_DOMAIN_SKILL_NAME + "`",
        ),
        (
            "`" + PRODUCTION_SWITCH_GROUP_SKILL_NAME + "`",
            "`" + DEVELOP_SWITCH_GROUP_SKILL_NAME + "`",
        ),
        (
            "`" + PRODUCTION_ACCOUNT_SKILL_NAME + "`",
            "`" + DEVELOP_ACCOUNT_SKILL_NAME + "`",
        ),
        (
            "`" + PRODUCTION_SKILL_NAME + "`",
            "`" + DEVELOP_SKILL_NAME + "`",
        ),
        ("plugins/codex/lihi", "plugins/codex/lihi-dev"),
        ("plugins/claude/lihi", "plugins/claude/lihi-dev"),
        (PRODUCTION_PLUGIN_SELECTOR, DEVELOP_PLUGIN_SELECTOR),
        (
            "displayed as `" + PRODUCTION_DISPLAY_NAME + "`",
            "displayed as `" + DEVELOP_DISPLAY_NAME + "`",
        ),
        (
            "display name `" + PRODUCTION_DISPLAY_NAME + "`",
            "display name `" + DEVELOP_DISPLAY_NAME + "`",
        ),
        (
            "顯示名稱為 `" + PRODUCTION_DISPLAY_NAME + "`",
            "顯示名稱為 `" + DEVELOP_DISPLAY_NAME + "`",
        ),
        (
            PRODUCTION_DISPLAY_NAME + " client bundle",
            DEVELOP_DISPLAY_NAME + " client bundle",
        ),
        (
            PRODUCTION_DISPLAY_NAME + " 用戶端套件",
            DEVELOP_DISPLAY_NAME + " 用戶端套件",
        ),
        (
            "$" + PRODUCTION_SWITCH_DOMAIN_SKILL_NAME,
            "$" + DEVELOP_SWITCH_DOMAIN_SKILL_NAME,
        ),
        (
            "$" + PRODUCTION_SWITCH_GROUP_SKILL_NAME,
            "$" + DEVELOP_SWITCH_GROUP_SKILL_NAME,
        ),
        (
            "$" + PRODUCTION_ACCOUNT_SKILL_NAME,
            "$" + DEVELOP_ACCOUNT_SKILL_NAME,
        ),
        ("$" + PRODUCTION_SKILL_NAME, "$" + DEVELOP_SKILL_NAME),
        (
            "name: " + PRODUCTION_SWITCH_DOMAIN_SKILL_NAME,
            "name: " + DEVELOP_SWITCH_DOMAIN_SKILL_NAME,
        ),
        (
            "name: " + PRODUCTION_SWITCH_GROUP_SKILL_NAME,
            "name: " + DEVELOP_SWITCH_GROUP_SKILL_NAME,
        ),
        (
            "name: " + PRODUCTION_ACCOUNT_SKILL_NAME,
            "name: " + DEVELOP_ACCOUNT_SKILL_NAME,
        ),
        ("name: " + PRODUCTION_SKILL_NAME, "name: " + DEVELOP_SKILL_NAME),
        (
            'display_name: "{0}"'.format(
                PRODUCTION_SWITCH_DOMAIN_SKILL_NAME
            ),
            'display_name: "{0}"'.format(
                DEVELOP_SWITCH_DOMAIN_SKILL_NAME
            ),
        ),
        (
            'display_name: "{0}"'.format(
                PRODUCTION_SWITCH_GROUP_SKILL_NAME
            ),
            'display_name: "{0}"'.format(
                DEVELOP_SWITCH_GROUP_SKILL_NAME
            ),
        ),
        (
            'display_name: "{0}"'.format(PRODUCTION_ACCOUNT_SKILL_NAME),
            'display_name: "{0}"'.format(DEVELOP_ACCOUNT_SKILL_NAME),
        ),
        (
            'display_name: "{0}"'.format(PRODUCTION_SKILL_NAME),
            'display_name: "{0}"'.format(DEVELOP_SKILL_NAME),
        ),
        (
            'value: "{0}"'.format(PRODUCTION_MCP_NAME),
            'value: "{0}"'.format(DEVELOP_MCP_NAME),
        ),
        ("codex mcp login lihi`", "codex mcp login lihi-dev`"),
        ("codex mcp login lihi\n", "codex mcp login lihi-dev\n"),
        ("codex mcp add lihi ", "codex mcp add lihi-dev "),
        ("remote `lihi` MCP server", "remote `lihi-dev` MCP server"),
        ("remote MCP server `lihi`", "remote MCP server `lihi-dev`"),
        ("the `lihi` MCP server", "the `lihi-dev` MCP server"),
        ("`lihi` MCP 伺服器", "`lihi-dev` MCP 伺服器"),
        ("MCP 伺服器 `lihi`", "MCP 伺服器 `lihi-dev`"),
        ("plugin named `lihi`", "plugin named `lihi-dev`"),
        ("server key is `lihi`", "server key is `lihi-dev`"),
        (
            "logical `lihi` MCP server key",
            "logical `lihi-dev` MCP server key",
        ),
        ("logical server key is `lihi`", "logical server key is `lihi-dev`"),
        ("bundled `lihi` MCP client", "bundled `lihi-dev` MCP client"),
        (
            "MCP settings → lihi → Authenticate",
            "MCP settings → lihi-dev → Authenticate",
        ),
        (
            "MCP 設定 → lihi → 驗證",
            "MCP 設定 → lihi-dev → 驗證",
        ),
        ("the lihi plugin server", "the lihi-dev plugin server"),
        ("select lihi,", "select lihi-dev,"),
        ("選擇 lihi，", "選擇 lihi-dev，"),
        ("選擇 lihi 外掛伺服器", "選擇 lihi-dev 外掛伺服器"),
    )
    for path in iter_text_files(staging_root):
        content = path.read_text(encoding="utf-8")
        updated = content
        for old_value, new_value in replacements:
            updated = updated.replace(old_value, new_value)
        if updated != content:
            path.write_text(updated, encoding="utf-8")


def rename_plugin_directories(staging_root: Path) -> None:
    for production_root, develop_root in PLUGIN_ROOT_PAIRS:
        source_path = staging_root / production_root
        develop_path = staging_root / develop_root
        if not source_path.is_dir() or develop_path.exists():
            raise PackagingError(
                "Cannot isolate develop plugin directory: {0}".format(
                    source_path
                )
            )
        source_path.rename(develop_path)


def update_develop_marketplaces(staging_root: Path) -> None:
    expected_sources = (
        "./plugins/codex/lihi-dev",
        "./plugins/claude/lihi-dev",
    )
    for index, relative_path in enumerate(MARKETPLACE_MANIFESTS):
        path = staging_root / relative_path
        marketplace = read_json(path)
        marketplace["name"] = DEVELOP_MARKETPLACE_NAME
        plugin = marketplace_plugin(
            marketplace,
            path,
            PRODUCTION_PLUGIN_NAME,
        )
        plugin["name"] = DEVELOP_PLUGIN_NAME
        if index == 0:
            interface = marketplace.get("interface")
            if not isinstance(interface, dict):
                raise PackagingError(
                    "Codex marketplace interface must be an object"
                )
            interface["displayName"] = DEVELOP_DISPLAY_NAME
            source = plugin.get("source")
            if not isinstance(source, dict):
                raise PackagingError(
                    "Codex marketplace source must be an object"
                )
            source["path"] = expected_sources[index]
        else:
            marketplace["description"] = "lihi develop agent integrations"
            plugin["displayName"] = DEVELOP_DISPLAY_NAME
            plugin["source"] = expected_sources[index]
            plugin["description"] = (
                "Develop build connecting to lihi through one OAuth MCP "
                "registration for account status, group and domain switching, "
                "and automatic URL shortening."
            )
        write_json(path, marketplace)


def update_develop_plugin_manifests(
    staging_root: Path,
    version: str,
) -> None:
    codex_path = staging_root / DEVELOP_PLUGIN_MANIFESTS[0]
    codex_manifest = read_json(codex_path)
    codex_manifest["name"] = DEVELOP_PLUGIN_NAME
    codex_manifest["version"] = codex_develop_version(version)
    codex_manifest["description"] = (
        "Develop build connecting Codex to lihi through one OAuth MCP "
        "registration for account status, group and domain switching, and "
        "automatic URL shortening."
    )
    codex_interface = codex_manifest.get("interface")
    if not isinstance(codex_interface, dict):
        raise PackagingError("Codex plugin interface must be an object")
    codex_interface["displayName"] = DEVELOP_DISPLAY_NAME
    codex_interface["shortDescription"] = (
        "Develop lihi account and short URL tools"
    )
    codex_interface["longDescription"] = (
        "Develop build connected to the lihi develop MCP server for account "
        "status, group and domain switching, and automatic URL shortening."
    )
    write_json(codex_path, codex_manifest)

    claude_path = staging_root / DEVELOP_PLUGIN_MANIFESTS[1]
    claude_manifest = read_json(claude_path)
    claude_manifest["name"] = DEVELOP_PLUGIN_NAME
    claude_manifest["displayName"] = DEVELOP_DISPLAY_NAME
    claude_manifest["version"] = version
    claude_manifest["description"] = (
        "Develop build connecting Claude Code to lihi through one OAuth MCP "
        "registration for account status, group and domain switching, and "
        "automatic URL shortening."
    )
    write_json(claude_path, claude_manifest)


def update_develop_mcp_identities(staging_root: Path) -> None:
    for plugin_root in DEVELOP_PLUGIN_ROOTS:
        path = staging_root / plugin_root / ".mcp.json"
        config = read_json(path)
        servers = config.get("mcpServers")
        if (
            not isinstance(servers, dict)
            or list(servers) != [PRODUCTION_MCP_NAME]
        ):
            raise PackagingError(
                "Cannot isolate develop MCP identity in {0}".format(path)
            )
        servers[DEVELOP_MCP_NAME] = servers.pop(PRODUCTION_MCP_NAME)
        write_json(path, config)


def rewrite_develop_readme(staging_root: Path) -> None:
    readme_rewrites = (
        (
            Path("README.md"),
            (
                "The production marketplace is available from "
                "[lihi-io/lihi-agent-plugin.git]"
                "(https://github.com/lihi-io/lihi-agent-plugin.git). "
                "The plugin selector is `{0}`, displayed as `{1}`.".format(
                    DEVELOP_PLUGIN_SELECTOR,
                    DEVELOP_DISPLAY_NAME,
                )
            ),
            (
                "This develop marketplace connects to the lihi develop "
                "environment. The plugin selector is `{0}`, displayed as "
                "`{1}`.".format(
                    DEVELOP_PLUGIN_SELECTOR,
                    DEVELOP_DISPLAY_NAME,
                )
            ),
        ),
        (
            Path("README.zh-TW.md"),
            (
                "正式環境市集來源為 [lihi-io/lihi-agent-plugin.git]"
                "(https://github.com/lihi-io/lihi-agent-plugin.git)。"
                "外掛選擇器為 `{0}`，顯示名稱為 `{1}`。".format(
                    DEVELOP_PLUGIN_SELECTOR,
                    DEVELOP_DISPLAY_NAME,
                )
            ),
            (
                "此開發版市集會連線至 lihi 開發環境。外掛選擇器為 "
                "`{0}`，顯示名稱為 `{1}`。".format(
                    DEVELOP_PLUGIN_SELECTOR,
                    DEVELOP_DISPLAY_NAME,
                )
            ),
        ),
    )
    for relative_path, source_sentence, develop_sentence in readme_rewrites:
        path = staging_root / relative_path
        content = path.read_text(encoding="utf-8")
        if source_sentence not in content:
            raise PackagingError(
                "Cannot rewrite develop installation guidance: {0}".format(
                    relative_path
                )
            )
        updated = content.replace(source_sentence, develop_sentence)
        updated = updated.replace(
            "codex plugin marketplace add "
            "https://github.com/lihi-io/lihi-agent-plugin.git",
            "codex plugin marketplace add .",
        )
        updated = updated.replace(
            "claude plugin marketplace add "
            "https://github.com/lihi-io/lihi-agent-plugin.git",
            "claude plugin marketplace add .",
        )
        if relative_path == Path("README.md"):
            updated = updated.replace(
                "### Install directly from GitHub",
                "### Install from the extracted develop artifact\n\n"
                "Run these commands from the extracted artifact root:",
            )
            updated = updated.replace(
                "### Install after downloading to local disk",
                "### Install with an absolute local path",
            )
            updated = updated.replace(
                "1. Download the repository archive from GitHub and extract "
                "it. A local Git clone works as well.",
                "1. Extract the downloaded develop artifact.",
            )
            updated = updated.replace(
                "2. Locate the extracted repository root containing "
                "`.agents/plugins/marketplace.json` and "
                "`.claude-plugin/marketplace.json`.",
                "2. Locate the extracted artifact root containing "
                "`.agents/plugins/marketplace.json` and "
                "`.claude-plugin/marketplace.json`.",
            )
            updated = updated.replace(
                "3. Replace `/absolute/path/to/lihi-agent-plugin` below with "
                "that repository root.",
                "3. Replace `/absolute/path/to/lihi-agent-VERSION` below with "
                "that artifact root.",
            )
            updated = updated.replace(
                "/absolute/path/to/lihi-agent-plugin",
                "/absolute/path/to/lihi-agent-VERSION",
            )
            updated = updated.replace(
                "Do not pass the downloaded ZIP file itself to the marketplace "
                "command. Extract it first and use the absolute path to the "
                "extracted root.",
                "Do not pass the downloaded artifact ZIP file itself to the "
                "marketplace command. Extract it first and use the absolute "
                "path to the extracted artifact root.",
            )
        else:
            updated = updated.replace(
                "### 直接從 GitHub 安裝",
                "### 從解壓縮後的開發版成品安裝\n\n"
                "請在解壓縮後的成品根目錄執行以下指令：",
            )
            updated = updated.replace(
                "### 下載到本機後安裝",
                "### 使用本機絕對路徑安裝",
            )
            updated = updated.replace(
                "1. 從 GitHub 下載原始碼壓縮檔並解壓縮，也可以使用本機 "
                "Git 複本。",
                "1. 將下載的開發版成品解壓縮。",
            )
            updated = updated.replace(
                "2. 找到同時包含 `.agents/plugins/marketplace.json` 與 "
                "`.claude-plugin/marketplace.json` 的解壓縮根目錄。",
                "2. 找到同時包含 `.agents/plugins/marketplace.json` 與 "
                "`.claude-plugin/marketplace.json` 的成品解壓縮"
                "根目錄。",
            )
            updated = updated.replace(
                "/absolute/path/to/lihi-agent-plugin",
                "/absolute/path/to/lihi-agent-VERSION",
            )
            updated = updated.replace(
                "不要把下載的 ZIP 檔本身傳給市集指令。請先解壓縮，再使用"
                "解壓縮根目錄的絕對路徑。",
                "不要把下載的成品 ZIP 檔本身傳給市集指令。請先解壓縮，"
                "再使用成品解壓縮根目錄的絕對路徑。",
            )
        path.write_text(updated, encoding="utf-8")


def apply_develop_identities(staging_root: Path, version: str) -> None:
    rename_skill_directories(staging_root)
    rewrite_develop_text_identities(staging_root)
    rename_plugin_directories(staging_root)
    update_develop_marketplaces(staging_root)
    update_develop_plugin_manifests(staging_root, version)
    update_develop_mcp_identities(staging_root)
    rewrite_develop_readme(staging_root)


def write_build_metadata(
    staging_root: Path,
    version: str,
    commit: str,
) -> None:
    skill_names = [
        DEVELOP_SKILL_NAME,
        DEVELOP_ACCOUNT_SKILL_NAME,
        DEVELOP_SWITCH_GROUP_SKILL_NAME,
        DEVELOP_SWITCH_DOMAIN_SKILL_NAME,
    ]
    write_json(
        staging_root / "DEVELOP_BUILD.json",
        {
            "kind": "develop",
            "version": version,
            "commit": commit.lower(),
            "marketplace_name": DEVELOP_MARKETPLACE_NAME,
            "plugin_name": DEVELOP_PLUGIN_NAME,
            "plugin_selector": DEVELOP_PLUGIN_SELECTOR,
            "mcp_server_name": DEVELOP_MCP_NAME,
            "skill_name": DEVELOP_SKILL_NAME,
            "skill_names": skill_names,
            "plugins": [
                {
                    "plugin_name": DEVELOP_PLUGIN_NAME,
                    "plugin_selector": DEVELOP_PLUGIN_SELECTOR,
                    "mcp_server_name": DEVELOP_MCP_NAME,
                    "skill_name": DEVELOP_SKILL_NAME,
                    "skill_names": skill_names,
                }
            ],
            "mcp_endpoint": DEVELOP_ENDPOINT,
        },
    )


def validate_staged_package(staging_root: Path, version: str) -> None:
    for relative_path in DEVELOP_RUNTIME_ENDPOINT_FILES:
        content = (staging_root / relative_path).read_text(encoding="utf-8")
        if DEVELOP_ENDPOINT not in content or PRODUCTION_ENDPOINT in content:
            raise PackagingError(
                "Packaged runtime config does not contain only the develop "
                "endpoint: {0}".format(relative_path)
            )

    expected_sources = (
        "./plugins/codex/lihi-dev",
        "./plugins/claude/lihi-dev",
    )
    for index, relative_path in enumerate(MARKETPLACE_MANIFESTS):
        path = staging_root / relative_path
        marketplace = read_json(path)
        validate_marketplace_plugin_names(
            marketplace,
            path,
            (DEVELOP_PLUGIN_NAME,),
        )
        plugin = marketplace_plugin(
            marketplace,
            path,
            DEVELOP_PLUGIN_NAME,
        )
        if marketplace.get("name") != DEVELOP_MARKETPLACE_NAME:
            raise PackagingError(
                "Packaged marketplace has the wrong identity: {0}".format(
                    path
                )
            )
        if marketplace_source_path(plugin, codex=index == 0) != expected_sources[index]:
            raise PackagingError(
                "Packaged marketplace has the wrong source: {0}".format(path)
            )
        marketplace_interface = marketplace.get("interface")
        if index == 0 and isinstance(marketplace_interface, dict):
            marketplace_display_name = marketplace_interface.get("displayName")
        else:
            marketplace_display_name = plugin.get("displayName")
        if marketplace_display_name != DEVELOP_DISPLAY_NAME:
            raise PackagingError(
                "Packaged marketplace has the wrong display name: {0}".format(
                    path
                )
            )

    expected_manifest_versions = (
        codex_develop_version(version),
        version,
    )
    for index, relative_path in enumerate(DEVELOP_PLUGIN_MANIFESTS):
        path = staging_root / relative_path
        manifest = read_json(path)
        interface = manifest.get("interface")
        display_name = (
            interface.get("displayName")
            if index == 0 and isinstance(interface, dict)
            else manifest.get("displayName")
        )
        if (
            manifest.get("name") != DEVELOP_PLUGIN_NAME
            or manifest.get("version") != expected_manifest_versions[index]
            or display_name != DEVELOP_DISPLAY_NAME
        ):
            raise PackagingError(
                "Packaged plugin has the wrong identity or version: "
                "{0}".format(path)
            )

    for production_root, develop_root in PLUGIN_ROOT_PAIRS:
        if (staging_root / production_root).exists():
            raise PackagingError(
                "Production plugin root remains in develop package"
            )
        validate_mcp_server_name(
            staging_root / develop_root / ".mcp.json",
            DEVELOP_MCP_NAME,
        )

    for develop_path, (
        _production_name,
        develop_name,
    ) in zip(DEVELOP_SKILL_PATHS, SKILL_IDENTITIES * 2):
        path = staging_root / develop_path
        if not path.is_dir():
            raise PackagingError(
                "Packaged skill directory has the wrong identity: {0}".format(
                    path
                )
            )
        skill_content = (path / "SKILL.md").read_text(encoding="utf-8")
        if (
            "\nname: {0}\n".format(develop_name) not in skill_content
            or BRAND_RULE not in skill_content
        ):
            raise PackagingError(
                "Packaged skill has the wrong identity: {0}".format(path)
            )

    for skill_name, relative_path in (
        (
            DEVELOP_SKILL_NAME,
            Path(
                "plugins/codex/lihi-dev/skills/"
                "lihi-shorten-dev/agents/openai.yaml"
            ),
        ),
        (
            DEVELOP_ACCOUNT_SKILL_NAME,
            Path(
                "plugins/codex/lihi-dev/skills/"
                "lihi-account-dev/agents/openai.yaml"
            ),
        ),
        (
            DEVELOP_SWITCH_GROUP_SKILL_NAME,
            Path(
                "plugins/codex/lihi-dev/skills/"
                "lihi-switch-group-dev/agents/openai.yaml"
            ),
        ),
        (
            DEVELOP_SWITCH_DOMAIN_SKILL_NAME,
            Path(
                "plugins/codex/lihi-dev/skills/"
                "lihi-switch-domain-dev/agents/openai.yaml"
            ),
        ),
    ):
        openai_yaml = (staging_root / relative_path).read_text(encoding="utf-8")
        if (
            'value: "{0}"'.format(DEVELOP_MCP_NAME) not in openai_yaml
            or "${0}".format(skill_name) not in openai_yaml
        ):
            raise PackagingError(
                "Packaged Codex skill metadata has the wrong identity"
            )

    for relative_path in (Path("README.md"), Path("README.zh-TW.md")):
        root_readme = (staging_root / relative_path).read_text(
            encoding="utf-8"
        )
        if (
            DEVELOP_PLUGIN_SELECTOR not in root_readme
            or "codex plugin marketplace add ." not in root_readme
            or "claude plugin marketplace add ." not in root_readme
        ):
            raise PackagingError(
                "Packaged README does not contain develop installation "
                "guidance: {0}".format(relative_path)
            )

    for path in iter_text_files(staging_root):
        if path == staging_root / "DEVELOP_BUILD.json":
            continue
        content = path.read_text(encoding="utf-8")
        for match in BRAND_PATTERN.finditer(content):
            if match.group(0) != "lihi":
                raise PackagingError(
                    "Brand name must be lowercase in develop package: "
                    "{0}".format(path)
                )
        if PRODUCTION_ORIGIN in content:
            raise PackagingError(
                "Production lihi origin remains in develop package: "
                "{0}".format(path)
            )
        if PRODUCTION_PLUGIN_SELECTOR in content:
            raise PackagingError(
                "Production plugin selector remains in develop package: "
                "{0}".format(path)
            )
        for production_identity in (
            "`{0}`".format(PRODUCTION_SKILL_NAME),
            "`{0}`".format(PRODUCTION_ACCOUNT_SKILL_NAME),
            "`{0}`".format(PRODUCTION_SWITCH_GROUP_SKILL_NAME),
            "`{0}`".format(PRODUCTION_SWITCH_DOMAIN_SKILL_NAME),
            "remote `lihi` MCP server",
            "remote MCP server `lihi`",
        ):
            if production_identity in content:
                raise PackagingError(
                    "Production runtime identity remains in develop package: "
                    "{0}".format(path)
                )


def write_package_directory(
    staging_root: Path,
    output_dir: Path,
    version: str,
) -> Path:
    package_name = "lihi-agent-{0}".format(version)
    package_path = output_dir / package_name
    if package_path.exists():
        if not package_path.is_dir():
            raise PackagingError(
                "Package output is not a directory: {0}".format(package_path)
            )
        shutil.rmtree(str(package_path))
    shutil.copytree(str(staging_root), str(package_path))
    return package_path


def package_develop_bundle(
    repo_root: Path,
    output_dir: Path,
    build_number: str,
    commit: str,
) -> Tuple[Path, str]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    version = build_develop_version(repo_root, build_number)
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise PackagingError(
            "commit must be a 7-40 character hexadecimal Git SHA"
        )
    validate_source_bundle(repo_root)

    with tempfile.TemporaryDirectory(
        prefix="lihi-agent-develop-"
    ) as temporary_dir:
        staging_root = Path(temporary_dir) / "package"
        staging_root.mkdir()
        copy_distribution_files(repo_root, staging_root)
        rewrite_develop_origin(staging_root)
        apply_develop_identities(staging_root, version)
        write_build_metadata(
            staging_root,
            version,
            commit,
        )
        validate_staged_package(staging_root, version)
        package_path = write_package_directory(
            staging_root,
            output_dir,
            version,
        )

    return package_path, version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-number", required=True)
    parser.add_argument("--commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        package_path, version = package_develop_bundle(
            repo_root=repo_root,
            output_dir=args.output_dir,
            build_number=args.build_number,
            commit=args.commit,
        )
    except (OSError, PackagingError, ValueError) as exc:
        raise SystemExit("error: {0}".format(exc))

    print("Created: {0}".format(package_path))
    print("Version: {0}".format(version))
    print("Plugin: {0}".format(DEVELOP_PLUGIN_SELECTOR))
    print("MCP endpoint: {0}".format(DEVELOP_ENDPOINT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
