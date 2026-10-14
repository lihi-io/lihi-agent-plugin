#!/usr/bin/env python3
"""Build the portable lihi plugin ZIP and four individual skill ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, Mapping, Sequence, Set, Tuple


PLUGIN_NAME = "lihi"
PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
DEVELOP_ORIGIN = "https://app.lihidev.com"

CODEX_PLUGIN_ROOT = Path("plugins/codex/lihi")
CODEX_MANIFEST = CODEX_PLUGIN_ROOT / ".codex-plugin/plugin.json"
CLAUDE_MANIFEST = Path("plugins/claude/lihi/.claude-plugin/plugin.json")
SOURCE_MANIFESTS = (CODEX_MANIFEST, CLAUDE_MANIFEST)
SOURCE_SKILLS_ROOT = CODEX_PLUGIN_ROOT / "skills"
SOURCE_ASSETS_ROOT = Path("packaging/openai-platform/assets")
ASSET_FILES = ("composer-icon.png", "logo.png")
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
PLUGIN_DESCRIPTION = (
    "Access lihi account status, group and domain switching, and automatic "
    "URL shortening through one OAuth MCP connection."
)
PLUGIN_SHORT_DESCRIPTION = "Short URLs and account tools"
PLUGIN_SUPPORT_URL = "https://lihistatus.com/contact"

PROMOTIONAL_URLS = (
    "https://knowledge.lihi.io/pricing",
    "https://lihidomain.com/",
)

SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)
ARTIFACT_KEYS = (PLUGIN_NAME,) + SKILLS

SKILL_FILES = {
    "lihi-shorten": (
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("references/oauth-recovery.md"),
        Path("references/shortening-workflow.md"),
        Path("scripts/detect_urls.py"),
    ),
    "lihi-account": (
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("references/oauth-recovery.md"),
    ),
    "lihi-switch-group": (
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("references/error-recovery.md"),
        Path("references/oauth-recovery.md"),
    ),
    "lihi-switch-domain": (
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("references/error-recovery.md"),
        Path("references/oauth-recovery.md"),
    ),
}

NEUTRAL_INTERACTIVE_AUTH = (
    "Ask the current host to start its interactive OAuth flow for lihi. If "
    "the flow cannot start or complete, direct the user to the current "
    "host's connection settings and ask them to authenticate lihi once. Do "
    "not request credentials or run a different host's command."
)
HOST_NEUTRAL_REWRITES = {
    Path("skills/lihi-shorten/SKILL.md"): (
        ("while Codex adjusts", "while the assistant adjusts"),
        ("or before Codex sends", "or before the assistant sends"),
        (
            "The bundled `lihi` MCP client is eager, so the host may start "
            "OAuth",
            "The lihi MCP connection may start OAuth",
        ),
        ("introduced by Codex so far", "introduced by the assistant so far"),
        (
            "the Codex OAuth recovery rules",
            "the OpenAI host OAuth recovery rules",
        ),
    ),
    Path("skills/lihi-shorten/references/oauth-recovery.md"): (
        (
            "# Codex OAuth recovery for shortening",
            "# OpenAI host OAuth recovery for shortening",
        ),
        (
            "Let Codex manage OAuth.",
            "Let the current OpenAI host manage OAuth.",
        ),
        (
            "For initial authentication or qualifying reauthentication, "
            "explain that lihi access is opening. Run `codex mcp login lihi` "
            "once when shell execution is available. If it cannot start or "
            "complete, ask the user to run it and do not retry automatically; "
            "use **MCP settings → lihi → Authenticate** only when the command "
            "is unavailable.",
            "For initial authentication or qualifying reauthentication, "
            "explain that lihi access is required or needs restoration. "
            + NEUTRAL_INTERACTIVE_AUTH,
        ),
        (
            "lihi 驗證已失效，我現在為你開啟 OAuth 登入；"
            "目前尚未建立或發布任何連結。",
            "lihi 驗證已失效。請在目前應用程式完成 lihi OAuth 驗證；"
            "目前尚未建立或發布任何連結。",
        ),
    ),
    Path("skills/lihi-shorten/references/shortening-workflow.md"): (
        (
            "For an account quota failure, preserve the original URL, explain "
            "the account limit, provide `方案與額度說明：https://knowledge."
            "lihi.io/pricing`, and ask whether to retry after resolution, keep "
            "this URL unchanged for the current snapshot, or cancel. Treat "
            "that guidance URL as metadata and never scan or shorten it.",
            "For an account quota failure, preserve the original URL, explain "
            "the account limit, and ask whether to retry after resolution, "
            "keep this URL unchanged for the current snapshot, or cancel.",
        ),
    ),
    Path("skills/lihi-account/SKILL.md"): (
        (
            "the Codex OAuth recovery rules",
            "the OpenAI host OAuth recovery rules",
        ),
        (
            " When usage, plan, or renewal is shown, append "
            "`訂閱方案說明：https://knowledge.lihi.io/pricing`; omit it for "
            "email/group/domain-only answers.",
            "",
        ),
    ),
    Path("skills/lihi-account/references/oauth-recovery.md"): (
        ("# Codex OAuth recovery", "# OpenAI host OAuth recovery"),
        (
            "Let Codex manage OAuth.",
            "Let the current OpenAI host manage OAuth.",
        ),
        ("allow one Codex host-managed refresh", "allow one host-managed refresh"),
        (
            "For initial authentication or qualifying reauthentication, "
            "explain that lihi access is required or needs restoration. When "
            "shell execution is available, run `codex mcp login lihi` once. "
            "If it cannot start or complete, do not retry automatically; ask "
            "the user to run the same command in their terminal. Use **MCP "
            "settings → lihi → Authenticate** only when the command is "
            "unavailable.",
            "For initial authentication or qualifying reauthentication, "
            "explain that lihi access is required or needs restoration. "
            + NEUTRAL_INTERACTIVE_AUTH,
        ),
    ),
    Path("skills/lihi-switch-group/references/oauth-recovery.md"): (
        (
            "# Codex OAuth recovery for group switching",
            "# OpenAI host OAuth recovery for group switching",
        ),
        (
            "Let Codex manage OAuth and token storage.",
            "Let the current OpenAI host manage OAuth and token storage.",
        ),
        (
            "For initial authentication or qualifying reauthentication, run "
            "`codex mcp login lihi` once when shell execution is available. "
            "If it cannot start or complete, ask the user to run it; use "
            "**MCP settings → lihi → Authenticate** only when that command is "
            "unavailable.",
            "For initial authentication or qualifying reauthentication, "
            + NEUTRAL_INTERACTIVE_AUTH,
        ),
    ),
    Path("skills/lihi-switch-group/SKILL.md"): (
        (
            "Preserve `email` and every non-null display value exactly and append "
            "`訂閱方案說明：https://knowledge.lihi.io/pricing` because usage "
            "and plan are displayed.",
            "Preserve `email` and every non-null display value exactly.",
        ),
    ),
    Path("skills/lihi-switch-domain/references/oauth-recovery.md"): (
        (
            "# Codex OAuth recovery for domain switching",
            "# OpenAI host OAuth recovery for domain switching",
        ),
        (
            "Let Codex manage OAuth and token storage.",
            "Let the current OpenAI host manage OAuth and token storage.",
        ),
        (
            "For initial authentication or qualifying reauthentication, run "
            "`codex mcp login lihi` once when shell execution is available. "
            "If it cannot start or complete, ask the user to run it; use "
            "**MCP settings → lihi → Authenticate** only when that command is "
            "unavailable.",
            "For initial authentication or qualifying reauthentication, "
            + NEUTRAL_INTERACTIVE_AUTH,
        ),
    ),
    Path("skills/lihi-switch-domain/SKILL.md"): (
        (
            "\n專屬網域說明：https://lihidomain.com/",
            "",
        ),
        (
            ", and append `訂閱方案說明：https://knowledge.lihi.io/pricing` "
            "because usage and plan are displayed.",
            ".",
        ),
    ),
}

SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BRAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])lihi(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
DRIVE_PREFIX_PATTERN = re.compile(r"^[A-Za-z]:")
HOST_SPECIFIC_PATTERN = re.compile(r"\b(?:Codex|Claude)\b", re.IGNORECASE)

MAX_ARCHIVE_SIZE = 100 * 1000 * 1000
MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBER_SIZE = 100 * 1024 * 1024
MAX_ARCHIVE_PATH_SEGMENTS = 20
MAX_ARCHIVE_PATH_BYTES = 1024
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
DETECTOR_ARCHIVE_PATH = "skills/lihi-shorten/scripts/detect_urls.py"


class PackagingError(RuntimeError):
    """Raised when the source tree cannot produce a safe public package."""


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
    for relative_path in SOURCE_MANIFESTS:
        manifest_path = repo_root / relative_path
        manifest = read_json(manifest_path)
        manifest_version = manifest.get("version")
        version_core = semantic_version_core(manifest_version, manifest_path)
        if manifest_version != version_core:
            raise PackagingError(
                "Production manifests must use plain major.minor.patch "
                "versions without build metadata: {0}".format(manifest_path)
            )
        versions.add(version_core)
    if len(versions) != 1:
        raise PackagingError(
            "Codex and Claude manifests must share one major.minor.patch version"
        )
    return versions.pop()


def is_ignored_source_path(relative_path: Path) -> bool:
    return (
        "__pycache__" in relative_path.parts
        or relative_path.suffix in {".pyc", ".pyo"}
        or relative_path.name == ".DS_Store"
    )


def regular_files(root: Path) -> Set[Path]:
    files = set()
    try:
        candidates = sorted(root.rglob("*"))
    except OSError as exc:
        raise PackagingError("Cannot inspect directory {0}: {1}".format(root, exc))
    for path in candidates:
        relative_path = path.relative_to(root)
        if is_ignored_source_path(relative_path):
            continue
        if path.is_symlink():
            raise PackagingError("Symbolic links are not allowed: {0}".format(path))
        if path.is_dir():
            continue
        try:
            mode = path.stat().st_mode
        except OSError as exc:
            raise PackagingError("Cannot inspect path {0}: {1}".format(path, exc))
        if not stat.S_ISREG(mode):
            raise PackagingError("Only regular files are allowed: {0}".format(path))
        files.add(relative_path)
    return files


def expected_source_skill_files(skill_name: str) -> Set[Path]:
    return set(SKILL_FILES[skill_name])


def expected_archive_files() -> Set[str]:
    return {
        (Path("skills") / skill_name / relative_path).as_posix()
        for skill_name in SKILLS
        for relative_path in SKILL_FILES[skill_name]
    } | {"plugin.json", "mcp.json"} | {
        "assets/" + name for name in ASSET_FILES
    }


def expected_skill_archive_files(skill_name: str) -> Set[str]:
    return {
        (Path(skill_name) / relative_path).as_posix()
        for relative_path in SKILL_FILES[skill_name]
    }


def public_artifact_filenames(version: str) -> Dict[str, str]:
    return {
        key: "{0}-{1}.zip".format(key, version) for key in ARTIFACT_KEYS
    }


def validate_source_bundle(repo_root: Path) -> str:
    version = release_version(repo_root)
    for relative_path in SOURCE_MANIFESTS:
        path = repo_root / relative_path
        manifest = read_json(path)
        if manifest.get("name") != PLUGIN_NAME:
            raise PackagingError(
                "Source plugin identity must be production lihi: {0}".format(path)
            )

    mcp_path = repo_root / CODEX_PLUGIN_ROOT / ".mcp.json"
    mcp = read_json(mcp_path)
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict) or list(servers) != [PLUGIN_NAME]:
        raise PackagingError("Expected one production lihi MCP server in {0}".format(mcp_path))
    server = servers[PLUGIN_NAME]
    if server != {
        "type": "http", "url": PRODUCTION_ENDPOINT, "auth": "oauth"
    }:
        raise PackagingError(
            "Source MCP server must use production HTTPS and host-managed OAuth"
        )

    skills_root = repo_root / SOURCE_SKILLS_ROOT
    if not skills_root.is_dir() or skills_root.is_symlink():
        raise PackagingError("Missing regular source skills directory: {0}".format(skills_root))
    actual_skills = {
        path.name
        for path in skills_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    }
    if actual_skills != set(SKILLS):
        raise PackagingError(
            "Expected source skills {0!r}, got {1!r}".format(
                SKILLS, tuple(sorted(actual_skills))
            )
        )

    for skill_name in SKILLS:
        skill_root = skills_root / skill_name
        actual_files = regular_files(skill_root)
        expected_files = expected_source_skill_files(skill_name)
        if actual_files != expected_files:
            raise PackagingError(
                "Unexpected files in {0}: expected {1!r}, got {2!r}".format(
                    skill_root,
                    tuple(sorted(path.as_posix() for path in expected_files)),
                    tuple(sorted(path.as_posix() for path in actual_files)),
                )
            )
        metadata_path = skill_root / "agents/openai.yaml"
        metadata = read_utf8(metadata_path)
        validate_openai_agent_metadata(metadata, metadata_path, skill_name)
        if DEVELOP_ORIGIN in metadata or "lihi-dev" in metadata:
            raise PackagingError(
                "Source metadata must remain production-only: {0}".format(
                    metadata_path
                )
            )

    detector = skills_root / "lihi-shorten/scripts/detect_urls.py"
    if not detector.stat().st_mode & 0o111:
        raise PackagingError("Source detector must remain executable: {0}".format(detector))

    return version


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PackagingError("Cannot read UTF-8 file {0}: {1}".format(path, exc))


def parse_quoted_agent_value(line: str, prefix: str, path: Path) -> str:
    if not line.startswith(prefix):
        raise PackagingError(
            "Agent metadata must use the supported YAML structure: {0}".format(
                path
            )
        )
    encoded = line[len(prefix) :]
    try:
        value = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise PackagingError(
            "Agent metadata has an invalid quoted value in {0}: {1}".format(
                path,
                exc,
            )
        )
    if not isinstance(value, str) or not value or has_unsupported_control(value):
        raise PackagingError(
            "Agent metadata values must be non-empty one-line strings: {0}".format(
                path
            )
        )
    return value


def parse_openai_agent_metadata(content: str, path: Path) -> dict:
    lines = content.splitlines()
    if len(lines) != 11 or lines[0] != "interface:" or lines[4:6] != [
        "dependencies:",
        "  tools:",
    ]:
        raise PackagingError(
            "Agent metadata must use the supported YAML structure: {0}".format(
                path
            )
        )

    interface = {
        "display_name": parse_quoted_agent_value(
            lines[1], "  display_name: ", path
        ),
        "short_description": parse_quoted_agent_value(
            lines[2], "  short_description: ", path
        ),
        "default_prompt": parse_quoted_agent_value(
            lines[3], "  default_prompt: ", path
        ),
    }
    tool = {
        "type": parse_quoted_agent_value(lines[6], "    - type: ", path),
        "value": parse_quoted_agent_value(lines[7], "      value: ", path),
        "description": parse_quoted_agent_value(
            lines[8], "      description: ", path
        ),
        "transport": parse_quoted_agent_value(
            lines[9], "      transport: ", path
        ),
        "url": parse_quoted_agent_value(lines[10], "      url: ", path),
    }
    return {"interface": interface, "tool": tool}


def validate_openai_agent_metadata(
    content: str,
    path: Path,
    skill_name: str,
) -> None:
    metadata = parse_openai_agent_metadata(content, path)
    interface = metadata["interface"]
    if interface["display_name"] != skill_name:
        raise PackagingError(
            "Agent metadata display_name must match the skill directory: "
            "{0}".format(path)
        )
    if "$" + skill_name not in interface["default_prompt"]:
        raise PackagingError(
            "Agent metadata default_prompt must reference ${0}: {1}".format(
                skill_name,
                path,
            )
        )
    if len(interface["short_description"]) > 1024:
        raise PackagingError(
            "Agent metadata short_description exceeds 1024 characters: "
            "{0}".format(path)
        )

    tool = metadata["tool"]
    expected = {
        "type": "mcp",
        "value": PLUGIN_NAME,
        "transport": "streamable_http",
        "url": PRODUCTION_ENDPOINT,
    }
    for field, value in expected.items():
        if tool[field] != value:
            raise PackagingError(
                "Production MCP dependency has invalid {0} in {1}".format(
                    field,
                    path,
                )
            )


def copy_regular_file(source: Path, target: Path, executable: bool = False) -> None:
    if source.is_symlink() or not source.is_file():
        raise PackagingError("Required regular file is missing: {0}".format(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(str(source), str(target))
        target.chmod(0o755 if executable else 0o644)
    except OSError as exc:
        raise PackagingError(
            "Cannot copy package file {0} to {1}: {2}".format(source, target, exc)
        )


def apply_host_neutral_rewrites(staging_root: Path) -> None:
    for relative_path, rewrites in HOST_NEUTRAL_REWRITES.items():
        path = staging_root / relative_path
        content = read_utf8(path)
        for old_value, new_value in rewrites:
            occurrences = content.count(old_value)
            if occurrences != 1:
                raise PackagingError(
                    "Host-neutral source fragment must appear exactly once in "
                    "{0}; found {1}: {2!r}".format(
                        relative_path,
                        occurrences,
                        old_value,
                    )
                )
            content = content.replace(old_value, new_value, 1)
        try:
            path.write_text(content, encoding="utf-8")
            path.chmod(0o644)
        except OSError as exc:
            raise PackagingError(
                "Cannot write host-neutral staged file {0}: {1}".format(
                    path, exc
                )
            )


def parse_skill_frontmatter(content: str, path: Path) -> Dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise PackagingError("Skill frontmatter is missing: {0}".format(path))
    try:
        closing = lines.index("---", 1)
    except ValueError:
        raise PackagingError("Skill frontmatter is unclosed: {0}".format(path))
    if not "\n".join(lines[closing + 1 :]).strip():
        raise PackagingError("Skill body is empty: {0}".format(path))
    values = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*): (.+)", line)
        if match is None:
            raise PackagingError(
                "Skill frontmatter must use single-line plain scalars: {0}".format(path)
            )
        key, value = match.groups()
        if key in values:
            raise PackagingError("Duplicate skill frontmatter key in {0}".format(path))
        values[key] = value
    if set(values) != {"name", "description"}:
        raise PackagingError(
            "Skill frontmatter must contain only name and description: {0}".format(path)
        )
    return values


def has_unsupported_control(value: str, allow_newline: bool = False) -> bool:
    for character in value:
        if character == "\n" and allow_newline:
            continue
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Zl", "Zp"}:
            return True
    return False


def validate_brand_casing(content: str, path: Path) -> None:
    for match in BRAND_PATTERN.finditer(content):
        if match.group(0) != "lihi":
            raise PackagingError(
                "Brand must be lowercase lihi in {0}".format(path)
            )


def validate_staging(repo_root: Path, staging_root: Path, version: str) -> None:
    actual_files = {path.as_posix() for path in regular_files(staging_root)}
    expected_files = expected_archive_files()
    if actual_files != expected_files:
        raise PackagingError(
            "Staged plugin files differ from the allowlist: expected {0!r}, got {1!r}".format(
                tuple(sorted(expected_files)), tuple(sorted(actual_files))
            )
        )

    validate_plugin_metadata(staging_root, version)
    identities = set()
    for skill_name in SKILLS:
        skill_root = staging_root / "skills" / skill_name
        skill_path = skill_root / "SKILL.md"
        content = read_utf8(skill_path)
        frontmatter = parse_skill_frontmatter(content, skill_path)
        if frontmatter["name"] != skill_name:
            raise PackagingError(
                "Skill name must match its directory: {0}".format(skill_path)
            )
        if not SKILL_NAME_PATTERN.fullmatch(skill_name):
            raise PackagingError("Unsupported skill name: {0}".format(skill_name))
        if len(frontmatter["description"]) > 1024:
            raise PackagingError("Skill description exceeds 1024 characters: {0}".format(skill_path))
        identity = PLUGIN_NAME + ":" + skill_name
        if len(identity) > 64 or identity in identities:
            raise PackagingError("Invalid or duplicate skill identity: {0}".format(identity))
        identities.add(identity)

        metadata_path = skill_root / "agents/openai.yaml"
        metadata = read_utf8(metadata_path)
        validate_openai_agent_metadata(metadata, metadata_path, skill_name)

    detector_source = repo_root / SOURCE_SKILLS_ROOT / "lihi-shorten/scripts/detect_urls.py"
    detector_staged = staging_root / "skills/lihi-shorten/scripts/detect_urls.py"
    read_utf8(detector_staged)
    if detector_source.read_bytes() != detector_staged.read_bytes():
        raise PackagingError("Packaged detector must be byte-identical to production")
    if not detector_staged.stat().st_mode & 0o111:
        raise PackagingError("Packaged detector must remain executable")

    for path in sorted(staging_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".yaml", ".yml"}:
            continue
        content = read_utf8(path)
        validate_brand_casing(content, path)
        if DEVELOP_ORIGIN in content or "lihi-dev" in content:
            raise PackagingError("Develop identity found in OpenAI package: {0}".format(path))
        for promotional_url in PROMOTIONAL_URLS:
            if promotional_url in content:
                raise PackagingError(
                    "Promotional URL found in OpenAI package: {0}: {1}".format(
                        path, promotional_url
                    )
                )
        if HOST_SPECIFIC_PATTERN.search(content):
            raise PackagingError("Host-specific wording found in OpenAI package: {0}".format(path))
        lowered = content.lower()
        if "codex mcp login" in lowered or "mcp settings" in lowered or "open `/mcp`" in lowered:
            raise PackagingError("Host-specific OAuth action found in OpenAI package: {0}".format(path))


def portable_manifest(repo_root: Path, version: str) -> dict:
    """Adapt approved production metadata without copying host configuration."""
    source = read_json(repo_root / CODEX_MANIFEST)
    manifest = {
        "$schema": PLUGIN_SCHEMA,
        "name": PLUGIN_NAME,
        "version": version,
        "description": PLUGIN_DESCRIPTION,
    }
    for key in ("author", "homepage", "repository", "license", "keywords"):
        if key in source:
            manifest[key] = source[key]
    interface = source.get("interface")
    if not isinstance(interface, dict):
        raise PackagingError("Source plugin interface must be an object")
    interface = dict(interface)
    interface.update({
        "shortDescription": PLUGIN_SHORT_DESCRIPTION,
        "supportURL": PLUGIN_SUPPORT_URL,
        "composerIcon": "./assets/composer-icon.png",
        "logo": "./assets/logo.png",
    })
    manifest["extensions"] = {"com.openai": {"interface": interface}}
    return manifest


def portable_mcp_config() -> dict:
    """Use portable transport and OAuth discovery; never package credentials."""
    return {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            PLUGIN_NAME: {
                "type": "streamable-http",
                "url": PRODUCTION_ENDPOINT,
                "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
            }
        },
    }


def write_json(path: Path, value: dict) -> None:
    try:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o644)
    except OSError as exc:
        raise PackagingError("Cannot write package metadata {0}: {1}".format(path, exc))


def validate_plugin_metadata(staging_root: Path, version: str) -> None:
    manifest_path = staging_root / "plugin.json"
    manifest = read_json(manifest_path)
    allowed_fields = {
        "$schema", "name", "version", "description", "author", "homepage",
        "repository", "license", "keywords", "extensions",
    }
    if (
        set(manifest) - allowed_fields
        or manifest.get("$schema") != PLUGIN_SCHEMA
        or manifest.get("name") != PLUGIN_NAME
        or manifest.get("version") != version
        or manifest.get("description") != PLUGIN_DESCRIPTION
    ):
        raise PackagingError("Invalid portable plugin manifest")
    extension = manifest.get("extensions", {}).get("com.openai", {})
    if set(extension) != {"interface"}:
        raise PackagingError("Public package must not declare app mappings or hooks")
    interface = extension["interface"]
    if interface.get("supportURL") != PLUGIN_SUPPORT_URL:
        raise PackagingError("Missing or invalid official support URL")
    for field, limit in (
        ("displayName", 30), ("shortDescription", 30),
        ("longDescription", 4000), ("developerName", 80), ("category", 80),
    ):
        value = interface.get(field)
        if (
            not isinstance(value, str) or not value.strip() or len(value) > limit
            or has_unsupported_control(value, allow_newline=field == "longDescription")
        ):
            raise PackagingError("Invalid plugin interface field: {0}".format(field))
    for field, filename in (("composerIcon", "composer-icon.png"), ("logo", "logo.png")):
        if interface.get(field) != "./assets/" + filename:
            raise PackagingError("Invalid packaged asset path: {0}".format(field))
        path = staging_root / "assets" / filename
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise PackagingError("Required asset is not a PNG: {0}".format(path))
    if read_json(staging_root / "mcp.json") != portable_mcp_config():
        raise PackagingError("Invalid portable production MCP configuration")


def prepare_staging(
    repo_root: Path,
    staging_root: Path,
    version: str,
) -> None:
    for skill_name in SKILLS:
        for relative_path in SKILL_FILES[skill_name]:
            source = repo_root / SOURCE_SKILLS_ROOT / skill_name / relative_path
            target = staging_root / "skills" / skill_name / relative_path
            copy_regular_file(
                source,
                target,
                executable=(
                    skill_name == "lihi-shorten"
                    and relative_path == Path("scripts/detect_urls.py")
                ),
            )

    apply_host_neutral_rewrites(staging_root)
    for filename in ASSET_FILES:
        copy_regular_file(
            repo_root / SOURCE_ASSETS_ROOT / filename,
            staging_root / "assets" / filename,
        )
    write_json(
        staging_root / "plugin.json", portable_manifest(repo_root, version)
    )
    write_json(staging_root / "mcp.json", portable_mcp_config())


def validate_archive_member_name(name: str) -> str:
    if not name or name != name.strip():
        raise PackagingError("Archive member path is empty or has outer whitespace")
    if "\\" in name or name.startswith("/") or DRIVE_PREFIX_PATTERN.match(name):
        raise PackagingError("Archive member path is absolute or uses a backslash: {0}".format(name))
    segments = name.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise PackagingError("Archive member path has an unsafe segment: {0}".format(name))
    if any(segment != segment.strip() for segment in segments):
        raise PackagingError("Archive member path has whitespace: {0}".format(name))
    if len(segments) > MAX_ARCHIVE_PATH_SEGMENTS:
        raise PackagingError("Archive member path is too deep: {0}".format(name))
    if len(name.encode("utf-8")) > MAX_ARCHIVE_PATH_BYTES:
        raise PackagingError("Archive member path is too long: {0}".format(name))
    path = PurePosixPath(name)
    if path.is_absolute():
        raise PackagingError("Archive member path must be relative: {0}".format(name))
    return unicodedata.normalize("NFKC", name).casefold()


def write_deterministic_zip(
    staging_root: Path, output_path: Path, archive_prefix: str = ""
) -> None:
    """Archive validated files, optionally under a named skill directory."""
    paths = sorted(regular_files(staging_root), key=lambda path: path.as_posix())
    try:
        with zipfile.ZipFile(
            str(output_path),
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for relative_path in paths:
                path = staging_root / relative_path
                name = (Path(archive_prefix) / relative_path).as_posix()
                validate_archive_member_name(name)
                permissions = 0o755 if name in {
                    DETECTOR_ARCHIVE_PATH,
                    "lihi-shorten/scripts/detect_urls.py",
                } else 0o644
                info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | permissions) << 16
                info.flag_bits |= 0x800
                archive.writestr(
                    info,
                    path.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackagingError("Cannot write ZIP archive {0}: {1}".format(output_path, exc))


def validate_archive(path: Path, expected_names: Set[str]) -> None:
    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise PackagingError("Cannot inspect ZIP archive {0}: {1}".format(path, exc))
    if archive_size > MAX_ARCHIVE_SIZE:
        raise PackagingError("ZIP archive exceeds 100 MiB: {0}".format(path))
    try:
        with zipfile.ZipFile(str(path), "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
                raise PackagingError("ZIP archive has an invalid entry count")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise PackagingError("ZIP archive contains duplicate member paths")
            normalized = [validate_archive_member_name(name) for name in names]
            if len(normalized) != len(set(normalized)):
                raise PackagingError("ZIP archive contains normalized path collisions")
            if set(names) != expected_names:
                raise PackagingError(
                    "ZIP archive differs from the package allowlist: expected {0!r}, got {1!r}".format(
                        tuple(sorted(expected_names)), tuple(sorted(names))
                    )
                )

            names_set = set(names)
            for name in names:
                parts = name.split("/")
                for index in range(1, len(parts)):
                    if "/".join(parts[:index]) in names_set:
                        raise PackagingError("ZIP archive has a path type conflict: {0}".format(name))

            total_size = 0
            for info in infos:
                mode = info.external_attr >> 16
                if info.is_dir() or stat.S_IFMT(mode) != stat.S_IFREG:
                    raise PackagingError("ZIP member is not a regular file: {0}".format(info.filename))
                if info.flag_bits & 0x1:
                    raise PackagingError("ZIP member must not be encrypted: {0}".format(info.filename))
                if info.compress_type != zipfile.ZIP_DEFLATED:
                    raise PackagingError("ZIP member uses unsupported compression: {0}".format(info.filename))
                if info.file_size > MAX_ARCHIVE_MEMBER_SIZE:
                    raise PackagingError("ZIP member exceeds 100 MiB: {0}".format(info.filename))
                total_size += info.file_size
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                raise PackagingError("ZIP archive exceeds 512 MiB when extracted")
            corrupted = archive.testzip()
            if corrupted is not None:
                raise PackagingError("ZIP member cannot be read: {0}".format(corrupted))

            for detector_name in (
                DETECTOR_ARCHIVE_PATH, "lihi-shorten/scripts/detect_urls.py"
            ):
                if detector_name not in expected_names:
                    continue
                detector = archive.getinfo(detector_name)
                if not (detector.external_attr >> 16) & 0o111:
                    raise PackagingError(
                        "Detector executable bit was not preserved in ZIP"
                    )
    except zipfile.BadZipFile as exc:
        raise PackagingError("ZIP archive is invalid: {0}: {1}".format(path, exc))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PackagingError("Cannot hash {0}: {1}".format(path, exc))
    return digest.hexdigest()


def remove_public_backup_directory(
    backup_dir: Path,
    backups: Mapping[str, Path],
) -> None:
    try:
        for backup in backups.values():
            if backup.is_symlink() or backup.exists():
                backup.unlink()
        backup_dir.rmdir()
    except OSError as exc:
        raise PackagingError(
            "Cannot remove OpenAI Platform ZIP backup directory {0}: {1}".format(
                backup_dir,
                exc,
            )
        )


def publish_public_zip_artifacts(
    output_dir: Path,
    temporary_zips: Mapping[str, Path],
    artifact_names: Mapping[str, str],
) -> None:
    artifact_keys = ARTIFACT_KEYS
    if set(temporary_zips) != set(artifact_keys) or set(artifact_names) != set(
        artifact_keys
    ):
        raise PackagingError("Public ZIP artifact set is incomplete")

    targets = {
        artifact_key: output_dir / artifact_names[artifact_key]
        for artifact_key in artifact_keys
    }
    for target in targets.values():
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise PackagingError(
                "Public ZIP output is not a regular file: {0}".format(target)
            )

    try:
        backup_dir = Path(
            tempfile.mkdtemp(
                prefix=".lihi-openai-platform-backup-",
                dir=str(output_dir),
            )
        )
    except OSError as exc:
        raise PackagingError(
            "Cannot create OpenAI Platform ZIP backup directory: {0}".format(
                exc
            )
        )

    backups = {}
    try:
        for artifact_key in artifact_keys:
            target = targets[artifact_key]
            if not target.exists():
                continue
            backup = backup_dir / artifact_names[artifact_key]
            backups[artifact_key] = backup
            shutil.copy2(str(target), str(backup))
    except OSError as exc:
        try:
            remove_public_backup_directory(backup_dir, backups)
        except PackagingError as cleanup_exc:
            raise PackagingError(
                "Cannot back up public ZIP artifacts: {0}; {1}".format(
                    exc,
                    cleanup_exc,
                )
            )
        raise PackagingError("Cannot back up public ZIP artifacts: {0}".format(exc))

    published = []
    try:
        for artifact_key in artifact_keys:
            os.replace(
                str(temporary_zips[artifact_key]),
                str(targets[artifact_key]),
            )
            published.append(artifact_key)
    except OSError as publish_exc:
        rollback_errors = []
        for artifact_key in reversed(published):
            target = targets[artifact_key]
            backup = backups.get(artifact_key)
            try:
                if backup is not None:
                    os.replace(str(backup), str(target))
                    del backups[artifact_key]
                elif target.is_symlink() or target.exists():
                    target.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(
                    "{0}: {1}".format(target, rollback_exc)
                )

        if rollback_errors:
            raise PackagingError(
                "Cannot publish OpenAI Platform ZIP artifacts: {0}; rollback "
                "was incomplete ({1}). Preserved backups at {2}".format(
                    publish_exc,
                    "; ".join(rollback_errors),
                    backup_dir,
                )
            )

        remove_public_backup_directory(backup_dir, backups)
        raise PackagingError(
            "Cannot publish OpenAI Platform ZIP artifacts; restored the previous "
            "artifact set: {0}".format(publish_exc)
        )

    remove_public_backup_directory(backup_dir, backups)


def build_bundle(
    repo_root: Path, output_dir: Path
) -> Tuple[Dict[str, Path], str, Dict[str, str]]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    version = validate_source_bundle(repo_root)
    artifact_names = public_artifact_filenames(version)

    with tempfile.TemporaryDirectory(prefix="lihi-openai-platform-") as temporary:
        staging_root = Path(temporary)
        prepare_staging(repo_root, staging_root, version)
        validate_staging(repo_root, staging_root, version)
        temporary_zips = {}
        digests = {}
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            for key in ARTIFACT_KEYS:
                with tempfile.NamedTemporaryFile(
                    prefix=".{0}-".format(key), suffix=".tmp",
                    dir=str(output_dir), delete=False,
                ) as stream:
                    temporary_zip = Path(stream.name)
                temporary_zips[key] = temporary_zip
                if key == PLUGIN_NAME:
                    archive_root = staging_root
                    archive_prefix = ""
                    expected_names = expected_archive_files()
                else:
                    archive_root = staging_root / "skills" / key
                    archive_prefix = key
                    expected_names = expected_skill_archive_files(key)
                write_deterministic_zip(archive_root, temporary_zip, archive_prefix)
                validate_archive(temporary_zip, expected_names)
                temporary_zip.chmod(0o644)
                digests[key] = sha256_file(temporary_zip)

            publish_public_zip_artifacts(output_dir, temporary_zips, artifact_names)
        except OSError as exc:
            raise PackagingError(
                "Cannot publish OpenAI Platform ZIP artifacts: {0}".format(exc)
            )
        finally:
            for temporary_zip in temporary_zips.values():
                try:
                    temporary_zip.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise PackagingError(
                        "Cannot remove temporary ZIP {0}: {1}".format(temporary_zip, exc)
                    )

    targets = {key: output_dir / artifact_names[key] for key in ARTIFACT_KEYS}
    return targets, version, digests


def parse_args(argv: Sequence[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the portable lihi plugin ZIP and four individual skill ZIPs."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory that will receive the versioned artifact.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        targets, version, digests = build_bundle(repo_root, args.output_dir)
    except PackagingError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1
    print("Built OpenAI Platform plugin bundle: {0}".format(targets[PLUGIN_NAME]))
    for key in ARTIFACT_KEYS:
        if key != PLUGIN_NAME:
            print("Built OpenAI skill bundle {0}: {1}".format(key, targets[key]))
        print("SHA-256 ({0}): {1}".format(key, digests[key]))
    print("Version: {0}".format(version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
