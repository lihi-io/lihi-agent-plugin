#!/usr/bin/env python3
"""Build public lihi OpenAI Platform plugin and skill ZIPs without changing sources."""

from __future__ import annotations

import argparse
import binascii
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Dict, Mapping, Sequence, Set, Tuple
from urllib.parse import urlsplit


PLUGIN_NAME = "lihi"
PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
DEVELOP_ORIGIN = "https://app.lihidev.com"
DEVELOPER_MARKETPLACE_NAME = "lihi-openai-developer"
DEVELOPER_MARKETPLACE_DISPLAY_NAME = "lihi OpenAI Developer"
DEVELOPER_BUNDLE_PREFIX = "lihi-openai-developer-"
PLATFORM_BUNDLE_PREFIX = "lihi-openai-platform-"

CODEX_PLUGIN_ROOT = Path("plugins/codex/lihi")
CODEX_MANIFEST = CODEX_PLUGIN_ROOT / ".codex-plugin/plugin.json"
CLAUDE_MANIFEST = Path("plugins/claude/lihi/.claude-plugin/plugin.json")
SOURCE_MANIFESTS = (CODEX_MANIFEST, CLAUDE_MANIFEST)
SOURCE_SKILLS_ROOT = CODEX_PLUGIN_ROOT / "skills"

PLATFORM_ROOT = Path("packaging/openai-platform")
PLATFORM_ASSETS_ROOT = PLATFORM_ROOT / "assets"
LOGO_SOURCE = PLATFORM_ASSETS_ROOT / "logo.png"
COMPOSER_ICON_SOURCE = PLATFORM_ASSETS_ROOT / "composer-icon.png"
LOGO_DIMENSION = 256
COMPOSER_ICON_DIMENSION = 48
SOURCE_ASSET_DIMENSIONS = {
    LOGO_SOURCE: LOGO_DIMENSION,
    COMPOSER_ICON_SOURCE: COMPOSER_ICON_DIMENSION,
}
PACKAGE_ASSET_DIMENSIONS = {
    Path("assets/logo.png"): LOGO_DIMENSION,
    Path("assets/composer-icon.png"): COMPOSER_ICON_DIMENSION,
}

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
            "group/domain-only answers.",
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
            "Preserve every non-null display value exactly and append "
            "`訂閱方案說明：https://knowledge.lihi.io/pricing` because usage "
            "and plan are displayed.",
            "Preserve every non-null display value exactly.",
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

PUBLIC_DESCRIPTION = (
    "Connect to lihi through one OAuth MCP integration for account status, "
    "group and domain switching, and automatic URL shortening."
)
PUBLIC_INTERFACE = {
    "displayName": "lihi",
    "shortDescription": "lihi account and short URLs",
    "longDescription": (
        "Connects once to the lihi OAuth MCP server for account status, group "
        "and domain switching, and automatic URL shortening while revising "
        "or preparing human-facing content."
    ),
    "developerName": "lihi",
    "category": "Productivity",
    "capabilities": ["Interactive", "Write"],
    "websiteURL": "https://lihi.io/",
    "supportURL": "https://lihistatus.com/contact",
    "privacyPolicyURL": "https://knowledge.lihi.io/privacy-policy/",
    "termsOfServiceURL": "https://knowledge.lihi.io/terms-of-use/",
    "defaultPrompt": [
        "Show my lihi account information",
        "View or switch my lihi work group or short URL domain",
        "Polish copy and automatically shorten detected new URLs",
    ],
    "logo": "./assets/logo.png",
    "composerIcon": "./assets/composer-icon.png",
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
DEVELOPER_APP_ID_PATTERN = re.compile(
    r"^plugin_asdk_app_[A-Za-z0-9][A-Za-z0-9_-]*$"
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_SAMPLES_PER_PIXEL = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}
ADAM7_PASSES = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)

MAX_ARCHIVE_SIZE = 100 * 1000 * 1000
MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBER_SIZE = 100 * 1024 * 1024
MAX_ARCHIVE_PATH_SEGMENTS = 20
MAX_ARCHIVE_PATH_BYTES = 1024
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MIN_IMAGE_DIMENSION = 48
MAX_IMAGE_DIMENSION = 4096
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

CATEGORY_VALUES = {
    "Productivity",
    "Creativity",
    "Developer Tools",
    "Business & Operations",
    "Data & Analytics",
    "Communication",
    "Education & Research",
    "Security",
    "Finance",
    "Healthcare",
    "Travel",
    "Entertainment",
    "Other",
}


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


