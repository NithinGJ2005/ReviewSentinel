"""ESLint runner — JavaScript/TypeScript static analysis."""

from __future__ import annotations

import json
import logging
import subprocess

from review_agent.models import StaticFinding, Severity, Category

logger = logging.getLogger(__name__)

_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def _eslint_severity(severity_int: int) -> Severity:
    """Convert ESLint numeric severity (1=warn, 2=error) to our enum."""
    if severity_int >= 2:
        return Severity.WARNING
    return Severity.SUGGESTION


def run_eslint(files: list[str], timeout: int = 60) -> list[StaticFinding]:
    """Run ESLint on JS/TS files and return normalized findings.

    Args:
        files: Absolute file paths to scan.
        timeout: Max seconds.

    Returns:
        List of StaticFinding objects.
    """
    from pathlib import Path

    js_files = [f for f in files if Path(f).suffix.lower() in _JS_EXTS]
    if not js_files:
        return []

    findings: list[StaticFinding] = []

    try:
        cmd = [
            "npx",
            "--yes",
            "eslint",
            "--format=json",
            "--no-eslintrc",
            "--env=browser,node,es2022",
            "--rule={'no-eval': 'error', 'no-implied-eval': 'error', "
            "'no-new-func': 'error', 'no-proto': 'error', 'no-undef': 'warn'}",
            *js_files,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = result.stdout.strip()
        if not output:
            return []

        data = json.loads(output)
        for file_result in data:
            fpath = file_result.get("filePath", "")
            for msg in file_result.get("messages", []):
                findings.append(
                    StaticFinding(
                        tool="eslint",
                        file_path=fpath,
                        line=msg.get("line", 0),
                        column=msg.get("column", 0),
                        rule_id=msg.get("ruleId", ""),
                        message=msg.get("message", ""),
                        severity=_eslint_severity(msg.get("severity", 1)),
                        category=Category.BUG,
                    )
                )

    except FileNotFoundError:
        logger.warning("ESLint/npx not found — skipping JS/TS analysis.")
    except subprocess.TimeoutExpired:
        logger.warning("ESLint timed out after %ds.", timeout)
    except json.JSONDecodeError as exc:
        logger.warning("ESLint JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("ESLint runner error: %s", exc)

    logger.info("ESLint found %d findings in %d files.", len(findings), len(js_files))
    return findings
