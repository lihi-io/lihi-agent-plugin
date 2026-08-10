#!/usr/bin/env python3
"""Extract HTTP(S) URLs from human-facing Markdown text.

Input is read as UTF-8 from an optional file argument, or from stdin when the
argument is omitted or is ``-``. JSON output contains unique accepted URLs in
first-seen order, every accepted occurrence, and rejected candidates. Offsets
are zero-based Unicode code-point indices into the original input and ``end``
is exclusive.
"""

import argparse
from bisect import bisect_left, bisect_right
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit


URL_BODY_PATTERN = (
    r"(?:(?!\]\()[^\s<>\"'`，。；：！？、…“”‘’《》〈〉【】〔〕〖〗〘〙〚〛）］｝])+"
)
RAW_URL_RE = re.compile(r"https?://" + URL_BODY_PATTERN, re.IGNORECASE)
URL_RE = re.compile(
    r"(?<![A-Za-z0-9])https?://" + URL_BODY_PATTERN,
    re.IGNORECASE,
)
SCHEME_RE = re.compile(r"https?://", re.IGNORECASE)
TRAILING_PUNCTUATION = frozenset(
    ".,;:!?，。；：！？、…\"'”’»›》〉】〕〗〙〛"
)
CLOSING_TO_OPENING = {
    ")": "(",
    "]": "[",
    "}": "{",
    "）": "（",
    "］": "［",
    "｝": "｛",
}
MARKDOWN_WRAPPERS = ("***", "___", "**", "__", "~~", "*", "_")
MAX_URL_LENGTH = 2048
INVALID_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _fence_opener(line: str) -> Optional[Tuple[str, int]]:
    body = line.rstrip("\r\n")
    indent = len(body) - len(body.lstrip(" "))
    if indent > 3:
        return None

    rest = body[indent:]
    if not rest or rest[0] not in ("`", "~"):
        return None

    marker = rest[0]
    length = 0
    while length < len(rest) and rest[length] == marker:
        length += 1
    if length < 3:
        return None

    # A backtick fence cannot have a backtick in its info string.
    if marker == "`" and "`" in rest[length:]:
        return None
    return marker, length


def _is_fence_closer(line: str, marker: str, opening_length: int) -> bool:
    body = line.rstrip("\r\n")
    indent = len(body) - len(body.lstrip(" "))
    if indent > 3:
        return False

    rest = body[indent:]
    length = 0
    while length < len(rest) and rest[length] == marker:
        length += 1
    return length >= opening_length and not rest[length:].strip(" \t")


def _mask_fenced_code(text: str, visible: List[bool]) -> None:
    offset = 0
    active_fence = None  # type: Optional[Tuple[str, int]]

    for line in text.splitlines(keepends=True):
        line_end = offset + len(line)
        if active_fence is not None:
            visible[offset:line_end] = [False] * len(line)
            if _is_fence_closer(line, *active_fence):
                active_fence = None
        else:
            opener = _fence_opener(line)
            if opener is not None:
                visible[offset:line_end] = [False] * len(line)
                active_fence = opener
        offset = line_end


def _is_escaped(text: str, position: int) -> bool:
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def _backtick_run(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end - start


def _mask_inline_code(text: str, visible: List[bool]) -> None:
    position = 0
    while position < len(text):
        if not visible[position] or text[position] != "`" or _is_escaped(text, position):
            position += 1
            continue

        opening_length = _backtick_run(text, position)
        opening_end = position + opening_length
        search = opening_end
        closing_end = None  # type: Optional[int]

        while search < len(text):
            # Do not match an inline span across a fenced code block.
            if not visible[search]:
                break
            if text[search] != "`":
                search += 1
                continue

            closing_length = _backtick_run(text, search)
            if closing_length == opening_length:
                closing_end = search + closing_length
                break
            search += closing_length

        if closing_end is None:
            position = opening_end
            continue

        visible[position:closing_end] = [False] * (closing_end - position)
        position = closing_end


def _visible_positions(text: str, include_code: bool) -> List[bool]:
    visible = [True] * len(text)
    if include_code:
        return visible
    _mask_fenced_code(text, visible)
    _mask_inline_code(text, visible)
    return visible


def _mask_markdown_link_labels(text: str, visible: List[bool]) -> None:
    bracket_stack = []  # type: List[int]
    label_spans = []  # type: List[Tuple[int, int]]

    for position, character in enumerate(text):
        if not visible[position] or _is_escaped(text, position):
            continue
        if character == "[":
            bracket_stack.append(position)
            continue
        if character != "]" or not bracket_stack:
            continue

        opening = bracket_stack.pop()
        destination_open = position + 1
        if (
            destination_open < len(text)
            and visible[destination_open]
            and text[destination_open] == "("
        ):
            label_spans.append((opening + 1, position))

    for start, end in label_spans:
        visible[start:end] = [False] * (end - start)


def _trim_prose_suffix(candidate: str) -> str:
    end = len(candidate)
    excess_closers = {
        closer: candidate.count(closer) - candidate.count(opener)
        for closer, opener in CLOSING_TO_OPENING.items()
    }
    changed = True
    while end and changed:
        changed = False
        while end and candidate[end - 1] in TRAILING_PUNCTUATION:
            end -= 1
            changed = True

        if end and candidate[end - 1] in CLOSING_TO_OPENING:
            closer = candidate[end - 1]
            if excess_closers[closer] > 0:
                excess_closers[closer] -= 1
                end -= 1
                changed = True
    return candidate[:end]


def _is_valid_underscore_opener(text: str, position: int, length: int) -> bool:
    before = text[position - 1] if position else ""
    after_position = position + length
    after = text[after_position] if after_position < len(text) else ""
    return not (before.isalnum() and after.isalnum())


def _wrapper_positions(
    text: str,
    visible: List[bool],
) -> Dict[str, List[int]]:
    positions = {}  # type: Dict[str, List[int]]
    for wrapper in MARKDOWN_WRAPPERS:
        wrapper_positions = []  # type: List[int]
        position = 0
        while position < len(text):
            marker = text.find(wrapper, position)
            if marker < 0:
                break
            marker_end = marker + len(wrapper)
            marker_visible = all(visible[marker:marker_end])
            underscore_opener = wrapper[0] != "_" or _is_valid_underscore_opener(
                text, marker, len(wrapper)
            )
            if marker_visible and not _is_escaped(text, marker) and underscore_opener:
                wrapper_positions.append(marker)
            position = marker_end
        positions[wrapper] = wrapper_positions
    return positions


def _has_unclosed_wrapper(
    start: int,
    wrapper: str,
    wrapper_positions: Dict[str, List[int]],
    line_breaks: List[int],
) -> bool:
    break_index = bisect_left(line_breaks, start)
    line_start = line_breaks[break_index - 1] + 1 if break_index else 0
    positions = wrapper_positions[wrapper]
    first = bisect_left(positions, line_start)
    last = bisect_right(positions, start - len(wrapper))
    return (last - first) % 2 == 1


def _trim_candidate(
    start: int,
    candidate: str,
    wrapper_positions: Dict[str, List[int]],
    line_breaks: List[int],
) -> str:
    candidate = _trim_prose_suffix(candidate)
    while candidate:
        before = candidate
        for wrapper in MARKDOWN_WRAPPERS:
            if candidate.endswith(wrapper) and _has_unclosed_wrapper(
                start, wrapper, wrapper_positions, line_breaks
            ):
                candidate = _trim_prose_suffix(candidate[: -len(wrapper)])
                break
        if candidate == before:
            break
    return candidate


def _is_identifier_underscore(text: str, start: int, candidate: str) -> bool:
    if start < 2 or text[start - 1] != "_":
        return False
    if not (text[start - 2].isalnum() or text[start - 2] == "_"):
        return False
    for wrapper in ("___", "__", "_"):
        wrapper_start = start - len(wrapper)
        if (
            wrapper_start >= 0
            and text[wrapper_start:start] == wrapper
            and candidate.endswith(wrapper)
            and _is_valid_underscore_opener(text, wrapper_start, len(wrapper))
        ):
            return False
    return True


def _authority_userinfo_end(candidate: str) -> Optional[int]:
    authority_start = candidate.find("://") + 3
    if authority_start < 3:
        return None
    delimiters = []  # type: List[int]
    for delimiter in "/?#":
        position = candidate.find(delimiter, authority_start)
        if position >= 0:
            delimiters.append(position)
    authority_end = min(delimiters) if delimiters else len(candidate)
    userinfo_end = candidate.rfind("@", authority_start, authority_end)
    return userinfo_end if userinfo_end >= authority_start else None


def _redact_credentials(candidate: str, userinfo_end: int) -> str:
    authority_start = candidate.find("://") + 3
    if authority_start < 3:
        return "[credential-bearing URL redacted]"
    return candidate[:authority_start] + "[redacted]@" + candidate[userinfo_end + 1 :]


def _invalid_url_reason(candidate: str) -> Optional[str]:
    if len(candidate) > MAX_URL_LENGTH:
        return "url_too_long"
    if (
        "\\" in candidate
        or INVALID_PERCENT_ESCAPE_RE.search(candidate) is not None
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate)
    ):
        return "invalid_url"

    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return "invalid_url"
        # Accessing port performs urllib's numeric and range validation.
        parsed.port
    except ValueError:
        return "invalid_url"
    return None