def write_json(path: Path, value: Mapping[str, object]) -> None:
    try:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise PackagingError("Cannot write JSON file {0}: {1}".format(path, exc))


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
        versions.add(
            semantic_version_core(manifest.get("version"), manifest_path)
        )
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


def expected_package_files(include_app: bool = False) -> Set[str]:
    names = {
        ".codex-plugin/plugin.json",
        "assets/logo.png",
        "assets/composer-icon.png",
    }
    if include_app:
        names.add(".app.json")
    for skill_name in SKILLS:
        for relative_path in SKILL_FILES[skill_name]:
            names.add(
                (Path("skills") / skill_name / relative_path).as_posix()
            )
    return names


def expected_skill_archive_files(skill_name: str) -> Set[str]:
    if skill_name not in SKILL_FILES:
        raise PackagingError("Unknown skill archive: {0}".format(skill_name))
    return {
        (Path(skill_name) / relative_path).as_posix()
        for relative_path in SKILL_FILES[skill_name]
    }


def public_artifact_filenames(version: str) -> Dict[str, str]:
    names = {
        "plugin": "{0}{1}.zip".format(PLATFORM_BUNDLE_PREFIX, version),
    }
    for skill_name in SKILLS:
        names[skill_name] = "{0}-{1}.zip".format(skill_name, version)
    return names


def expected_developer_bundle_files() -> Set[str]:
    names = {".agents/plugins/marketplace.json"}
    names.update(
        "plugins/{0}/{1}".format(PLUGIN_NAME, name)
        for name in expected_package_files(include_app=True)
    )
    return names


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
    if not isinstance(server, dict) or server.get("url") != PRODUCTION_ENDPOINT:
        raise PackagingError("Source MCP server must use {0}".format(PRODUCTION_ENDPOINT))

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


def build_public_manifest(repo_root: Path, version: str) -> dict:
    source = read_json(repo_root / CODEX_MANIFEST)
    author = source.get("author")
    keywords = source.get("keywords")
    if not isinstance(author, dict) or author.get("name") != "lihi":
        raise PackagingError("Codex source manifest has invalid lihi author metadata")
    if not isinstance(keywords, list) or any(
        not isinstance(item, str) or not item for item in keywords
    ):
        raise PackagingError("Codex source manifest has invalid keywords")
    return {
        "name": PLUGIN_NAME,
        "version": version,
        "description": PUBLIC_DESCRIPTION,
        "author": copy.deepcopy(author),
        "homepage": "https://lihi.io/",
        "keywords": list(keywords),
        "skills": "./skills/",
        "interface": copy.deepcopy(PUBLIC_INTERFACE),
    }


def validate_developer_app_id(app_id: object) -> str:
    if (
        not isinstance(app_id, str)
        or len(app_id) > 256
        or DEVELOPER_APP_ID_PATTERN.fullmatch(app_id) is None
    ):
        raise PackagingError(
            "app-id must start with plugin_asdk_app_ and contain only letters, "
            "digits, underscores, or hyphens"
        )
    return app_id


def build_developer_app_manifest(app_id: str) -> dict:
    return {
        "apps": {
            PLUGIN_NAME: {
                "id": validate_developer_app_id(app_id),
            }
        }
    }


def build_developer_marketplace() -> dict:
    return {
        "name": DEVELOPER_MARKETPLACE_NAME,
        "interface": {
            "displayName": DEVELOPER_MARKETPLACE_DISPLAY_NAME,
        },
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": "./plugins/{0}".format(PLUGIN_NAME),
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }


def expected_png_data_size(
    width: int,
    height: int,
    color_type: int,
    bit_depth: int,
    interlace: int,
) -> int:
    bits_per_pixel = PNG_SAMPLES_PER_PIXEL[color_type] * bit_depth

    def pass_size(pass_width: int, pass_height: int) -> int:
        if pass_width <= 0 or pass_height <= 0:
            return 0
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        return pass_height * (row_bytes + 1)

    if interlace == 0:
        return pass_size(width, height)

    total = 0
    for x_start, y_start, x_step, y_step in ADAM7_PASSES:
        pass_width = (
            (width - x_start + x_step - 1) // x_step
            if width > x_start
            else 0
        )
        pass_height = (
            (height - y_start + y_step - 1) // y_step
            if height > y_start
            else 0
        )
        total += pass_size(pass_width, pass_height)
    return total


def validate_png(path: Path) -> Tuple[int, int]:
    if path.is_symlink() or not path.is_file():
        raise PackagingError("Required PNG asset is missing: {0}".format(path))
    try:
        size = path.stat().st_size
        data = path.read_bytes()
    except OSError as exc:
        raise PackagingError("Cannot read PNG asset {0}: {1}".format(path, exc))
    if size > MAX_IMAGE_SIZE:
        raise PackagingError("PNG asset exceeds 5 MiB: {0}".format(path))
    if not data.startswith(PNG_SIGNATURE):
        raise PackagingError("PNG signature is invalid: {0}".format(path))

    offset = len(PNG_SIGNATURE)
    ihdr = None
    idat_parts = []
    seen_idat = False
    idat_ended = False
    seen_iend = False
    chunk_index = 0
    while offset < len(data):
        if len(data) - offset < 12:
            raise PackagingError("PNG chunk is truncated: {0}".format(path))
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise PackagingError("PNG chunk is truncated: {0}".format(path))
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise PackagingError("PNG chunk CRC is invalid: {0}".format(path))
        if not re.fullmatch(rb"[A-Za-z]{4}", chunk_type):
            raise PackagingError("PNG chunk type is invalid: {0}".format(path))

        if chunk_index == 0 and chunk_type != b"IHDR":
            raise PackagingError("PNG IHDR must be the first chunk: {0}".format(path))
        if chunk_type == b"IHDR":
            if ihdr is not None or length != 13:
                raise PackagingError("PNG IHDR is invalid: {0}".format(path))
            ihdr = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            if ihdr is None or idat_ended:
                raise PackagingError("PNG IDAT sequence is invalid: {0}".format(path))
            seen_idat = True
            idat_parts.append(chunk_data)
        else:
            if seen_idat and chunk_type != b"IEND":
                idat_ended = True
        if chunk_type == b"IEND":
            if length != 0 or seen_iend:
                raise PackagingError("PNG IEND is invalid: {0}".format(path))
            seen_iend = True
            offset = chunk_end
            if offset != len(data):
                raise PackagingError("PNG has data after IEND: {0}".format(path))
            break
        offset = chunk_end
        chunk_index += 1

    if ihdr is None or not seen_idat or not seen_iend:
        raise PackagingError("PNG is missing required chunks: {0}".format(path))
    width, height, bit_depth, color_type, compression, filtering, interlace = ihdr
    if color_type not in PNG_BIT_DEPTHS or bit_depth not in PNG_BIT_DEPTHS[color_type]:
        raise PackagingError("PNG color type or bit depth is invalid: {0}".format(path))
    if compression != 0 or filtering != 0 or interlace not in {0, 1}:
        raise PackagingError("PNG encoding method is unsupported: {0}".format(path))
    if width != height:
        raise PackagingError("PNG asset must be square: {0}".format(path))
    if width < MIN_IMAGE_DIMENSION or width > MAX_IMAGE_DIMENSION:
        raise PackagingError(
            "PNG dimensions must be between 48 and 4096 pixels: {0}".format(path)
        )

    expected_size = expected_png_data_size(
        width, height, color_type, bit_depth, interlace
    )
    compressed = b"".join(idat_parts)
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(compressed, expected_size + 1)
        if decoder.unconsumed_tail or len(decoded) > expected_size:
            raise PackagingError("PNG decoded data is too large: {0}".format(path))
        decoded += decoder.flush()
    except zlib.error as exc:
        raise PackagingError("PNG image data cannot be decoded: {0}: {1}".format(path, exc))
    if not decoder.eof or decoder.unused_data or len(decoded) != expected_size:
        raise PackagingError("PNG decoded data size is invalid: {0}".format(path))
    return width, height


