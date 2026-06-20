"""Triage agent node — classifies risk and decides which agents to run."""

from __future__ import annotations

import json
import logging
import os

import google.generativeai as genai

from review_agent.agents.state import ReviewState

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
_MODEL = genai.GenerativeModel("gemini-2.5-flash")

TRIAGE_PROMPT = """\
You are a triage assistant for a code review system. You will receive a summary of changed files \
in a pull request. Your job is to:
1. Assess overall risk level: "low" | "medium" | "high".
2. Decide whether a security scan is necessary (skip only for docs/config/test-only PRs).
3. Decide whether a code-smell scan is necessary (skip for tiny single-line fixes).

Respond with ONLY valid JSON matching this schema:
{
  "risk_level": "low" | "medium" | "high",
  "skip_security": true | false,
  "skip_smell": true | false,
  "reasoning": "<1–2 sentence justification>"
}
"""


def triage_node(state: ReviewState) -> ReviewState:
    """Use Gemini Flash to triage the PR and set skip flags."""
    hunks = state.get("diff_hunks", [])
    if not hunks:
        return {"risk_level": "low", "skip_security": True, "skip_smell": True}

    by_file: dict[str, list] = {}
    for h in hunks:
        by_file.setdefault(h.file_path, []).append(h)

    file_summary_parts: list[str] = []
    for fpath, fhunks in list(by_file.items())[:20]:
        added = sum(len(h.added_lines) for h in fhunks)
        removed = sum(len(h.removed_lines) for h in fhunks)
        file_summary_parts.append(f"- {fpath} (+{added} / -{removed})")

    user_content = (
        f"Changed files ({len(by_file)} total):\n" + "\n".join(file_summary_parts)
    )

    try:
        response = _MODEL.generate_content(
            f"{TRIAGE_PROMPT}\n\nUser: {user_content}",
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=256,
                temperature=0.1,
            ),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:-3]
        data = json.loads(raw)
        logger.info(
            "Triage: risk=%s skip_security=%s skip_smell=%s — %s",
            data.get("risk_level"),
            data.get("skip_security"),
            data.get("skip_smell"),
            data.get("reasoning", ""),
        )
        usage = response.usage_metadata
        return {
            "risk_level": data.get("risk_level", "medium"),
            "skip_security": bool(data.get("skip_security", False)),
            "skip_smell": bool(data.get("skip_smell", False)),
            "total_input_tokens": getattr(usage, "prompt_token_count", 0),
            "total_output_tokens": getattr(usage, "candidates_token_count", 0),
        }
    except Exception as exc:
        logger.warning("Triage node failed (%s), defaulting to medium risk.", exc)
        return {"risk_level": "medium", "skip_security": False, "skip_smell": False}
