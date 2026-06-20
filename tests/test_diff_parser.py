"""Tests for diff_parser module."""

import pytest
from review_agent.diff_parser import parse_diff, group_hunks_by_file, filter_hunks_by_language
from review_agent.models import DiffHunk

# Each diff string must have EXACT hunk line counts for unidiff.
# Format: @@ -<src_start>,<src_count> +<tgt_start>,<tgt_count> @@
# Line counts include context lines.

SAMPLE_DIFF_PY = (
    "diff --git a/review_agent/utils.py b/review_agent/utils.py\n"
    "index abc1234..def5678 100644\n"
    "--- a/review_agent/utils.py\n"
    "+++ b/review_agent/utils.py\n"
    "@@ -10,6 +10,8 @@ def process_items(items):\n"
    "     result = []\n"
    "     for i in range(len(items)):\n"
    "         item = items[i]\n"
    "-        if item > 0:\n"
    "+        if item >= 0:\n"
    "             result.append(item)\n"
    "+    if not result:\n"
    "+        return None\n"
    "     return result\n"
)

SAMPLE_DIFF_JS = (
    "diff --git a/frontend/app.js b/frontend/app.js\n"
    "index 111aaaa..222bbbb 100644\n"
    "--- a/frontend/app.js\n"
    "+++ b/frontend/app.js\n"
    "@@ -1,4 +1,6 @@\n"
    " function fetchData(url) {\n"
    "-    return fetch(url);\n"
    '+    if (!url) throw new Error("URL required");\n'
    "+    return fetch(url).then(r => r.json());\n"
    " }\n"
    " \n"
    "+module.exports = { fetchData };\n"
)

SAMPLE_DIFF = SAMPLE_DIFF_PY + SAMPLE_DIFF_JS


def test_parse_single_py_diff():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    assert len(hunks) >= 1
    assert hunks[0].language == "python"


def test_parse_diff_returns_hunks():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    assert len(hunks) >= 1


def test_parse_diff_detects_python_language():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    by_file = group_hunks_by_file(hunks)
    py_file = next((k for k in by_file if k.endswith(".py")), None)
    assert py_file is not None
    assert by_file[py_file][0].language == "python"


def test_parse_diff_added_removed_lines():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    py_hunks = [h for h in hunks if h.file_path.endswith(".py")]
    assert py_hunks
    hunk = py_hunks[0]
    added = hunk.added_lines
    removed = hunk.removed_lines
    assert any(">= 0" in l.value for l in added)
    assert any("> 0" in l.value for l in removed)


def test_parse_empty_diff():
    result = parse_diff("")
    assert result == []


def test_parse_invalid_diff():
    result = parse_diff("not a real diff at all\n\n\n")
    assert isinstance(result, list)


def test_group_hunks_by_file():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    grouped = group_hunks_by_file(hunks)
    assert isinstance(grouped, dict)
    assert len(grouped) >= 1


def test_filter_hunks_by_language():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    py_only = filter_hunks_by_language(hunks, {"python"})
    assert all(h.language == "python" for h in py_only)
    assert len(py_only) >= 1


def test_filter_excludes_other_languages():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    js_only = filter_hunks_by_language(hunks, {"javascript"})
    assert len(js_only) == 0


def test_hunk_text_contains_diff_lines():
    hunks = parse_diff(SAMPLE_DIFF_PY)
    py_hunk = next(h for h in hunks if h.language == "python")
    text = py_hunk.hunk_text
    assert "+" in text or "-" in text
