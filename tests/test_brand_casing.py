import re
import subprocess
import unittest
from pathlib import Path


BRAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])lihi(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".json", ".md", ".py", ".yaml", ".yml"}


class BrandCasingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]

    def test_brand_name_is_lowercase_in_tracked_text(self):
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=str(self.repo_root),
            check=True,
            stdout=subprocess.PIPE,
        )

        for relative_path in result.stdout.decode("utf-8").split("\0"):
            if not relative_path:
                continue
            path = self.repo_root / relative_path
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8")
            for match in BRAND_PATTERN.finditer(content):
                with self.subTest(path=relative_path, offset=match.start()):
                    self.assertEqual(match.group(0), "lihi")

    def test_brand_pattern_handles_chinese_adjacency(self):
        lowercase_text = "使用lihi縮短"
        non_lowercase_text = "使用" + "lihi".upper() + "縮短"

        lowercase_match = BRAND_PATTERN.search(lowercase_text)
        non_lowercase_match = BRAND_PATTERN.search(non_lowercase_text)

        self.assertIsNotNone(lowercase_match)
        self.assertEqual(lowercase_match.group(0), "lihi")
        self.assertIsNotNone(non_lowercase_match)
        self.assertNotEqual(non_lowercase_match.group(0), "lihi")


if __name__ == "__main__":
    unittest.main()
