import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
DEVELOP_ENDPOINT = "https://app.lihidev.com/mcp/v1/tools"
PRODUCTION_SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)
DEVELOP_SKILLS = tuple(name + "-dev" for name in PRODUCTION_SKILLS)


def load_packager(repo_root):
    path = repo_root / "scripts/package_develop_bundle.py"
    spec = importlib.util.spec_from_file_location("package_develop_bundle", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree_hash(root, relative_paths):
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = root / relative
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or "__pycache__" in candidate.parts:
                continue
            digest.update(str(candidate.relative_to(root)).encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()


class DevelopPackagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.packager = load_packager(cls.repo_root)
        cls.source_paths = (
            Path("plugins"),
            Path(".agents"),
            Path(".claude-plugin"),
            Path("docs"),
            Path("README.md"),
            Path("README.zh-TW.md"),
        )
        before = tree_hash(cls.repo_root, cls.source_paths)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary.name) / "output"
        command = [
            sys.executable,
            str(cls.repo_root / "scripts/package_develop_bundle.py"),
            "--output-dir",
            str(cls.output_dir),
            "--build-number",
            "42",
            "--commit",
            "abcdef1",
        ]
        cls.process = subprocess.run(
            command,
            cwd=str(cls.repo_root),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cls.source_hash_after = tree_hash(cls.repo_root, cls.source_paths)
        cls.source_hash_before = before
        cls.version = "0.3.2-develop.42"
        cls.codex_version = cls.version + "+codex.42"
        cls.package = cls.output_dir / ("lihi-agent-" + cls.version)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_subprocess_build_succeeds_without_modifying_source(self):
        self.assertEqual(self.process.returncode, 0, self.process.stderr)
        self.assertIn("Version: " + self.version, self.process.stdout)
        self.assertTrue(self.package.is_dir())
        self.assertEqual(self.source_hash_before, self.source_hash_after)

    def test_version_helpers_enforce_shared_semver_core(self):
        self.assertEqual(
            self.packager.semantic_version_core(
                "0.3.2+codex.cache", Path("manifest.json")
            ),
            "0.3.2",
        )
        self.assertEqual(
            self.packager.codex_develop_version(self.version),
            self.codex_version,
        )
        with self.assertRaises(self.packager.PackagingError):
            self.packager.semantic_version_core("0.3", Path("manifest.json"))
        with self.assertRaises(self.packager.PackagingError):
            self.packager.codex_develop_version("0.3.2")
        with self.assertRaises(self.packager.PackagingError):
            self.packager.build_develop_version(self.repo_root, "bad")

    def test_production_build_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            for index, relative_path in enumerate(self.packager.PLUGIN_MANIFESTS):
                path = fixture_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                version = "0.3.2+codex.cache" if index == 0 else "0.3.2"
                path.write_text(
                    json.dumps({"version": version}) + "\n",
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(
                self.packager.PackagingError,
                "without build metadata",
            ):
                self.packager.build_develop_version(fixture_root, "42")

    def test_develop_marketplaces_and_manifests_are_isolated(self):
        codex_marketplace = self.read_json(
            self.package / ".agents/plugins/marketplace.json"
        )
        claude_marketplace = self.read_json(
            self.package / ".claude-plugin/marketplace.json"
        )
        self.assertEqual(codex_marketplace["name"], "lihi-dev")
        self.assertEqual(claude_marketplace["name"], "lihi-dev")
        self.assertEqual(codex_marketplace["plugins"][0]["name"], "lihi-dev")
        self.assertEqual(claude_marketplace["plugins"][0]["name"], "lihi-dev")
        self.assertEqual(
            codex_marketplace["plugins"][0]["source"]["path"],
            "./plugins/codex/lihi-dev",
        )
        self.assertEqual(
            claude_marketplace["plugins"][0]["source"],
            "./plugins/claude/lihi-dev",
        )

        codex_manifest = self.read_json(
            self.package
            / "plugins/codex/lihi-dev/.codex-plugin/plugin.json"
        )
        claude_manifest = self.read_json(
            self.package
            / "plugins/claude/lihi-dev/.claude-plugin/plugin.json"
        )
        self.assertEqual(codex_manifest["name"], "lihi-dev")
        self.assertEqual(codex_manifest["version"], self.codex_version)
        self.assertEqual(claude_manifest["name"], "lihi-dev")
        self.assertEqual(claude_manifest["version"], self.version)
        for manifest in (codex_manifest, claude_manifest):
            self.assertIn("automatic URL shortening", manifest["description"])

    def test_each_develop_host_has_four_skills_and_one_mcp(self):
        for host in ("codex", "claude"):
            root = self.package / "plugins" / host / "lihi-dev"
            self.assertFalse((self.package / "plugins" / host / "lihi").exists())
            self.assertEqual(
                {path.name for path in (root / "skills").iterdir() if path.is_dir()},
                set(DEVELOP_SKILLS),
            )
            config = self.read_json(root / ".mcp.json")
            self.assertEqual(list(config["mcpServers"]), ["lihi-dev"])
            self.assertEqual(
                config["mcpServers"]["lihi-dev"]["url"], DEVELOP_ENDPOINT
            )
            for name in DEVELOP_SKILLS:
                content = (root / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("\nname: {0}\n".format(name), content)

    def test_codex_develop_metadata_has_all_four_dependencies(self):
        root = self.package / "plugins/codex/lihi-dev/skills"
        for name in DEVELOP_SKILLS:
            metadata = (root / name / "agents/openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("$" + name, metadata)
            self.assertIn('value: "lihi-dev"', metadata)
            self.assertIn(DEVELOP_ENDPOINT, metadata)

    def test_build_metadata_uses_authoritative_list_and_compatibility_alias(self):
        metadata = self.read_json(self.package / "DEVELOP_BUILD.json")
        self.assertEqual(metadata["version"], self.version)
        self.assertNotIn("+codex.", metadata["version"])
        self.assertEqual(metadata["commit"], "abcdef1")
        self.assertEqual(metadata["skill_names"], list(DEVELOP_SKILLS))
        self.assertEqual(metadata["skill_name"], metadata["skill_names"][0])
        self.assertEqual(metadata["plugins"][0]["skill_names"], list(DEVELOP_SKILLS))
        self.assertEqual(
            metadata["plugins"][0]["skill_name"],
            metadata["plugins"][0]["skill_names"][0],
        )
        self.assertEqual(metadata["mcp_endpoint"], DEVELOP_ENDPOINT)

    def test_artifact_contains_only_develop_runtime_origin_and_identities(self):
        for path in sorted(self.package.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml"}:
                continue
            content = path.read_text(encoding="utf-8")
            if path.name != "DEVELOP_BUILD.json":
                self.assertNotIn(PRODUCTION_ENDPOINT, content, str(path))
                self.assertNotIn("lihi@lihi", content, str(path))
                self.assertNotIn("lihi-switch-workgroup", content, str(path))
                self.assertNotIn("account_group", content, str(path))
                self.assertNotIn("supports_custom_slug", content, str(path))
                self.assertNotIn("site_create.domain", content, str(path))

    def test_develop_guides_are_rewritten_for_local_artifact(self):
        english = (self.package / "README.md").read_text(encoding="utf-8")
        chinese = (self.package / "README.zh-TW.md").read_text(encoding="utf-8")
        for content in (english, chinese):
            self.assertIn("lihi-dev@lihi-dev", content)
            self.assertIn("codex plugin marketplace add .", content)
            self.assertIn("claude plugin marketplace add .", content)
            self.assertIn(DEVELOP_ENDPOINT, content)
        self.assertFalse(
            (self.package / "docs/openai-platform-packaging.md").exists()
        )

    def test_packager_excludes_caches_and_preserves_detector_mode(self):
        self.assertFalse(any("__pycache__" in path.parts for path in self.package.rglob("*")))
        self.assertFalse(any(path.suffix == ".pyc" for path in self.package.rglob("*")))
        source = self.repo_root / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py"
        packaged = (
            self.package
            / "plugins/codex/lihi-dev/skills/lihi-shorten-dev/scripts/detect_urls.py"
        )
        self.assertEqual(source.read_bytes(), packaged.read_bytes())
        self.assertEqual(bool(source.stat().st_mode & 0o111), bool(packaged.stat().st_mode & 0o111))

    def test_source_runtime_remains_production_only(self):
        for host in ("codex", "claude"):
            root = self.repo_root / "plugins" / host / "lihi"
            config = self.read_json(root / ".mcp.json")
            self.assertEqual(list(config["mcpServers"]), ["lihi"])
            self.assertEqual(config["mcpServers"]["lihi"]["url"], PRODUCTION_ENDPOINT)
            self.assertEqual(
                {path.name for path in (root / "skills").iterdir() if path.is_dir()},
                set(PRODUCTION_SKILLS),
            )


if __name__ == "__main__":
    unittest.main()
