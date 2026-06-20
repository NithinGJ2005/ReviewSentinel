"""Bandit runner — Python security static analysis."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import os
from pathlib import Path

from review_agent.models import StaticFinding, Severity, Category

logger = logging.getLogger(__name__)

_BANDIT_SEVERITY_MAP = {
    "HIGH": Severity.CRITICAL,
    "MEDIUM": Severity.WARNING,
    "LOW": Severity.SUGGESTION,
    "UNDEFINED": Severity.SUGGESTION,
}


def run_bandit(files: list[str]) -> list[StaticFinding]:
    """Run Bandit on a list of Python files and return normalized findings.

    Args:
        files: Absolute paths to Python files to scan.

    Returns:
        List of StaticFinding objects.
    """
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return []

    findings: list[StaticFinding] = []

    try:
        cmd = [
            "bandit",
            "-f", "json",
            "-q",
            "--exit-zero",  # don't exit with error on findings
            *py_files,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if not result.stdout.strip():
            logger.debug("Bandit returned no output for %s files.", len(py_files))
            return []

        data = json.loads(result.stdout)
        for issue in data.get("results", []):
            sev_str = issue.get("issue_severity", "LOW").upper()
            findings.append(
                StaticFinding(
                    tool="bandit",
                    file_path=issue.get("filename", ""),
                    line=issue.get("line_number", 0),
                    column=issue.get("col_offset", 0),
                    rule_id=issue.get("test_id", ""),
                    message=issue.get("issue_text", ""),
                    severity=_BANDIT_SEVERITY_MAP.get(sev_str, Severity.WARNING),
                    category=Category.SECURITY,
                )
            )

    except FileNotFoundError:
        logger.warning("Bandit not installed or not on PATH — skipping.")
    except subprocess.TimeoutExpired:
        logger.warning("Bandit timed out scanning %d files.", len(py_files))
    except json.JSONDecodeError as exc:
        logger.warning("Bandit JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Bandit runner error: %s", exc)

    logger.info("Bandit found %d findings in %d files.", len(findings), len(py_files))
    return findings
