import hashlib
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


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
    shutil.copytree(
        source_root / "packaging/openai-platform/assets",
        destination / "packaging/openai-platform/assets",
    )
    claude_manifest = source_root / "plugins/claude/lihi/.claude-plugin/plugin.json"
    claude_target = destination / "plugins/claude/lihi/.claude-plugin/plugin.json"
    claude_target.parent.mkdir(parents=True)
    shutil.copy2(claude_manifest, claude_target)


def run_packager(repo_root, output_dir, extra_args=()):
    command = [
        sys.executable,
        str(repo_root / "scripts/package_openai_platform_bundle.py"),
        "--output-dir",
        str(output_dir),
    ]
    command.extend(extra_args)
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
            Path("packaging"),
            Path("scripts/package_openai_platform_bundle.py"),
        )
        cls.source_hash_before = tree_hash(cls.fixture_root, cls.source_paths)
        cls.output_dir = Path(cls.temporary.name) / "output"
        cls.process = run_packager(cls.fixture_root, cls.output_dir)
        cls.source_hash_after = tree_hash(cls.fixture_root, cls.source_paths)
        cls.version = "0.3.2"
        cls.bundle = cls.output_dir / "lihi-{0}.zip".format(cls.version)
        cls.skill_bundles = {
            name: cls.output_dir / "{0}-{1}.zip".format(name, cls.version)
            for name in SKILLS
        }
        cls.bundles = {"lihi": cls.bundle, **cls.skill_bundles}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fresh_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture_root = Path(temporary.name) / "repo"
        copy_fixture(self.repo_root, fixture_root)
        return temporary, fixture_root

    def archive_text(self, archive):
        return "\n".join(
            archive.read(info).decode("utf-8")
            for info in archive.infolist()
            if Path(info.filename).suffix.lower()
            in {".json", ".md", ".yaml", ".yml"}
        )

    def test_subprocess_builds_plugin_and_four_skills_without_modifying_source(self):
        self.assertEqual(self.process.returncode, 0, self.process.stderr)
        self.assertIn("Version: " + self.version, self.process.stdout)
        self.assertIn("Built OpenAI Platform plugin bundle:", self.process.stdout)
        self.assertEqual(self.source_hash_before, self.source_hash_after)
        self.assertEqual(set(self.output_dir.iterdir()), set(self.bundles.values()))
        for key, bundle in self.bundles.items():
            self.assertIn(
                "SHA-256 ({0}): {1}".format(
                    key, hashlib.sha256(bundle.read_bytes()).hexdigest()
                ),
                self.process.stdout,
            )

    def test_version_helpers_enforce_shared_semver_core(self):
        self.assertEqual(
            self.packager.semantic_version_core(
                "0.3.2+codex.cache", Path("manifest.json")
            ),
            "0.3.2",
        )
        with self.assertRaises(self.packager.PackagingError):
            self.packager.semantic_version_core("0.3", Path("manifest.json"))

    def test_zip_has_one_plugin_root_and_exact_allowlist(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            names = archive.namelist()
            self.assertEqual(set(names), self.packager.expected_archive_files())
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(
                {name.split("/")[0] for name in names},
                {"plugin.json", "mcp.json", "skills", "assets"},
            )
            for skill_name in SKILLS:
                self.assertIn("skills/" + skill_name + "/SKILL.md", names)
            self.assertFalse(any("\\" in name for name in names))
            self.assertFalse(any(".." in name.split("/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith(".pyc") for name in names))
            self.assertFalse(any(".codex-plugin" in name for name in names))
            self.assertFalse(any(name.endswith(".app.json") for name in names))
            self.assertFalse(any(name.endswith(".mcp.json") for name in names))
            self.assertLessEqual(self.bundle.stat().st_size, 100 * 1000 * 1000)
            self.assertLessEqual(len(names), 5000)
            self.assertLessEqual(
                sum(info.file_size for info in archive.infolist()),
                512 * 1024 * 1024,
            )

    def test_individual_skill_zips_match_the_platform_skills_exactly(self):
        with zipfile.ZipFile(str(self.bundle), "r") as plugin:
            for skill_name, bundle in self.skill_bundles.items():
                with self.subTest(skill=skill_name), zipfile.ZipFile(str(bundle), "r") as skill:
                    expected = {
                        (Path(skill_name) / path).as_posix()
                        for path in self.packager.SKILL_FILES[skill_name]
                    }
                    self.assertEqual(set(skill.namelist()), expected)
                    self.assertEqual(len(skill.namelist()), len(expected))
                    self.assertEqual(
                        {name.split("/")[0] for name in skill.namelist()}, {skill_name}
                    )
                    self.assertIsNone(skill.testzip())
                    for name in expected:
                        self.assertEqual(skill.read(name), plugin.read("skills/" + name))
                        self.assertEqual(
                            skill.getinfo(name).external_attr,
                            plugin.getinfo("skills/" + name).external_attr,
                        )

    def test_portable_manifest_and_oauth_mcp_configuration(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            manifest = json.loads(archive.read("plugin.json"))
            self.assertEqual(
                manifest["$schema"],
                "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            )
            self.assertEqual(manifest["name"], "lihi")
            self.assertEqual(manifest["version"], self.version)
            self.assertNotIn("skills", manifest)
            self.assertNotIn("mcpServers", manifest)
            self.assertNotIn("interface", manifest)
            self.assertEqual(set(manifest["extensions"]), {"com.openai"})
            extension = manifest["extensions"]["com.openai"]
            self.assertEqual(set(extension), {"interface"})
            interface = extension["interface"]
            self.assertEqual(interface["displayName"], "lihi")
            self.assertEqual(interface["supportURL"], "https://lihistatus.com/contact")
            self.assertLessEqual(len(interface["shortDescription"]), 30)
            self.assertEqual(interface["composerIcon"], "./assets/composer-icon.png")
            self.assertEqual(interface["logo"], "./assets/logo.png")
            self.assertEqual(manifest["author"]["name"], "lihi")
            config = json.loads(archive.read("mcp.json"))
            self.assertEqual(
                config["$schema"],
                "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            )
            self.assertEqual(config["mcpServers"], {
                "lihi": {
                    "type": "streamable-http",
                    "url": PRODUCTION_ENDPOINT,
                    "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
                }
            })

    def test_brand_assets_are_packaged_byte_identically(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            for name in ("composer-icon.png", "logo.png"):
                self.assertEqual(
                    archive.read("assets/" + name),
                    (self.fixture_root / "packaging/openai-platform/assets" / name).read_bytes(),
                )

    def test_skills_are_valid_host_neutral_and_keep_production_dependency(self):
        for skill_name in SKILLS:
            with self.subTest(skill=skill_name), zipfile.ZipFile(
                str(self.bundle), "r"
            ) as archive:
                skill_path = "skills/" + skill_name + "/SKILL.md"
                skill_content = archive.read(skill_path).decode("utf-8")
                metadata = self.packager.parse_skill_frontmatter(
                    skill_content, Path(skill_path)
                )
                self.assertEqual(metadata["name"], skill_name)
                self.assertLessEqual(len(metadata["description"]), 1024)
                self.assertLessEqual(len("lihi:" + skill_name), 64)
                if skill_name in {"lihi-switch-group", "lihi-switch-domain"}:
                    self.assertIn("`email`: a non-empty string", skill_content)
                    self.assertIn("帳號 Email：<email>", skill_content)

                agent_path = "skills/" + skill_name + "/agents/openai.yaml"
                agent_text = archive.read(agent_path).decode("utf-8")
                self.assertIn("$" + skill_name, agent_text)
                self.assertIn('value: "lihi"', agent_text)
                self.assertIn(PRODUCTION_ENDPOINT, agent_text)

                text = self.archive_text(archive)
                self.assertNotRegex(text, r"(?i)\b(?:codex|claude)\b")
                self.assertNotIn("codex mcp login", text.lower())
                self.assertNotIn("MCP settings", text)
                self.assertNotIn("open `/mcp`", text.lower())
                self.assertNotIn("https://app.lihidev.com", text)
                self.assertNotIn("lihi-dev", text)
                for promotional_url in self.packager.PROMOTIONAL_URLS:
                    self.assertNotIn(promotional_url, text)

    def test_promotional_link_sentences_are_removed(self):
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            markdown = [
                archive.read(info).decode("utf-8")
                for info in archive.infolist()
                if info.filename.endswith(".md")
            ]
        combined = "\n".join(markdown)
        self.assertNotIn("訂閱方案說明：", combined)
        self.assertNotIn("專屬網域說明：", combined)
        self.assertIn("建議選擇專屬網域，有助於增加信任度。", combined)
        self.assertIn("explain the account limit", combined)

    def test_rewrites_are_applied_only_to_declared_files(self):
        for skill_name in SKILLS:
            with zipfile.ZipFile(str(self.bundle), "r") as archive:
                for relative_path in self.packager.SKILL_FILES[skill_name]:
                    archive_path = (Path("skills") / skill_name / relative_path).as_posix()
                    packaged = archive.read(archive_path)
                    source = (
                        self.fixture_root
                        / "plugins/codex/lihi/skills"
                        / skill_name
                        / relative_path
                    ).read_bytes()
                    rewrite_path = Path("skills") / skill_name / relative_path
                    if rewrite_path in self.packager.HOST_NEUTRAL_REWRITES:
                        self.assertNotEqual(packaged, source, rewrite_path)
                    else:
                        self.assertEqual(packaged, source, rewrite_path)

    def test_detector_bytes_and_executable_mode_are_preserved(self):
        name = "skills/lihi-shorten/scripts/detect_urls.py"
        source = (
            self.fixture_root
            / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
        )
        with zipfile.ZipFile(str(self.bundle), "r") as archive:
            self.assertEqual(archive.read(name), source.read_bytes())
            mode = archive.getinfo(name).external_attr >> 16
            self.assertEqual(stat.S_IFMT(mode), stat.S_IFREG)
            self.assertTrue(mode & 0o111)

    def test_missing_listing_asset_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture_root / "packaging/openai-platform/assets/logo.png").unlink()
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Required regular file is missing", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_invalid_listing_asset_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        (fixture_root / "packaging/openai-platform/assets/logo.png").write_bytes(b"bad")
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Required asset is not a PNG", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_app_id_option_is_removed(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        process = run_packager(
            fixture_root,
            output_dir,
            extra_args=("--app-id", "plugin_asdk_app_example"),
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("unrecognized arguments: --app-id", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_repeated_build_is_byte_for_byte_reproducible(self):
        second_output = Path(self.temporary.name) / "second-output"
        second = run_packager(self.fixture_root, second_output)
        self.assertEqual(second.returncode, 0, second.stderr)
        for bundle in self.bundles.values():
            with self.subTest(bundle=bundle.name):
                second_bundle = second_output / bundle.name
                self.assertEqual(bundle.read_bytes(), second_bundle.read_bytes())

    def test_version_mismatch_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_root / "plugins/claude/lihi/.claude-plugin/plugin.json"
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

    def test_production_build_metadata_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_root / "plugins/codex/lihi/.codex-plugin/plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0.3.2+codex.cache"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("without build metadata", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_missing_source_file_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        missing = (
            fixture_root
            / "plugins/codex/lihi/skills/lihi-account/references/oauth-recovery.md"
        )
        missing.unlink()
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Unexpected files", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

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

    def test_non_utf8_detector_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        detector = (
            fixture_root
            / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
        )
        detector.write_bytes(detector.read_bytes() + b"\xff")
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Cannot read UTF-8 file", process.stderr)
        self.assertFalse(any(output_dir.glob("*.zip")))

    def test_stale_host_specific_source_fails_closed(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        skill_path = fixture_root / "plugins/codex/lihi/skills/lihi-shorten/SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        skill_path.write_text(
            content.replace("while Codex adjusts", "while Codex revises", 1),
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

    def test_validation_failure_preserves_existing_artifact_set(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        first = run_packager(fixture_root, output_dir)
        self.assertEqual(first.returncode, 0, first.stderr)
        artifacts = {
            path.name: path.read_bytes() for path in output_dir.glob("*.zip")
        }
        self.assertEqual(len(artifacts), 5)
        metadata_path = (
            fixture_root
            / "plugins/codex/lihi/skills/lihi-account/agents/openai.yaml"
        )
        metadata_path.write_text("broken\n", encoding="utf-8")
        second = run_packager(fixture_root, output_dir)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(
            {path.name: path.read_bytes() for path in output_dir.glob("*.zip")},
            artifacts,
        )
        self.assertFalse(any(output_dir.glob("*.tmp")))

    def test_partial_publication_restores_all_five_archives(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        targets, version, digests = self.packager.build_bundle(fixture_root, output_dir)
        before = {key: path.read_bytes() for key, path in targets.items()}
        account_skill = fixture_root / "plugins/codex/lihi/skills/lihi-account/SKILL.md"
        account_skill.write_text(
            account_skill.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
        original_replace = self.packager.os.replace
        calls = []

        def fail_on_third_publish(source, target):
            calls.append(Path(target).name)
            if len(calls) == 3:
                raise OSError("simulated publish failure")
            return original_replace(source, target)

        with mock.patch.object(self.packager.os, "replace", side_effect=fail_on_third_publish):
            with self.assertRaises(self.packager.PackagingError) as raised:
                self.packager.build_bundle(fixture_root, output_dir)
        self.assertIn("restored the previous artifact set", str(raised.exception))
        self.assertEqual({key: path.read_bytes() for key, path in targets.items()}, before)
        self.assertEqual(
            {path.resolve() for path in output_dir.iterdir()}, set(targets.values())
        )
        self.assertEqual(
            digests, {key: hashlib.sha256(data).hexdigest() for key, data in before.items()}
        )
        self.assertEqual(version, "0.3.2")

    def test_late_archive_validation_failure_preserves_all_five_archives(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        targets, _, _ = self.packager.build_bundle(fixture_root, output_dir)
        before = {key: path.read_bytes() for key, path in targets.items()}
        original_validate = self.packager.validate_archive
        calls = []

        def fail_on_last_archive(path, expected_names):
            calls.append(path)
            if len(calls) == 5:
                raise self.packager.PackagingError("simulated invalid archive")
            return original_validate(path, expected_names)

        with mock.patch.object(
            self.packager, "validate_archive", side_effect=fail_on_last_archive
        ), mock.patch.object(self.packager.os, "replace") as replace:
            with self.assertRaises(self.packager.PackagingError):
                self.packager.build_bundle(fixture_root, output_dir)
        replace.assert_not_called()
        self.assertEqual(len(calls), 5)
        self.assertEqual({key: path.read_bytes() for key, path in targets.items()}, before)
        self.assertEqual(
            {path.resolve() for path in output_dir.iterdir()}, set(targets.values())
        )

    def test_symlink_output_cannot_replace_unrelated_file(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        output_dir.mkdir()
        unrelated = Path(temporary.name) / "unrelated.zip"
        unrelated.write_bytes(b"preserve me")
        target = output_dir / "lihi-0.3.2.zip"
        target.symlink_to(unrelated)
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("not a regular file", process.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(unrelated.read_bytes(), b"preserve me")

    def test_unsupported_source_mcp_fields_are_rejected(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        path = fixture_root / "plugins/codex/lihi/.mcp.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["mcpServers"]["lihi"]["headers"] = {"Authorization": "Bearer example"}
        path.write_text(json.dumps(config), encoding="utf-8")
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("host-managed OAuth", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_archive_validator_rejects_unsafe_and_colliding_paths(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cases = (
            ("traversal.zip", ("../SKILL.md",)),
            ("backslash.zip", ("skill\\SKILL.md",)),
            ("collision.zip", ("skill/A.md", "skill/a.md")),
        )
        for filename, names in cases:
            path = root / filename
            with zipfile.ZipFile(str(path), "w") as archive:
                for name in names:
                    archive.writestr(name, b"x")
            with self.subTest(filename=filename), self.assertRaises(
                self.packager.PackagingError
            ):
                self.packager.validate_archive(path, set(names))


if __name__ == "__main__":
    unittest.main()
