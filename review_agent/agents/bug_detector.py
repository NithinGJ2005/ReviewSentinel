"""Bug detector agent node — finds logic errors, off-by-one, null handling, race conditions."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import google.generativeai as genai

from review_agent.agents.state import ReviewState
from review_agent.models import Finding, Severity, Category

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
_MODEL = genai.GenerativeModel("gemini-2.5-flash")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "bug_detector_prompt.txt"


def _load_prompt(student_mode: bool = False) -> str:
    if _PROMPT_PATH.exists():
        base = _PROMPT_PATH.read_text(encoding="utf-8")
    else:
        base = """\
You are an expert bug detector reviewing a GitHub pull request hunk.
Focus ONLY on logic errors, off-by-one mistakes, null/undefined dereferences, \
race conditions, incorrect exception handling, and incorrect algorithmic logic.
Only flag issues you are REASONABLY CONFIDENT about.

Respond with JSON only (no prose outside the JSON array):
[
  {
    "file_path": "...",
    "line_start": <int>,
    "line_end": <int>,
    "severity": "critical" | "warning" | "suggestion",
    "category": "bug",
    "explanation": "...",
    "code_snippet": "...",
    "confidence": <float 0-1>
  }
]
If no bugs are found, return an empty array: []
"""

    if student_mode:
        suffix_path = _PROMPT_PATH.parent / "student_mode_suffix.txt"
        if suffix_path.exists():
            base += "\n\n" + suffix_path.read_text(encoding="utf-8")
    return base


def _build_context_block(file_path: str, context: dict[str, str]) -> str:
    content = context.get(file_path, "")
    if not content:
        return ""
    return "\n".join(content.splitlines()[:200])


def bug_detector_node(state: ReviewState) -> ReviewState:
    """Run the bug detection agent on all diff hunks."""
    hunks = state.get("diff_hunks", [])
    context = state.get("file_context", {})

    if not hunks:
        return {"bug_findings": []}

    system_prompt = _load_prompt(state.get("student_mode", False))
    all_findings: list[Finding] = []
    total_in = 0
    total_out = 0

    for hunk in hunks:
        hunk_text = hunk.hunk_text
        if not hunk_text.strip():
            continue

        ctx_block = _build_context_block(hunk.file_path, context)
        user_content = (
            f"File: {hunk.file_path} (language: {hunk.language})\n\n"
            f"### Diff Hunk\n```diff\n{hunk_text}\n```\n\n"
        )
        if ctx_block:
            user_content += f"### Surrounding File Context (first 200 lines)\n```\n{ctx_block}\n```\n"

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
                        category=Category.BUG,
                        explanation=item.get("explanation", ""),
                        code_snippet=item.get("code_snippet", ""),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                    all_findings.append(finding)
                except Exception as parse_exc:
                    logger.debug("Skipping malformed finding: %s", parse_exc)

        except Exception as exc:
            logger.warning("Bug detector failed on hunk %s: %s", hunk.file_path, exc)

    logger.info("Bug detector found %d findings", len(all_findings))
    return {
        "bug_findings": all_findings,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }
