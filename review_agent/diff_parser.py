"""Diff parser — converts raw unified diff text into DiffHunk objects."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import unidiff

from review_agent.models import DiffHunk, DiffLine

logger = logging.getLogger(__name__)

# Map file extensions → language names
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".tf": "terraform",
    ".sql": "sql",
}


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext, "unknown")


def parse_diff(raw_diff: str) -> list[DiffHunk]:
    """Parse a raw unified diff string into a list of DiffHunk objects.

    Args:
        raw_diff: The raw unified diff text (e.g., from GitHub API).

    Returns:
        A flat list of DiffHunk objects, one per hunk in the diff.
    """
    if not raw_diff or not raw_diff.strip():
        return []

    try:
        patch_set = unidiff.PatchSet(raw_diff)
    except unidiff.UnidiffParseError as exc:
        logger.warning("Failed to parse diff: %s", exc)
        return []

    hunks: list[DiffHunk] = []

    for patched_file in patch_set:
        # Skip binary or deleted files
        if patched_file.is_binary_file:
            continue

        file_path = patched_file.path
        language = _detect_language(file_path)

        for hunk in patched_file:
            diff_lines: list[DiffLine] = []

            for line in hunk:
                if line.is_added:
                    line_type = "added"
                elif line.is_removed:
                    line_type = "removed"
                else:
                    line_type = "context"

                diff_lines.append(
                    DiffLine(
                        line_type=line_type,
                        source_line_no=line.source_line_no,
                        target_line_no=line.target_line_no,
                        value=line.value,
                    )
                )

            hunks.append(
                DiffHunk(
                    file_path=file_path,
                    language=language,
                    source_start=hunk.source_start,
                    source_length=hunk.source_length,
                    target_start=hunk.target_start,
                    target_length=hunk.target_length,
                    lines=diff_lines,
                )
            )

    logger.debug("Parsed %d hunks from diff (%d bytes)", len(hunks), len(raw_diff))
    return hunks


def group_hunks_by_file(hunks: list[DiffHunk]) -> dict[str, list[DiffHunk]]:
    """Group a flat list of DiffHunk objects by file path."""
    result: dict[str, list[DiffHunk]] = {}
    for hunk in hunks:
        result.setdefault(hunk.file_path, []).append(hunk)
    return result


def filter_hunks_by_language(
    hunks: list[DiffHunk], languages: set[str]
) -> list[DiffHunk]:
    """Return only hunks whose detected language is in the given set."""
    return [h for h in hunks if h.language in languages]
