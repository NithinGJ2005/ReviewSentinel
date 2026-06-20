"""Semgrep runner — multi-language security and bug pattern scanning."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from review_agent.models import StaticFinding, Severity, Category

logger = logging.getLogger(__name__)

_SEMGREP_SEVERITY_MAP = {
    "ERROR": Severity.CRITICAL,
    "WARNING": Severity.WARNING,
    "INFO": Severity.SUGGESTION,
}

# Default ruleset — covers OWASP top 10 + common bugs
_DEFAULT_RULES = "p/owasp-top-ten"


def run_semgrep(
    files: list[str],
    rules: str = _DEFAULT_RULES,
    timeout: int = 120,
) -> list[StaticFinding]:
    """Run Semgrep on the given files and return normalized findings.

    Args:
        files: Absolute paths to files to scan.
        rules: Semgrep rule config (registry shorthand or path).
        timeout: Max seconds to wait.

    Returns:
        List of StaticFinding objects.
    """
    if not files:
        return []

    findings: list[StaticFinding] = []

    try:
        cmd = [
            "semgrep",
            "--json",
            "--quiet",
            f"--config={rules}",
            "--no-rewrite-rule-ids",
            *files,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = result.stdout.strip()
        if not output:
            logger.debug("Semgrep returned no output.")
            return []

        data = json.loads(output)
        for match in data.get("results", []):
            sev_str = match.get("extra", {}).get("severity", "WARNING").upper()
            meta = match.get("extra", {}).get("metadata", {})
            category_str = meta.get("category", "security").lower()
            category = Category.SECURITY if "security" in category_str else Category.BUG

            findings.append(
                StaticFinding(
                    tool="semgrep",
                    file_path=match.get("path", ""),
                    line=match.get("start", {}).get("line", 0),
                    column=match.get("start", {}).get("col", 0),
                    rule_id=match.get("check_id", ""),
                    message=match.get("extra", {}).get("message", ""),
                    severity=_SEMGREP_SEVERITY_MAP.get(sev_str, Severity.WARNING),
                    category=category,
                )
            )

    except FileNotFoundError:
        logger.warning("Semgrep not installed or not on PATH — skipping.")
    except subprocess.TimeoutExpired:
        logger.warning("Semgrep timed out after %ds.", timeout)
    except json.JSONDecodeError as exc:
        logger.warning("Semgrep JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Semgrep runner error: %s", exc)

    logger.info("Semgrep found %d findings.", len(findings))
    return findings
