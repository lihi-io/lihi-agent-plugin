import binascii
import hashlib
import importlib.util
import json
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path


PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)


def load_packager(repo_root):
    path = repo_root / "scripts/package_openai_platform_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "package_openai_platform_bundle", str(path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path, width=48, height=48, rgba=(24, 88, 140, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    row = bytes(rgba) * width
    pixels = b"".join(b"\x00" + row for _ in range(height))
    content = b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
            ),
            png_chunk(b"IDAT", zlib.compress(pixels, 9)),
            png_chunk(b"IEND", b""),
        )
    )
    path.write_bytes(content)


def tree_hash(root, relative_paths):
    digest = hashlib.sha256()
    for relative_path in relative_paths:
        path = root / relative_path
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if (
                not candidate.is_file()
                or "__pycache__" in candidate.parts
                or candidate.suffix in {".pyc", ".pyo"}
            ):
                continue
            digest.update(str(candidate.relative_to(root)).encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()


def copy_fixture(source_root, destination):
    (destination / "scripts").mkdir(parents=True)
    shutil.copy2(
        source_root / "scripts/package_openai_platform_bundle.py",
        destination / "scripts/package_openai_platform_bundle.py",
    )
    shutil.copytree(
        source_root / "plugins/codex/lihi",
        destination / "plugins/codex/lihi",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    claude_manifest = source_root / "plugins/claude/lihi/.claude-plugin/plugin.json"
    claude_target = destination / "plugins/claude/lihi/.claude-plugin/plugin.json"
    claude_target.parent.mkdir(parents=True)
    shutil.copy2(claude_manifest, claude_target)
    write_png(
        destination / "packaging/openai-platform/assets/logo.png",
        width=256,
        height=256,
    )
    write_png(
        destination / "packaging/openai-platform/assets/composer-icon.png",
        rgba=(250, 180, 32, 255),
    )


def run_packager(repo_root, output_dir, app_id=None):
    command = [
        sys.executable,
        str(repo_root / "scripts/package_openai_platform_bundle.py"),
        "--output-dir",
        str(output_dir),
    ]
    if app_id is not None:
        command.extend(("--app-id", app_id))
    return subprocess.run(
        command,
        cwd=str(repo_root),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class OpenAIPlatformPackagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.packager = load_packager(cls.repo_root)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.temporary.name) / "repo"
        copy_fixture(cls.repo_root, cls.fixture_root)
        cls.source_paths = (
            Path("plugins"),
            Path("packaging/openai-platform"),
            Path("scripts/package_openai_platform_bundle.py"),
        )
        cls.source_hash_before = tree_hash(cls.fixture_root, cls.source_paths)
        cls.output_dir = Path(cls.temporary.name) / "output"
        cls.process = run_packager(cls.fixture_root, cls.output_dir)
        cls.source_hash_after = tree_hash(cls.fixture_root, cls.source_paths)
        cls.version = "0.3.1"
        cls.bundle = cls.output_dir / (
            "lihi-openai-platform-" + cls.version + ".zip"
        )
        cls.skill_bundles = {
            skill_name: cls.output_dir
            / "{0}-{1}.zip".format(skill_name, cls.version)
            for skill_name in SKILLS
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fresh_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture_root = Path(temporary.name) / "repo"
        copy_fixture(self.repo_root, fixture_root)
        return temporary, fixture_root

    def test_subprocess_build_succeeds_without_modifying_source(self):
        self.assertEqual(self.process.returncode, 0, self.process.stderr)
        self.assertIn("Version: " + self.version, self.process.stdout)
        self.assertIn("SHA-256: ", self.process.stdout)
        self.assertTrue(self.bundle.is_file())
        for skill_name, skill_bundle in self.skill_bundles.items():
            self.assertIn(
                "Built OpenAI skill bundle {0}:".format(skill_name),
                self.process.stdout,
            )
            self.assertTrue(skill_bundle.is_file())
        self.assertEqual(self.source_hash_before, self.source_hash_after)
        self.assertEqual(
            sorted(path.name for path in self.output_dir.glob("*.zip")),
            sorted(
                [self.bundle.name]
                + [path.name for path in self.skill_bundles.values()]
            ),
        )

    def test_version_helpers_enforce_shared_semver_core(self):
        self.assertEqual(
            self.packager.semantic_version_core(
                "0.3.1+codex.cache", Path("manifest.json")
            ),
            "0.3.1",
        )
        with self.assertRaises(self.packager.PackagingError):
            self.packager.semantic_version_core("0.3", Path("manifest.json"))

    def test_zip_has_exact_root_allowlist_and_safe_paths(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            names = archive.namelist()
            self.assertEqual(set(names), self.packager.expected_package_files())
            self.assertEqual(len(names), len(set(names)))
            self.assertIn(".codex-plugin/plugin.json", names)
            self.assertFalse(any(name.startswith("lihi/") for name in names))
            self.assertFalse(any("\\" in name for name in names))
            self.assertFalse(any(".." in name.split("/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith(".pyc") for name in names))
            self.assertLessEqual(self.bundle.stat().st_size, 100 * 1000 * 1000)
            self.assertLessEqual(len(names), 5000)
            self.assertLessEqual(
                sum(info.file_size for info in archive.infolist()),
                512 * 1024 * 1024,
            )

    def test_manifest_is_public_with_mcp_metadata(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            manifest = json.loads(
                archive.read(".codex-plugin/plugin.json").decode("utf-8")
            )
        self.assertEqual(manifest["name"], "lihi")
        self.assertEqual(manifest["version"], "0.3.1")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)
        interface = manifest["interface"]
        self.assertEqual(interface["shortDescription"], "lihi account and short URLs")
        self.assertLessEqual(len(interface["displayName"]), 30)
        self.assertLessEqual(len(interface["shortDescription"]), 30)
        self.assertLessEqual(len(interface["longDescription"]), 4000)
        self.assertEqual(interface["websiteURL"], "https://lihi.io/")
        self.assertEqual(interface["supportURL"], "https://lihistatus.com/contact")
        self.assertEqual(
            interface["privacyPolicyURL"],
            "https://knowledge.lihi.io/privacy-policy/",
        )
        self.assertEqual(
            interface["termsOfServiceURL"],
            "https://knowledge.lihi.io/terms-of-use/",
        )
        self.assertEqual(interface["logo"], "./assets/logo.png")
        self.assertEqual(
            interface["composerIcon"], "./assets/composer-icon.png"
        )
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(
            all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])
        )

    def test_four_skills_are_valid_immediate_children(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            names = set(archive.namelist())
            for skill_name in SKILLS:
                path = "skills/{0}/SKILL.md".format(skill_name)
                self.assertIn(path, names)
                content = archive.read(path).decode("utf-8")
                metadata = self.packager.parse_skill_frontmatter(
                    content, Path(path)
                )
                self.assertEqual(metadata["name"], skill_name)
                self.assertLessEqual(len(metadata["description"]), 1024)
                self.assertLessEqual(len("lihi:" + skill_name), 64)
                self.assertTrue(content.split("---", 2)[2].strip())

    def test_individual_skill_zips_have_one_named_top_level_directory(self):
        for skill_name, bundle in self.skill_bundles.items():
            with self.subTest(skill_name=skill_name):
                with zipfile.ZipFile(str(bundle), "r") as archive:
                    names = archive.namelist()
                    expected = self.packager.expected_skill_archive_files(
                        skill_name
                    )
                    self.assertEqual(set(names), expected)
                    self.assertEqual(len(names), len(set(names)))
                    self.assertEqual(
                        {name.split("/", 1)[0] for name in names},
                        {skill_name},
                    )
                    self.assertIn(
                        "{0}/SKILL.md".format(skill_name),
                        names,
                    )
                    self.assertFalse(
                        any(
                            name.startswith(".codex-plugin/")
                            or name.startswith("assets/")
                            or name.endswith(".app.json")
                            or name.endswith(".mcp.json")
                            for name in names
                        )
                    )

                    skill_text = archive.read(
                        "{0}/SKILL.md".format(skill_name)
                    ).decode("utf-8")
                    metadata = self.packager.parse_skill_frontmatter(
                        skill_text,
                        Path(skill_name) / "SKILL.md",
                    )
                    self.assertEqual(metadata["name"], skill_name)
                    self.assertTrue(skill_text.split("---", 2)[2].strip())

                    agent_text = archive.read(
                        "{0}/agents/openai.yaml".format(skill_name)
                    ).decode("utf-8")
                    self.assertIn('value: "lihi"', agent_text)
                    self.assertIn(PRODUCTION_ENDPOINT, agent_text)

                    markdown = "\n".join(
                        archive.read(name).decode("utf-8")
                        for name in names
                        if name.endswith(".md")
                    )
                    self.assertNotRegex(
                        markdown,
                        r"(?i)\b(?:codex|claude)\b",
                    )
                    for promotional_url in self.packager.PROMOTIONAL_URLS:
                        self.assertNotIn(promotional_url, markdown)

                    if skill_name == "lihi-shorten":
                        detector_name = (
                            "lihi-shorten/scripts/detect_urls.py"
                        )
                        detector_mode = (
                            archive.getinfo(detector_name).external_attr >> 16
                        )
                        self.assertEqual(
                            stat.S_IFMT(detector_mode),
                            stat.S_IFREG,
                        )
                        self.assertTrue(detector_mode & 0o111)

    def test_skills_are_host_neutral_and_keep_production_dependencies(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            combined = []
            for info in archive.infolist():
                if Path(info.filename).suffix.lower() not in {
                    ".json",
                    ".md",
                    ".yaml",
                    ".yml",
                }:
                    continue
                text = archive.read(info).decode("utf-8")
                combined.append(text)
                self.assertNotRegex(text, r"(?i)\b(?:codex|claude)\b")
                self.assertNotIn("codex mcp login", text.lower())
                self.assertNotIn("MCP settings", text)
                self.assertNotIn("open `/mcp`", text.lower())
                self.assertNotIn("https://app.lihidev.com", text)
                self.assertNotIn("lihi-dev", text)
            package_text = "\n".join(combined)
            self.assertEqual(package_text.count(PRODUCTION_ENDPOINT), 4)
            for skill_name in SKILLS:
                metadata_path = "skills/{0}/agents/openai.yaml".format(
                    skill_name
                )
                metadata = archive.read(metadata_path).decode("utf-8")
                self.assertIn("$" + skill_name, metadata)
                self.assertIn('value: "lihi"', metadata)
                self.assertIn(PRODUCTION_ENDPOINT, metadata)

    def test_public_skills_remove_promotional_link_sentences(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            markdown = "\n".join(
                archive.read(info).decode("utf-8")
                for info in archive.infolist()
                if info.filename.endswith(".md")
            )
        for promotional_url in self.packager.PROMOTIONAL_URLS:
            self.assertNotIn(promotional_url, markdown)
        self.assertNotIn("訂閱方案說明：", markdown)
        self.assertNotIn("專屬網域說明：", markdown)
        self.assertNotIn("lihi 服務內容：", markdown)
        self.assertNotIn("lihi 提供專屬網域與公用網域", markdown)
        self.assertIn(
            "建議選擇專屬網域，有助於增加信任度。",
            markdown,
        )
        self.assertIn(
            "explain the account limit",
            markdown,
        )
        self.assertNotIn("lihi plans define short URL creation quotas", markdown)

    def test_staging_rewrites_only_host_specific_skill_files(self):
        self.assertFalse(
            (self.repo_root / "packaging/openai-platform/overlay").exists()
        )
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            for skill_name in SKILLS:
                for relative_path in self.packager.SKILL_FILES[skill_name]:
                    package_path = (
                        Path("skills") / skill_name / relative_path
                    )
                    packaged = archive.read(package_path.as_posix())
                    source = (
                        self.fixture_root
                        / "plugins/codex/lihi/skills"
                        / skill_name
                        / relative_path
                    ).read_bytes()
                    if package_path in self.packager.HOST_NEUTRAL_REWRITES:
                        self.assertNotEqual(packaged, source, package_path)
                    else:
                        self.assertEqual(packaged, source, package_path)

            shorten = archive.read("skills/lihi-shorten/SKILL.md").decode("utf-8")
            account = archive.read("skills/lihi-account/SKILL.md").decode("utf-8")
            self.assertIn("while the assistant adjusts", shorten)
            self.assertIn("OpenAI host OAuth recovery rules", shorten)
            self.assertIn("OpenAI host OAuth recovery rules", account)

    def test_stale_host_specific_source_fails_closed(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        skill_path = (
            fixture_root
            / "plugins/codex/lihi/skills/lihi-shorten/SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("while Codex adjusts", content)
        skill_path.write_text(
            content.replace(
                "while Codex adjusts",
                "while Codex revises",
                1,
            ),
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(
            "Host-neutral source fragment must appear exactly once",
            process.stderr,
        )
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_detector_and_assets_are_preserved(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            detector_name = "skills/lihi-shorten/scripts/detect_urls.py"
            source_detector = (
                self.fixture_root
                / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
            )
            self.assertEqual(archive.read(detector_name), source_detector.read_bytes())
            mode = archive.getinfo(detector_name).external_attr >> 16
            self.assertEqual(stat.S_IFMT(mode), stat.S_IFREG)
            self.assertTrue(mode & 0o111)
            self.assertEqual(
                archive.read("assets/logo.png"),
                (
                    self.fixture_root
                    / "packaging/openai-platform/assets/logo.png"
                ).read_bytes(),
            )
            self.assertEqual(
                archive.read("assets/composer-icon.png"),
                (
                    self.fixture_root
                    / "packaging/openai-platform/assets/composer-icon.png"
                ).read_bytes(),
            )
            self.assertEqual(
                struct.unpack(">II", archive.read("assets/logo.png")[16:24]),
                (256, 256),
            )
            self.assertEqual(
                struct.unpack(
                    ">II", archive.read("assets/composer-icon.png")[16:24]
                ),
                (48, 48),
            )

    def test_repeated_build_is_byte_for_byte_reproducible(self):
        second_output = Path(self.temporary.name) / "second-output"
        second = run_packager(self.fixture_root, second_output)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_bundles = [self.bundle] + list(self.skill_bundles.values())
        for first_bundle in first_bundles:
            second_bundle = second_output / first_bundle.name
            with self.subTest(bundle=first_bundle.name):
                self.assertEqual(
                    first_bundle.read_bytes(),
                    second_bundle.read_bytes(),
                )
                self.assertEqual(
                    hashlib.sha256(first_bundle.read_bytes()).hexdigest(),
                    hashlib.sha256(second_bundle.read_bytes()).hexdigest(),
                )

    def test_app_id_builds_installable_developer_marketplace_bundle(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "developer-output"
        app_id = "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d"
        source_hash_before = tree_hash(fixture_root, self.source_paths)
        process = run_packager(fixture_root, output_dir, app_id=app_id)
        source_hash_after = tree_hash(fixture_root, self.source_paths)

        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Built OpenAI Developer bundle:", process.stdout)
        self.assertIn("Marketplace: lihi-openai-developer", process.stdout)
        self.assertIn("Plugin: lihi@lihi-openai-developer", process.stdout)
        self.assertEqual(source_hash_before, source_hash_after)
        self.assertFalse(any(output_dir.glob("*.zip")))

        bundles = list(output_dir.glob("lihi-openai-developer-*"))
        self.assertEqual(len(bundles), 1)
        bundle = bundles[0]
        actual_files = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            actual_files,
            self.packager.expected_developer_bundle_files(),
        )

        plugin_root = bundle / "plugins/lihi"
        manifest = json.loads(
            (plugin_root / ".codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["name"], "lihi")
        self.assertRegex(
            manifest["version"],
            r"^0\.3\.1\+codex\.dev\.[0-9a-f]{12}$",
        )
        self.assertEqual(manifest["apps"], "./.app.json")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("supportURL", manifest["interface"])
        self.assertEqual(
            json.loads((plugin_root / ".app.json").read_text(encoding="utf-8")),
            {"apps": {"lihi": {"id": app_id}}},
        )
        self.assertEqual(
            json.loads(
                (bundle / ".agents/plugins/marketplace.json").read_text(
                    encoding="utf-8"
                )
            ),
            self.packager.build_developer_marketplace(),
        )

    def test_developer_bundle_is_reproducible_and_app_id_isolated(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        app_id = "plugin_asdk_app_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        first_output = Path(temporary.name) / "developer-first"
        second_output = Path(temporary.name) / "developer-second"

        first = run_packager(fixture_root, first_output, app_id=app_id)
        repeated = run_packager(fixture_root, first_output, app_id=app_id)
        second = run_packager(fixture_root, second_output, app_id=app_id)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)

        first_bundle = next(first_output.glob("lihi-openai-developer-*"))
        second_bundle = next(second_output.glob("lihi-openai-developer-*"))
        self.assertEqual(first_bundle.name, second_bundle.name)
        self.assertEqual(
            self.packager.sha256_directory(first_bundle),
            self.packager.sha256_directory(second_bundle),
        )
        self.assertEqual(
            len(list(first_output.glob("lihi-openai-developer-*"))),
            1,
        )

        other_output = Path(temporary.name) / "developer-other"
        other_id = "plugin_asdk_app_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        other = run_packager(fixture_root, other_output, app_id=other_id)
        self.assertEqual(other.returncode, 0, other.stderr)
        other_bundle = next(other_output.glob("lihi-openai-developer-*"))
        self.assertNotEqual(first_bundle.name, other_bundle.name)
        self.assertNotIn(
            other_id,
            (first_bundle / "plugins/lihi/.app.json").read_text(
                encoding="utf-8"
            ),
        )

    def test_invalid_developer_app_id_fails_before_output(self):
        for index, app_id in enumerate(
            (
                "",
                "plugin_asdk_app_",
                "asdk_app_1234",
                "plugin_asdk_app_bad.value",
                " plugin_asdk_app_1234",
            )
        ):
            temporary, fixture_root = self.fresh_fixture()
            self.addCleanup(temporary.cleanup)
            output_dir = Path(temporary.name) / "invalid-{0}".format(index)
            process = run_packager(fixture_root, output_dir, app_id=app_id)
            self.assertNotEqual(process.returncode, 0, app_id)
            self.assertIn("app-id must start with plugin_asdk_app_", process.stderr)
            self.assertFalse(output_dir.exists(), app_id)

    def test_developer_rebuild_does_not_overwrite_existing_content(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "developer-output"
        app_id = "plugin_asdk_app_cccccccccccccccccccccccccccccccc"
        first = run_packager(fixture_root, output_dir, app_id=app_id)
        self.assertEqual(first.returncode, 0, first.stderr)
        bundle = next(output_dir.glob("lihi-openai-developer-*"))
        marker = bundle / "existing-user-marker.txt"
        marker.write_text("preserve me\n", encoding="utf-8")

        second = run_packager(fixture_root, output_dir, app_id=app_id)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn(
            "already exists with different content",
            second.stderr,
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")
        self.assertFalse(
            any(path.name.startswith(".lihi-openai-developer-") for path in output_dir.iterdir())
        )

    def test_missing_asset_fails_closed_with_fixed_path(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        logo = fixture_root / "packaging/openai-platform/assets/logo.png"
        logo.unlink()
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(str(logo), process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_invalid_png_dimensions_and_data_fail_closed(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        logo = fixture_root / "packaging/openai-platform/assets/logo.png"
        output_dir = Path(temporary.name) / "output"
        write_png(logo, width=48, height=49)
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("must be square", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

        write_png(logo, width=255, height=255)
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("must be exactly 256x256 pixels", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

        logo.write_bytes(b"not a png")
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("PNG signature is invalid", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_version_mismatch_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = (
            fixture_root / "plugins/claude/lihi/.claude-plugin/plugin.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0.4.0"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("must share one major.minor.patch version", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_validation_failure_preserves_existing_artifact_set(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        first = run_packager(fixture_root, output_dir)
        self.assertEqual(first.returncode, 0, first.stderr)
        artifacts = {
            path.name: path.read_bytes()
            for path in output_dir.glob("*.zip")
        }
        self.assertEqual(len(artifacts), 5)
        (
            fixture_root / "packaging/openai-platform/assets/composer-icon.png"
        ).write_bytes(b"broken")
        second = run_packager(fixture_root, output_dir)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in output_dir.glob("*.zip")
            },
            artifacts,
        )
        self.assertFalse(any(output_dir.glob("*.tmp")))

    def test_publish_failure_rolls_back_every_existing_artifact(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        first = run_packager(fixture_root, output_dir)
        self.assertEqual(first.returncode, 0, first.stderr)
        artifacts = {
            path.name: path.read_bytes()
            for path in output_dir.glob("*.zip")
        }
        self.assertEqual(len(artifacts), 5)

        write_png(
            fixture_root / "packaging/openai-platform/assets/logo.png",
            width=256,
            height=256,
            rgba=(220, 40, 90, 255),
        )
        original_replace = self.packager.os.replace
        replace_calls = []

        def fail_on_third_publish(source, target):
            replace_calls.append(Path(target).name)
            if len(replace_calls) == 3:
                raise OSError("simulated publish failure")
            return original_replace(source, target)

        self.packager.os.replace = fail_on_third_publish
        try:
            with self.assertRaises(self.packager.PackagingError) as raised:
                self.packager.build_bundle(fixture_root, output_dir)
        finally:
            self.packager.os.replace = original_replace

        self.assertIn("restored the previous artifact set", str(raised.exception))
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in output_dir.glob("*.zip")
            },
            artifacts,
        )
        self.assertFalse(any(output_dir.glob("*.tmp")))
        self.assertFalse(
            any(
                path.name.startswith(".lihi-openai-platform-backup-")
                for path in output_dir.iterdir()
            )
        )

    def test_malformed_agent_yaml_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        metadata_path = (
            fixture_root
            / "plugins/codex/lihi/skills/lihi-account/agents/openai.yaml"
        )
        metadata = metadata_path.read_text(encoding="utf-8")
        metadata_path.write_text(
            metadata.replace("interface:\n", "interface: [\n", 1),
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("supported YAML structure", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_archive_validator_rejects_unsafe_and_colliding_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            unsafe = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(str(unsafe), "w") as archive:
                archive.writestr("../escape", b"unsafe")
            with self.assertRaises(self.packager.PackagingError):
                self.packager.validate_archive(unsafe, {"../escape"})

            collision = Path(temporary) / "collision.zip"
            first = "skills/cafe\u0301/SKILL.md"
            second = "skills/caf\u00e9/SKILL.md"
            with zipfile.ZipFile(str(collision), "w") as archive:
                archive.writestr(first, b"one")
                archive.writestr(second, b"two")
            with self.assertRaises(self.packager.PackagingError):
                self.packager.validate_archive(collision, {first, second})


if __name__ == "__main__":
    unittest.main()
