import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)


def load_packager(repo_root):
    path = repo_root / "scripts/package_production_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "package_production_bundle", str(path)
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
            if not candidate.is_file() or "__pycache__" in candidate.parts:
                continue
            digest.update(str(candidate.relative_to(root)).encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()


def copy_fixture(source_root, destination):
    for relative_path in (
        Path(".agents"),
        Path(".claude-plugin"),
        Path("plugins/codex/lihi"),
        Path("plugins/claude/lihi"),
    ):
        shutil.copytree(
            source_root / relative_path,
            destination / relative_path,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    for relative_path in (
        Path("README.md"),
        Path("README.zh-TW.md"),
        Path("scripts/package_production_bundle.py"),
    ):
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative_path, target)


def run_packager(repo_root, output_dir):
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/package_production_bundle.py"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=str(repo_root),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class ProductionPackagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.packager = load_packager(cls.repo_root)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.temporary.name) / "repo"
        copy_fixture(cls.repo_root, cls.fixture_root)
        cls.source_paths = (
            Path(".agents"),
            Path(".claude-plugin"),
            Path("plugins"),
            Path("README.md"),
            Path("README.zh-TW.md"),
        )
        cls.source_hash_before = tree_hash(cls.fixture_root, cls.source_paths)
        cls.output_dir = Path(cls.temporary.name) / "output"
        cls.process = run_packager(cls.fixture_root, cls.output_dir)
        cls.source_hash_after = tree_hash(cls.fixture_root, cls.source_paths)
        cls.version = "0.3.2"
        cls.package = cls.output_dir / "lihi-agent-0.3.2"

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fresh_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        fixture_root = Path(temporary.name) / "repo"
        copy_fixture(self.repo_root, fixture_root)
        return temporary, fixture_root

    def read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_subprocess_builds_installable_production_bundle_without_source_changes(self):
        self.assertEqual(self.process.returncode, 0, self.process.stderr)
        self.assertIn("Version: " + self.version, self.process.stdout)
        self.assertIn("Plugin: lihi@lihi", self.process.stdout)
        self.assertIn("MCP endpoint: " + PRODUCTION_ENDPOINT, self.process.stdout)
        self.assertTrue(self.package.is_dir())
        self.assertEqual(self.source_hash_before, self.source_hash_after)
        self.assertEqual(
            {path.name for path in self.package.iterdir()},
            {".agents", ".claude-plugin", "plugins", "README.md", "README.zh-TW.md"},
        )
        self.assertFalse((self.package / "docs").exists())

    def test_marketplaces_and_manifests_keep_production_identity(self):
        codex_marketplace = self.read_json(
            self.package / ".agents/plugins/marketplace.json"
        )
        claude_marketplace = self.read_json(
            self.package / ".claude-plugin/marketplace.json"
        )
        for marketplace in (codex_marketplace, claude_marketplace):
            self.assertEqual(marketplace["name"], "lihi")
            self.assertEqual(marketplace["plugins"][0]["name"], "lihi")
        self.assertEqual(
            codex_marketplace["plugins"][0]["source"]["path"],
            "./plugins/codex/lihi",
        )
        self.assertEqual(
            claude_marketplace["plugins"][0]["source"],
            "./plugins/claude/lihi",
        )

        codex_manifest = self.read_json(
            self.package / "plugins/codex/lihi/.codex-plugin/plugin.json"
        )
        claude_manifest = self.read_json(
            self.package / "plugins/claude/lihi/.claude-plugin/plugin.json"
        )
        self.assertEqual(codex_manifest["name"], "lihi")
        self.assertEqual(claude_manifest["name"], "lihi")
        self.assertEqual(
            self.packager.semantic_version_core(
                codex_manifest["version"], Path("codex.json")
            ),
            self.version,
        )
        self.assertEqual(
            self.packager.semantic_version_core(
                claude_manifest["version"], Path("claude.json")
            ),
            self.version,
        )

    def test_packaged_guides_use_authoritative_repository(self):
        expected = "https://github.com/lihi-io/lihi-agent-plugin.git"
        for filename in ("README.md", "README.zh-TW.md"):
            content = (self.package / filename).read_text(encoding="utf-8")
            self.assertIn(expected, content)

    def test_both_hosts_share_production_mcp_and_skill_identities(self):
        for host in ("codex", "claude"):
            root = self.package / "plugins" / host / "lihi"
            self.assertEqual(
                {path.name for path in (root / "skills").iterdir() if path.is_dir()},
                set(SKILLS),
            )
            config = self.read_json(root / ".mcp.json")
            self.assertEqual(list(config["mcpServers"]), ["lihi"])
            self.assertEqual(config["mcpServers"]["lihi"]["url"], PRODUCTION_ENDPOINT)
            for skill_name in SKILLS:
                content = (root / "skills" / skill_name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("\nname: {0}\n".format(skill_name), content)

    def test_codex_metadata_keeps_production_dependencies(self):
        root = self.package / "plugins/codex/lihi/skills"
        for skill_name in SKILLS:
            metadata = (root / skill_name / "agents/openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("$" + skill_name, metadata)
            self.assertIn('value: "lihi"', metadata)
            self.assertIn(PRODUCTION_ENDPOINT, metadata)

    def test_package_contains_no_develop_identity_or_endpoint(self):
        for path in sorted(self.package.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {
                ".md",
                ".json",
                ".yaml",
                ".yml",
            }:
                continue
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("lihi-dev", content, str(path))
            self.assertNotIn("https://app.lihidev.com", content, str(path))
            self.assertNotIn("plugin_asdk_app_", content, str(path))

    def test_detector_bytes_and_executable_mode_are_preserved(self):
        source = (
            self.repo_root
            / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
        )
        packaged = (
            self.package
            / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
        )
        self.assertEqual(source.read_bytes(), packaged.read_bytes())
        self.assertEqual(
            bool(source.stat().st_mode & 0o111),
            bool(packaged.stat().st_mode & 0o111),
        )

    def test_version_mismatch_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_root / "plugins/claude/lihi/.claude-plugin/plugin.json"
        manifest = self.read_json(manifest_path)
        manifest["version"] = "0.4.0"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("must share one major.minor.patch version", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_production_build_metadata_fails_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        manifest_path = fixture_root / "plugins/codex/lihi/.codex-plugin/plugin.json"
        manifest = self.read_json(manifest_path)
        manifest["version"] = "0.3.2+codex.cache"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("without build metadata", process.stderr)
        self.assertFalse(output_dir.exists())

    def test_existing_output_is_preserved_and_not_overwritten(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "output"
        target = output_dir / "lihi-agent-0.3.2"
        target.mkdir(parents=True)
        marker = target / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("already exists", process.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_symbolic_link_is_rejected_before_output(self):
        temporary, fixture_root = self.fresh_fixture()
        self.addCleanup(temporary.cleanup)
        link = fixture_root / "plugins/codex/lihi/linked-readme"
        link.symlink_to(fixture_root / "README.md")
        output_dir = Path(temporary.name) / "output"
        process = run_packager(fixture_root, output_dir)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Symbolic links are not allowed", process.stderr)
        self.assertFalse(any(output_dir.glob("lihi-agent-*")))


if __name__ == "__main__":
    unittest.main()