def validate_png_dimension(path: Path, expected_dimension: int) -> None:
    width, height = validate_png(path)
    if (width, height) != (expected_dimension, expected_dimension):
        raise PackagingError(
            "PNG asset must be exactly {0}x{0} pixels: {1}".format(
                expected_dimension, path
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


def require_text(
    value: object,
    field: str,
    maximum: int,
    one_line: bool = True,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackagingError("{0} must be a non-empty string".format(field))
    if len(value) > maximum:
        raise PackagingError("{0} exceeds {1} characters".format(field, maximum))
    if one_line and ("\n" in value or "\r" in value):
        raise PackagingError("{0} must fit on one line".format(field))
    if has_unsupported_control(value, allow_newline=not one_line):
        raise PackagingError("{0} contains unsupported characters".format(field))
    return value


def validate_https_url(value: object, field: str) -> None:
    url = require_text(value, field, 1024)
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise PackagingError("{0} is not a valid HTTPS URL: {1}".format(field, exc))
    if parsed.scheme != "https" or not parsed.netloc or not hostname:
        raise PackagingError("{0} must be an absolute HTTPS URL".format(field))
    if username is not None or password is not None:
        raise PackagingError("{0} must not contain credentials".format(field))


def validate_brand_casing(content: str, path: Path) -> None:
    for match in BRAND_PATTERN.finditer(content):
        if match.group(0) != "lihi":
            raise PackagingError(
                "Brand must be lowercase lihi in {0}".format(path)
            )


def validate_developer_app_manifest(path: Path, app_id: str) -> None:
    payload = read_json(path)
    expected = build_developer_app_manifest(app_id)
    if payload != expected:
        raise PackagingError(
            "Developer .app.json must contain exactly one lihi app mapping"
        )


def validate_manifest(
    manifest: dict,
    staging_root: Path,
    app_id: str = None,
) -> None:
    if manifest.get("name") != PLUGIN_NAME:
        raise PackagingError("Public manifest name must be lihi")
    manifest_path = staging_root / ".codex-plugin/plugin.json"
    version = manifest.get("version")
    core_version = semantic_version_core(version, manifest_path)
    if app_id is None:
        if version != core_version:
            raise PackagingError(
                "Public manifest version must be major.minor.patch only"
            )
    elif not version.startswith(core_version + "+codex.dev."):
        raise PackagingError(
            "Developer manifest version must use a Codex cachebuster"
        )
    require_text(manifest.get("description"), "description", 4000, one_line=False)
    if manifest.get("skills") != "./skills/":
        raise PackagingError("Public manifest skills must be ./skills/")
    for excluded in ("mcpServers", "hooks"):
        if excluded in manifest:
            raise PackagingError("OpenAI manifest must not contain {0}".format(excluded))
    if app_id is None:
        if "apps" in manifest:
            raise PackagingError("Public manifest must not contain apps")
    else:
        validate_developer_app_id(app_id)
        if manifest.get("apps") != "./.app.json":
            raise PackagingError("Developer manifest apps must be ./.app.json")
        validate_developer_app_manifest(staging_root / ".app.json", app_id)

    author = manifest.get("author")
    if not isinstance(author, dict):
        raise PackagingError("Public manifest author must be an object")
    author_name = require_text(author.get("name"), "author.name", 120)
    validate_https_url(author.get("url"), "author.url")
    validate_https_url(manifest.get("homepage"), "homepage")

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        raise PackagingError("Public manifest interface must be an object")
    display_name = require_text(interface.get("displayName"), "displayName", 30)
    require_text(interface.get("shortDescription"), "shortDescription", 30)
    require_text(interface.get("longDescription"), "longDescription", 4000, one_line=False)
    developer_name = require_text(interface.get("developerName"), "developerName", 80)
    if author_name != developer_name:
        raise PackagingError("author.name and developerName must match")
    if display_name != "lihi":
        raise PackagingError("Public displayName must be lihi")
    category = interface.get("category")
    if category not in CATEGORY_VALUES:
        raise PackagingError("Public manifest category is unsupported")

    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) > 20:
        raise PackagingError("Public capabilities must be a list of at most 20 strings")
    for index, capability in enumerate(capabilities):
        require_text(capability, "capabilities[{0}]".format(index), 120)

    prompts = interface.get("defaultPrompt")
    if not isinstance(prompts, list) or not prompts or len(prompts) > 3:
        raise PackagingError("Public defaultPrompt must contain one to three prompts")
    normalized_prompts = set()
    for index, prompt in enumerate(prompts):
        value = require_text(prompt, "defaultPrompt[{0}]".format(index), 128)
        if "@" in value:
            raise PackagingError("Public defaultPrompt must not contain @mentions")
        normalized = " ".join(unicodedata.normalize("NFKC", value).split())
        if normalized in normalized_prompts:
            raise PackagingError("Public defaultPrompt entries must be unique")
        normalized_prompts.add(normalized)

    link_fields = [
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
    ]
    if app_id is None:
        link_fields.append("supportURL")
    elif "supportURL" in interface:
        raise PackagingError(
            "Developer manifest must omit unsupported interface.supportURL"
        )
    for field in link_fields:
        validate_https_url(interface.get(field), field)
    if interface.get("logo") != "./assets/logo.png":
        raise PackagingError("Public logo must be ./assets/logo.png")
    if interface.get("composerIcon") != "./assets/composer-icon.png":
        raise PackagingError(
            "Public composerIcon must be ./assets/composer-icon.png"
        )
    if "screenshots" in interface:
        raise PackagingError("Public package must not contain screenshots")

    for relative_path, dimension in PACKAGE_ASSET_DIMENSIONS.items():
        validate_png_dimension(staging_root / relative_path, dimension)


def validate_staging(
    repo_root: Path,
    staging_root: Path,
    app_id: str = None,
) -> None:
    actual_files = {path.as_posix() for path in regular_files(staging_root)}
    expected_files = expected_package_files(include_app=app_id is not None)
    if actual_files != expected_files:
        raise PackagingError(
            "Staged package files differ from the allowlist: expected {0!r}, got {1!r}".format(
                tuple(sorted(expected_files)), tuple(sorted(actual_files))
            )
        )

    manifest_path = staging_root / ".codex-plugin/plugin.json"
    manifest = read_json(manifest_path)
    validate_manifest(manifest, staging_root, app_id=app_id)

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
        host_neutral_content = content
        if app_id is not None and path == staging_root / ".codex-plugin/plugin.json":
            manifest_for_scan = read_json(path)
            manifest_for_scan["version"] = semantic_version_core(
                manifest_for_scan.get("version"), path
            )
            host_neutral_content = json.dumps(
                manifest_for_scan,
                ensure_ascii=False,
                sort_keys=True,
            )
        if HOST_SPECIFIC_PATTERN.search(host_neutral_content):
            raise PackagingError("Host-specific wording found in OpenAI package: {0}".format(path))
        lowered = host_neutral_content.lower()
        if "codex mcp login" in lowered or "mcp settings" in lowered or "open `/mcp`" in lowered:
            raise PackagingError("Host-specific OAuth action found in OpenAI package: {0}".format(path))


def prepare_staging(
    repo_root: Path,
    staging_root: Path,
    version: str,
    app_id: str = None,
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

    copy_regular_file(repo_root / LOGO_SOURCE, staging_root / "assets/logo.png")
    copy_regular_file(
        repo_root / COMPOSER_ICON_SOURCE,
        staging_root / "assets/composer-icon.png",
    )

    manifest_path = staging_root / ".codex-plugin/plugin.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_public_manifest(repo_root, version)
    if app_id is not None:
        validate_developer_app_id(app_id)
        manifest["apps"] = "./.app.json"
        manifest["interface"].pop("supportURL", None)
        app_manifest_path = staging_root / ".app.json"
        write_json(app_manifest_path, build_developer_app_manifest(app_id))
        app_manifest_path.chmod(0o644)
    write_json(manifest_path, manifest)
    manifest_path.chmod(0o644)


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


def write_deterministic_zip(staging_root: Path, output_path: Path) -> None:
    paths = sorted(
        (path for path in staging_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(staging_root).as_posix(),
    )
    try:
        with zipfile.ZipFile(
            str(output_path),
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for path in paths:
                name = path.relative_to(staging_root).as_posix()
                validate_archive_member_name(name)
                permissions = (
                    0o755
                    if name
                    in {
                        "skills/lihi-shorten/scripts/detect_urls.py",
                        "lihi-shorten/scripts/detect_urls.py",
                    }
                    else 0o644
                )
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
                "skills/lihi-shorten/scripts/detect_urls.py",
                "lihi-shorten/scripts/detect_urls.py",
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


def sha256_directory(root: Path) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(regular_files(root)):
        path = root / relative_path
        name = relative_path.as_posix().encode("utf-8")
        data = path.read_bytes()
        mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
        digest.update(struct.pack(">I", len(name)))
        digest.update(name)
        digest.update(struct.pack(">I", mode))
        digest.update(struct.pack(">Q", len(data)))
        digest.update(data)
    return digest.hexdigest()


def validate_developer_bundle(
    repo_root: Path,
    bundle_root: Path,
    app_id: str,
    version: str,
) -> None:
    actual_files = {path.as_posix() for path in regular_files(bundle_root)}
    expected_files = expected_developer_bundle_files()
    if actual_files != expected_files:
        raise PackagingError(
            "Developer bundle files differ from the allowlist: expected "
            "{0!r}, got {1!r}".format(
                tuple(sorted(expected_files)), tuple(sorted(actual_files))
            )
        )

    marketplace_path = bundle_root / ".agents/plugins/marketplace.json"
    if read_json(marketplace_path) != build_developer_marketplace():
        raise PackagingError("Developer marketplace metadata is invalid")

    plugin_root = bundle_root / "plugins" / PLUGIN_NAME
    validate_staging(repo_root, plugin_root, app_id=app_id)
    manifest = read_json(plugin_root / ".codex-plugin/plugin.json")
    if manifest.get("version") != version:
        raise PackagingError("Developer manifest version is invalid")
    if not version.startswith(release_version(repo_root) + "+codex.dev."):
        raise PackagingError("Developer manifest must use a Codex cachebuster")


def prepare_developer_bundle(
    repo_root: Path,
    bundle_root: Path,
    base_version: str,
    app_id: str,
) -> str:
    app_id = validate_developer_app_id(app_id)
    plugin_root = bundle_root / "plugins" / PLUGIN_NAME
    plugin_root.mkdir(parents=True)
    prepare_staging(
        repo_root,
        plugin_root,
        base_version,
        app_id=app_id,
    )

    cachebuster = sha256_directory(plugin_root)[:12]
    version = "{0}+codex.dev.{1}".format(base_version, cachebuster)
    manifest_path = plugin_root / ".codex-plugin/plugin.json"
    manifest = read_json(manifest_path)
    manifest["version"] = version
    write_json(manifest_path, manifest)
    manifest_path.chmod(0o644)

    marketplace_path = bundle_root / ".agents/plugins/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    write_json(marketplace_path, build_developer_marketplace())
    marketplace_path.chmod(0o644)

    validate_developer_bundle(repo_root, bundle_root, app_id, version)
    return version


def publish_developer_directory(
    staging_root: Path,
    output_dir: Path,
    version: str,
) -> Tuple[Path, str]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PackagingError(
            "Cannot create output directory {0}: {1}".format(output_dir, exc)
        )

    target = output_dir / (DEVELOPER_BUNDLE_PREFIX + version)
    staged_digest = sha256_directory(staging_root)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir():
            raise PackagingError(
                "Developer bundle output is not a regular directory: {0}".format(
                    target
                )
            )
        if sha256_directory(target) != staged_digest:
            raise PackagingError(
                "Developer bundle output already exists with different content: "
                "{0}".format(target)
            )
        return target, staged_digest

    try:
        with tempfile.TemporaryDirectory(
            prefix=".lihi-openai-developer-",
            dir=str(output_dir),
        ) as temporary:
            candidate = Path(temporary) / "bundle"
            shutil.copytree(str(staging_root), str(candidate))
            if sha256_directory(candidate) != staged_digest:
                raise PackagingError("Copied Developer bundle content changed")
            os.replace(str(candidate), str(target))
    except OSError as exc:
        raise PackagingError(
            "Cannot publish Developer bundle {0}: {1}".format(target, exc)
        )
    return target, staged_digest


def build_developer_bundle(
    repo_root: Path,
    output_dir: Path,
    app_id: str,
) -> Tuple[Path, str, str]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    app_id = validate_developer_app_id(app_id)
    base_version = validate_source_bundle(repo_root)
    for relative_path, dimension in SOURCE_ASSET_DIMENSIONS.items():
        validate_png_dimension(repo_root / relative_path, dimension)

    with tempfile.TemporaryDirectory(
        prefix="lihi-openai-developer-staging-"
    ) as temporary:
        staging_root = Path(temporary) / "marketplace"
        staging_root.mkdir()
        version = prepare_developer_bundle(
            repo_root,
            staging_root,
            base_version,
            app_id,
        )
        target, digest = publish_developer_directory(
            staging_root,
            output_dir,
            version,
        )
    return target, version, digest


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
    artifact_keys = ("plugin",) + SKILLS
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


def build_bundle(repo_root: Path, output_dir: Path) -> Tuple[Path, str, str]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    version = validate_source_bundle(repo_root)

    for relative_path, dimension in SOURCE_ASSET_DIMENSIONS.items():
        validate_png_dimension(repo_root / relative_path, dimension)

    with tempfile.TemporaryDirectory(prefix="lihi-openai-platform-") as temporary:
        temporary_root = Path(temporary)
        staging_root = temporary_root / "plugin"
        staging_root.mkdir(parents=True)
        prepare_staging(repo_root, staging_root, version)
        validate_staging(repo_root, staging_root)

        skill_staging_roots = {}
        for skill_name in SKILLS:
            skill_root = temporary_root / "skills" / skill_name
            packaged_skill_root = skill_root / skill_name
            packaged_skill_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                str(staging_root / "skills" / skill_name),
                str(packaged_skill_root),
                copy_function=shutil.copy2,
            )
            actual_names = {
                path.relative_to(skill_root).as_posix()
                for path in skill_root.rglob("*")
                if path.is_file()
            }
            expected_names = expected_skill_archive_files(skill_name)
            if actual_names != expected_names:
                raise PackagingError(
                    "Individual skill staging differs from the allowlist for "
                    "{0}: expected {1!r}, got {2!r}".format(
                        skill_name,
                        tuple(sorted(expected_names)),
                        tuple(sorted(actual_names)),
                    )
                )
            skill_staging_roots[skill_name] = skill_root

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PackagingError("Cannot create output directory {0}: {1}".format(output_dir, exc))
        artifact_names = public_artifact_filenames(version)
        staging_roots = {"plugin": staging_root}
        staging_roots.update(skill_staging_roots)
        expected_names_by_artifact = {"plugin": expected_package_files()}
        expected_names_by_artifact.update(
            {
                skill_name: expected_skill_archive_files(skill_name)
                for skill_name in SKILLS
            }
        )
        temporary_zips = {}
        try:
            for artifact_key in ("plugin",) + SKILLS:
                with tempfile.NamedTemporaryFile(
                    prefix=".{0}-".format(artifact_key),
                    suffix=".tmp",
                    dir=str(output_dir),
                    delete=False,
                ) as stream:
                    temporary_zip = Path(stream.name)
                temporary_zips[artifact_key] = temporary_zip
                write_deterministic_zip(
                    staging_roots[artifact_key],
                    temporary_zip,
                )
                validate_archive(
                    temporary_zip,
                    expected_names_by_artifact[artifact_key],
                )
                temporary_zip.chmod(0o644)

            publish_public_zip_artifacts(
                output_dir,
                temporary_zips,
                artifact_names,
            )
        except OSError as exc:
            raise PackagingError(
                "Cannot publish OpenAI Platform ZIP artifacts: {0}".format(exc)
            )
        finally:
            for temporary_zip in tuple(temporary_zips.values()):
                try:
                    temporary_zip.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise PackagingError(
                        "Cannot remove temporary ZIP {0}: {1}".format(
                            temporary_zip, exc
                        )
                    )

    target = output_dir / artifact_names["plugin"]
    digest = sha256_file(target)
    return target, version, digest


def parse_args(argv: Sequence[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the public lihi OpenAI Platform plugin and skill ZIPs, or a Developer mode "
            "marketplace bundle when --app-id is provided."
        )
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory that will receive the versioned artifact.",
    )
    parser.add_argument(
        "--app-id",
        help=(
            "Registered ChatGPT Developer mode technical ID beginning with "
            "plugin_asdk_app_. When present, build a local marketplace bundle "
            "instead of the public ZIP artifacts."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        if args.app_id is None:
            target, version, digest = build_bundle(repo_root, args.output_dir)
        else:
            target, version, digest = build_developer_bundle(
                repo_root,
                args.output_dir,
                args.app_id,
            )
    except PackagingError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1
    if args.app_id is None:
        print("Built OpenAI Platform bundle: {0}".format(target))
        for skill_name in SKILLS:
            skill_target = args.output_dir.resolve() / public_artifact_filenames(
                version
            )[skill_name]
            print(
                "Built OpenAI skill bundle {0}: {1}".format(
                    skill_name,
                    skill_target,
                )
            )
    else:
        print("Built OpenAI Developer bundle: {0}".format(target))
        print("Marketplace: {0}".format(DEVELOPER_MARKETPLACE_NAME))
        print(
            "Plugin: {0}@{1}".format(
                PLUGIN_NAME,
                DEVELOPER_MARKETPLACE_NAME,
            )
        )
    print("Version: {0}".format(version))
    print("SHA-256: {0}".format(digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
