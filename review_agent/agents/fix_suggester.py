"""Fix suggester agent node — generates concrete diffs for each finding."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import google.generativeai as genai

from review_agent.agents.state import ReviewState
from review_agent.models import Finding, FixSuggestion

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
_MODEL = genai.GenerativeModel("gemini-2.5-flash")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "fix_suggester_prompt.txt"


def _load_prompt(student_mode: bool = False) -> str:
    if _PROMPT_PATH.exists():
        base = _PROMPT_PATH.read_text(encoding="utf-8")
    else:
        base = """\
You are a code fix suggestion assistant. Given a code review finding and the relevant code snippet, \
produce a minimal, correct suggested fix.
Respond with ONLY valid JSON:
{
  "original_code": "<exact lines to replace>",
  "suggested_code": "<corrected replacement>",
  "explanation": "<why this fixes the issue>"
}
If you cannot confidently suggest a fix, return:
{"original_code": "", "suggested_code": "", "explanation": "No safe fix available."}
"""

    if student_mode:
        suffix_path = _PROMPT_PATH.parent / "student_mode_suffix.txt"
        if suffix_path.exists():
            base += "\n\n" + suffix_path.read_text(encoding="utf-8")
    return base


def _validate_python_syntax(code: str) -> bool:
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def fix_suggester_node(state: ReviewState) -> ReviewState:
    """Generate fix suggestions for all findings."""
    all_findings: list[Finding] = (
        list(state.get("bug_findings", []))
        + list(state.get("security_findings", []))
        + list(state.get("smell_findings", []))
    )

    if not all_findings:
        return {"suggested_fixes": []}

    system_prompt = _load_prompt(state.get("student_mode", False))
    suggestions: list[FixSuggestion] = []
    total_in = 0
    total_out = 0

    # Only fix critical/warning findings
    fixable = [f for f in all_findings if f.severity.value in ("critical", "warning")]

    for finding in fixable:
        ref_key = f"{finding.category.value}:{finding.file_path}:{finding.line_start}"

        user_content = (
            f"Finding:\n"
            f"  File: {finding.file_path}\n"
            f"  Lines: {finding.line_start}–{finding.line_end}\n"
            f"  Severity: {finding.severity}\n"
            f"  Category: {finding.category}\n"
            f"  Explanation: {finding.explanation}\n\n"
            f"Code snippet:\n```\n{finding.code_snippet}\n```"
        )

        try:
            response = _MODEL.generate_content(
                f"{system_prompt}\n\n{user_content}",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=512,
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

            data = json.loads(raw)
            orig = data.get("original_code", "")
            sugg = data.get("suggested_code", "")
            expl = data.get("explanation", "No fix available.")

            syntax_ok = True
            if finding.file_path.endswith(".py") and sugg:
                syntax_ok = _validate_python_syntax(sugg)

            suggestions.append(
                FixSuggestion(
                    finding_ref=ref_key,
                    file_path=finding.file_path,
                    line_start=finding.line_start,
                    line_end=finding.line_end,
                    original_code=orig,
                    suggested_code=sugg,
                    explanation=expl,
                    syntax_valid=syntax_ok,
                )
            )

        except Exception as exc:
            logger.warning("Fix suggester failed for %s: %s", ref_key, exc)

    logger.info("Fix suggester produced %d suggestions", len(suggestions))
    return {
        "suggested_fixes": suggestions,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }
