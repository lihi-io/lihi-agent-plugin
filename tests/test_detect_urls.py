import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = (
    ROOT / "plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py",
    ROOT / "plugins/claude/lihi/skills/lihi-shorten/scripts/detect_urls.py",
)


def load_detector(path: Path):
    spec = importlib.util.spec_from_file_location(f"detect_urls_{path.parts[-5]}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load detector: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DetectUrlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.detectors = tuple(load_detector(path) for path in SCRIPT_PATHS)

    def assert_same_result(self, text: str, include_code: bool = False) -> Dict[str, object]:
        results = tuple(
            detector.detect_urls(text, include_code=include_code)
            for detector in self.detectors
        )
        self.assertEqual(results[0], results[1])
        return results[0]

    def test_bundled_scripts_are_identical(self) -> None:
        self.assertEqual(SCRIPT_PATHS[0].read_bytes(), SCRIPT_PATHS[1].read_bytes())
        ast.parse(SCRIPT_PATHS[0].read_text(encoding="utf-8"), feature_version=(3, 8))
        ast.parse(Path(__file__).read_text(encoding="utf-8"), feature_version=(3, 8))

    def test_chinese_adjacency_punctuation_duplicates_and_offsets(self) -> None:
        text = (
            "請看https://example.com/a_(b). "
            "再看（https://example.com/活動）及https://example.com/a_(b)。"
        )
        result = self.assert_same_result(text)

        self.assertEqual(
            result["urls"],
            ["https://example.com/a_(b)", "https://example.com/活動"],
        )
        self.assertEqual(len(result["occurrences"]), 3)
        for occurrence in result["occurrences"]:
            start = occurrence["start"]
            end = occurrence["end"]
            self.assertEqual(text[start:end], occurrence["url"])

    def test_markdown_code_is_ignored_unless_requested(self) -> None:
        text = (
            "[活動](https://example.com/live)，"
            "`https://example.com/inline`\n"
            "```text\nhttps://example.com/fenced\n```\n"
        )
        default_result = self.assert_same_result(text)
        self.assertEqual(default_result["urls"], ["https://example.com/live"])

        code_result = self.assert_same_result(text, include_code=True)
        self.assertEqual(
            code_result["urls"],
            [
                "https://example.com/live",
                "https://example.com/inline",
                "https://example.com/fenced",
            ],
        )

    def test_credentials_are_rejected_even_in_excluded_code(self) -> None:
        text = (
            "正常 https://example.com/ok "
            "`curl https://alice:secret@example.com/private https://example.com/code`\n"
            "```text\n"
            "https://bob:password@example.org/admin\n"
            "https://example.org/code\n"
            "```\n"
            "token_https://carol:hidden@example.net/id"
        )
        default_result = self.assert_same_result(text)
        self.assertEqual(default_result["urls"], ["https://example.com/ok"])
        self.assertEqual(
            [item["reason"] for item in default_result["rejected"]],
            ["embedded_credentials", "embedded_credentials", "embedded_credentials"],
        )

        include_code_result = self.assert_same_result(text, include_code=True)
        self.assertEqual(
            include_code_result["urls"],
            [
                "https://example.com/ok",
                "https://example.com/code",
                "https://example.org/code",
            ],
        )
        serialized = json.dumps(include_code_result, ensure_ascii=False)
        for credential in ("alice", "secret", "bob", "password", "carol", "hidden"):
            self.assertNotIn(credential, serialized)

    def test_credential_scan_does_not_require_a_leading_boundary(self) -> None:
        text = "prefixhttps://alice:secret@example.com/private"
        result = self.assert_same_result(text)

        self.assertEqual(result["urls"], [])
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["rejected"][0]["reason"], "embedded_credentials")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("alice", serialized)
        self.assertNotIn("secret", serialized)

        nested_text = (
            "https://safe.example/pathhttps://bob:password@example.org/private"
        )
        nested_result = self.assert_same_result(nested_text)
        self.assertEqual(nested_result["urls"], [])
        self.assertEqual(
            [item["reason"] for item in nested_result["rejected"]],
            ["embedded_credentials"],
        )
        serialized = json.dumps(nested_result, ensure_ascii=False)
        self.assertNotIn("bob", serialized)
        self.assertNotIn("password", serialized)

    def test_markdown_url_label_is_preserved_and_destination_is_detected(self) -> None:
        text = "[https://example.com](https://example.com)"
        result = self.assert_same_result(text)

        self.assertEqual(result["urls"], ["https://example.com"])
        self.assertEqual(result["rejected"], [])
        self.assertEqual(len(result["occurrences"]), 1)
        occurrence = result["occurrences"][0]
        self.assertEqual(occurrence["start"], text.rindex("https://"))
        self.assertEqual(text[occurrence["start"] : occurrence["end"]], occurrence["url"])

        credential_text = (
            "[https://alice:secret@example.com](https://example.com/safe)"
        )
        credential_result = self.assert_same_result(credential_text)
        self.assertEqual(credential_result["urls"], ["https://example.com/safe"])
        self.assertEqual(
            [item["reason"] for item in credential_result["rejected"]],
            ["embedded_credentials"],
        )
        serialized = json.dumps(credential_result, ensure_ascii=False)
        self.assertNotIn("alice", serialized)
        self.assertNotIn("secret", serialized)

    def test_markdown_emphasis_is_not_part_of_the_url(self) -> None:
        text = (
            "**https://example.com/bold** "
            "_https://example.com/italic_ "
            "~~https://example.com/old~~ "
            "**Learn more at https://example.com/more** "
            "_詳情 https://example.com/details_ "
            "**[click](https://example.com/click)** "
            "**_https://example.com/nested_** "
            "_**https://example.com/nested2**_ "
            "~~**https://example.com/nested3**~~ "
            "foo_https://example.com/not-a-boundary "
            "foo_https://example.com/not-a-boundary_"
        )
        result = self.assert_same_result(text)
        self.assertEqual(
            result["urls"],
            [
                "https://example.com/bold",
                "https://example.com/italic",
                "https://example.com/old",
                "https://example.com/more",
                "https://example.com/details",
                "https://example.com/click",
                "https://example.com/nested",
                "https://example.com/nested2",
                "https://example.com/nested3",
            ],
        )
        for occurrence in result["occurrences"]:
            self.assertEqual(
                text[occurrence["start"] : occurrence["end"]],
                occurrence["url"],
            )

    def test_credentials_and_invalid_urls_are_rejected(self) -> None:
        text = (
            "https://user:secret@example.com/private "
            "https://second:password@[::1 "
            "https://[::1"
        )
        result = self.assert_same_result(text)

        self.assertEqual(result["urls"], [])
        self.assertEqual(
            [item["reason"] for item in result["rejected"]],
            ["embedded_credentials", "embedded_credentials", "invalid_url"],
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("user", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("second", serialized)
        self.assertNotIn("password", serialized)
        self.assertEqual(
            result["rejected"][0]["url"],
            "https://[redacted]@example.com/private",
        )
        self.assertTrue(result["rejected"][0]["redacted"])
        self.assertEqual(result["rejected"][1]["url"], "https://[redacted]@[::1")

    def test_url_contract_boundaries_are_rejected_locally(self) -> None:
        base = "https://example.com/"
        maximum_length_url = base + "x" * (2048 - len(base))
        overlong_url = maximum_length_url + "x"
        text = " ".join(
            [
                maximum_length_url,
                "https://example.com:abc/path",
                "https://example.com:99999/path",
                "https://example.com/%ZZ",
                "https://example.com\\evil",
                "https://example.com/control\x00value",
                overlong_url,
            ]
        )
        result = self.assert_same_result(text)

        self.assertEqual(result["urls"], [maximum_length_url])
        self.assertEqual(
            [item["reason"] for item in result["rejected"]],
            [
                "invalid_url",
                "invalid_url",
                "invalid_url",
                "invalid_url",
                "invalid_url",
                "url_too_long",
            ],
        )
        for occurrence in result["occurrences"]:
            self.assertEqual(text[occurrence["start"] : occurrence["end"]], occurrence["url"])

    def test_large_markdown_inputs_do_not_rescan_quadratically(self) -> None:
        wrapped_count = 8000
        wrapped_text = " ".join(
            f"**https://example.com/{index}**" for index in range(wrapped_count)
        )
        unmatched_closers = "https://example.com/end" + ")" * 20000
        adjacent_schemes = "xhttps://" * 8000

        started = time.perf_counter()
        wrapped_result = self.detectors[0].detect_urls(wrapped_text)
        closer_result = self.detectors[0].detect_urls(unmatched_closers)
        scheme_result = self.detectors[0].detect_urls(adjacent_schemes)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(wrapped_result["urls"]), wrapped_count)
        self.assertEqual(closer_result["urls"], ["https://example.com/end"])
        self.assertEqual(scheme_result["rejected"], [])
        self.assertLess(elapsed, 3.0)

    def test_cli_supports_stdin_and_utf8_file(self) -> None:
        text = "潤飾後請參考：https://example.com/產品。"
        for path in SCRIPT_PATHS:
            stdin_run = subprocess.run(
                [sys.executable, str(path)],
                input=text,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(stdin_run.stdout)["urls"], ["https://example.com/產品"])

            with tempfile.NamedTemporaryFile("w", encoding="utf-8") as input_file:
                input_file.write(text)
                input_file.flush()
                file_run = subprocess.run(
                    [sys.executable, str(path), input_file.name],
                    text=True,
                    capture_output=True,
                    check=True,
                )
            self.assertEqual(json.loads(file_run.stdout)["urls"], ["https://example.com/產品"])

    def test_file_offsets_preserve_crlf(self) -> None:
        text = "第一行\r\n連結：https://example.com/crlf\r\n"
        expected_start = text.index("https://")
        for path in SCRIPT_PATHS:
            with tempfile.NamedTemporaryFile("wb") as input_file:
                input_file.write(text.encode("utf-8"))
                input_file.flush()
                file_run = subprocess.run(
                    [sys.executable, str(path), input_file.name],
                    text=True,
                    capture_output=True,
                    check=True,
                )
            result = json.loads(file_run.stdout)
            self.assertEqual(result["occurrences"][0]["start"], expected_start)


if __name__ == "__main__":
    unittest.main()