def _credential_rejections(
    text: str,
    wrapper_positions: Dict[str, List[int]],
    line_breaks: List[int],
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    rejected = []  # type: List[Dict[str, Any]]
    rejected_starts = set()  # type: Set[int]

    # Inspect every scheme occurrence independently. Eligibility boundaries and
    # code masking must never let embedded user information bypass redaction.
    scheme_matches = list(SCHEME_RE.finditer(text))
    for index, scheme_match in enumerate(scheme_matches):
        start = scheme_match.start()
        candidate_limit = (
            scheme_matches[index + 1].start()
            if index + 1 < len(scheme_matches)
            else len(text)
        )
        raw_match = RAW_URL_RE.match(text, start, candidate_limit)
        if raw_match is None:
            continue
        candidate = _trim_candidate(
            start,
            raw_match.group(0),
            wrapper_positions,
            line_breaks,
        )
        if not candidate:
            continue

        userinfo_end = _authority_userinfo_end(candidate)
        if userinfo_end is None:
            continue

        end = start + len(candidate)
        rejected.append(
            {
                "url": _redact_credentials(candidate, userinfo_end),
                "start": start,
                "end": end,
                "reason": "embedded_credentials",
                "redacted": True,
            }
        )
        rejected_starts.add(start)

    return rejected, rejected_starts


def detect_urls(text: str, include_code: bool = False) -> Dict[str, Any]:
    code_visible = _visible_positions(text, include_code)
    eligible_visible = code_visible.copy()
    _mask_markdown_link_labels(text, eligible_visible)
    wrapper_positions = _wrapper_positions(text, code_visible)
    line_breaks = [index for index, character in enumerate(text) if character in "\r\n"]
    urls = []  # type: List[str]
    seen = set()  # type: Set[str]
    occurrences = []  # type: List[Dict[str, Any]]
    rejected, credential_starts = _credential_rejections(
        text,
        wrapper_positions,
        line_breaks,
    )
    credential_spans = [
        (item["start"], item["end"])
        for item in rejected
    ]
    credential_span_starts = [start for start, _ in credential_spans]

    for match in URL_RE.finditer(text):
        start = match.start()
        raw_candidate = match.group(0)
        identifier_underscore = _is_identifier_underscore(text, start, raw_candidate)
        candidate = _trim_candidate(
            start,
            raw_candidate,
            wrapper_positions,
            line_breaks,
        )
        if not candidate:
            continue
        end = start + len(candidate)

        userinfo_end = _authority_userinfo_end(candidate)
        if userinfo_end is not None:
            if start not in credential_starts:
                rejected.append(
                    {
                        "url": _redact_credentials(candidate, userinfo_end),
                        "start": start,
                        "end": end,
                        "reason": "embedded_credentials",
                        "redacted": True,
                    }
                )
                credential_starts.add(start)
            continue

        overlap_index = bisect_left(credential_span_starts, end)
        if (
            overlap_index
            and credential_spans[overlap_index - 1][1] > start
        ):
            continue

        if not eligible_visible[start] or identifier_underscore:
            continue

        invalid_reason = _invalid_url_reason(candidate)
        if invalid_reason is not None:
            rejected.append(
                {
                    "url": candidate,
                    "start": start,
                    "end": end,
                    "reason": invalid_reason,
                }
            )
            continue

        occurrences.append({"url": candidate, "start": start, "end": end})
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)

    rejected.sort(key=lambda item: (item["start"], item["end"]))
    return {
        "offset_unit": "unicode_code_points",
        "include_code": include_code,
        "urls": urls,
        "occurrences": occurrences,
        "rejected": rejected,
    }


def _read_input(path: Optional[str]) -> str:
    if path is None or path == "-":
        return sys.stdin.buffer.read().decode("utf-8")
    with Path(path).open("r", encoding="utf-8", newline="") as input_file:
        return input_file.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file",
        nargs="?",
        help="UTF-8 input file; omit or use - to read stdin",
    )
    parser.add_argument(
        "--include-code",
        action="store_true",
        help="include URLs inside Markdown fenced and inline code",
    )
    args = parser.parse_args()

    try:
        text = _read_input(args.file)
    except (OSError, UnicodeError) as error:
        parser.error(str(error))

    json.dump(detect_urls(text, args.include_code), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
