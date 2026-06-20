"""Security scanner agent node — combines Semgrep/Bandit with Gemini LLM triage."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import google.generativeai as genai

from review_agent.agents.state import ReviewState
from review_agent.models import Finding, StaticFinding, Severity, Category

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
_MODEL = genai.GenerativeModel("gemini-2.5-flash")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "security_scanner_prompt.txt"


def _load_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return """\
You are a security-focused code reviewer. You will receive a diff hunk and any static analysis \
findings from Semgrep/Bandit for that file.
Evaluate static findings for true/false positives and identify additional security vulnerabilities.
Do NOT flag general code quality issues.

Respond with ONLY a JSON array:
[
  {
    "file_path": "...", "line_start": <int>, "line_end": <int>,
    "severity": "critical" | "warning" | "suggestion",
    "category": "security", "explanation": "...", "code_snippet": "...",
    "confidence": <float 0-1>, "source": "llm" | "semgrep" | "bandit"
  }
]
If no security issues found, return [].
"""


def security_scanner_node(state: ReviewState) -> ReviewState:
    """Combine static findings with Gemini security analysis."""
    if state.get("skip_security", False):
        logger.info("Skipping security scan (triage decision).")
        return {"security_findings": []}

    hunks = state.get("diff_hunks", [])
    static_findings: list[StaticFinding] = state.get("static_findings", [])
    context = state.get("file_context", {})

    static_by_file: dict[str, list[StaticFinding]] = {}
    for sf in static_findings:
        static_by_file.setdefault(sf.file_path, []).append(sf)

    system_prompt = _load_prompt()
    all_findings: list[Finding] = []
    total_in = 0
    total_out = 0

    for hunk in hunks:
        hunk_text = hunk.hunk_text
        if not hunk_text.strip():
            continue

        file_statics = static_by_file.get(hunk.file_path, [])
        static_block = ""
        if file_statics:
            static_lines = [
                f"  - [{sf.tool}] Line {sf.line}: [{sf.rule_id}] {sf.message} (sev: {sf.severity})"
                for sf in file_statics
            ]
            static_block = "### Static Analysis Findings\n" + "\n".join(static_lines) + "\n\n"

        ctx_content = context.get(hunk.file_path, "")
        ctx_block = ""
        if ctx_content:
            ctx_block = f"### File Context\n```\n{chr(10).join(ctx_content.splitlines()[:150])}\n```\n\n"

        user_content = (
            f"File: {hunk.file_path} (language: {hunk.language})\n\n"
            f"### Diff Hunk\n```diff\n{hunk_text}\n```\n\n"
            f"{static_block}{ctx_block}"
        )

        try:
            response = _MODEL.generate_content(
                f"{system_prompt}\n\n{user_content}",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1024,
                    temperature=0.1,
                ),
            )
            usage = response.usage_metadata
            total_in += getattr(usage, "prompt_token_count", 0)
            total_out += getattr(usage, "candidates_token_count", 0)

            raw = response.text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]

            findings_data = json.loads(raw)
            if not isinstance(findings_data, list):
                findings_data = []

            for item in findings_data:
                try:
                    finding = Finding(
                        file_path=item.get("file_path", hunk.file_path),
                        line_start=int(item.get("line_start", hunk.target_start)),
                        line_end=int(item.get("line_end", hunk.target_start)),
                        severity=Severity(item.get("severity", "warning")),
                        category=Category.SECURITY,
                        explanation=item.get("explanation", ""),
                        code_snippet=item.get("code_snippet", ""),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                    all_findings.append(finding)
                except Exception as parse_exc:
                    logger.debug("Skipping malformed security finding: %s", parse_exc)

        except Exception as exc:
            logger.warning("Security LLM node failed on %s: %s — degrading to static findings", hunk.file_path, exc)
            for sf in file_statics:
                all_findings.append(
                    Finding(
                        file_path=sf.file_path,
                        line_start=sf.line,
                        line_end=sf.line,
                        severity=sf.severity,
                        category=Category.SECURITY,
                        explanation=f"[{sf.tool}] {sf.message}",
                        confidence=0.7,
                    )
                )

    logger.info("Security scanner found %d findings", len(all_findings))
    return {
        "security_findings": all_findings,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }
