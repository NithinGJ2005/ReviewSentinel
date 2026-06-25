"""Code smell detector agent — naming, duplication, complexity, design smells."""

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

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "smell_detector_prompt.txt"


def _load_prompt(student_mode: bool = False) -> str:
    if _PROMPT_PATH.exists():
        base = _PROMPT_PATH.read_text(encoding="utf-8")
    else:
        base = """\
You are a code quality reviewer focused on detecting code smells and maintainability issues.
Look for: long methods, excessive complexity, poor naming, magic numbers, dead code, duplication.
Do NOT flag security issues or outright bugs.

Respond with ONLY a JSON array:
[
  {
    "file_path": "...", "line_start": <int>, "line_end": <int>,
    "severity": "warning" | "suggestion",
    "category": "smell", "explanation": "...", "code_snippet": "...",
    "confidence": <float 0-1>
  }
]
If no smells found, return [].
"""

    if student_mode:
        suffix_path = _PROMPT_PATH.parent / "student_mode_suffix.txt"
        if suffix_path.exists():
            base += "\n\n" + suffix_path.read_text(encoding="utf-8")
    return base


def smell_detector_node(state: ReviewState) -> ReviewState:
    """Detect code smells in changed hunks."""
    if state.get("skip_smell", False):
        logger.info("Skipping smell scan (triage decision).")
        return {"smell_findings": []}

    hunks = state.get("diff_hunks", [])
    context = state.get("file_context", {})
    system_prompt = _load_prompt(state.get("student_mode", False))
    all_findings: list[Finding] = []
    total_in = 0
    total_out = 0

    for hunk in hunks:
        hunk_text = hunk.hunk_text
        if not hunk_text.strip():
            continue

        ctx_content = context.get(hunk.file_path, "")
        ctx_block = ""
        if ctx_content:
            ctx_block = f"### File Context\n```\n{chr(10).join(ctx_content.splitlines()[:150])}\n```\n\n"

        user_content = (
            f"File: {hunk.file_path} (language: {hunk.language})\n\n"
            f"### Diff Hunk\n```diff\n{hunk_text}\n```\n\n{ctx_block}"
        )

        try:
            response = _MODEL.generate_content(
                f"{system_prompt}\n\n{user_content}",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=768,
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
                        severity=Severity(item.get("severity", "suggestion")),
                        category=Category.SMELL,
                        explanation=item.get("explanation", ""),
                        code_snippet=item.get("code_snippet", ""),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                    all_findings.append(finding)
                except Exception as parse_exc:
                    logger.debug("Skipping malformed smell finding: %s", parse_exc)

        except Exception as exc:
            logger.warning("Smell detector failed on %s: %s", hunk.file_path, exc)

    logger.info("Smell detector found %d findings", len(all_findings))
    return {
        "smell_findings": all_findings,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }
