"""Agent state definition for the LangGraph review pipeline."""

from __future__ import annotations

from typing import TypedDict, Annotated
import operator

from review_agent.models import (
    DiffHunk,
    StaticFinding,
    Finding,
    FixSuggestion,
    ReviewComment,
)


class ReviewState(TypedDict, total=False):
    # Inputs
    pr_number: int
    repo: str
    dry_run: bool

    # Parsed diff
    diff_hunks: list[DiffHunk]
    file_context: dict[str, str]          # retrieved context per file
    head_commit_sha: str

    # Static analysis results
    static_findings: Annotated[list[StaticFinding], operator.add]

    # LLM agent findings (accumulated via reducer)
    bug_findings: Annotated[list[Finding], operator.add]
    security_findings: Annotated[list[Finding], operator.add]
    smell_findings: Annotated[list[Finding], operator.add]

    # Fix suggestions
    suggested_fixes: list[FixSuggestion]

    # Final output
    final_review: ReviewComment

    # Cost tracking
    total_input_tokens: Annotated[int, operator.add]
    total_output_tokens: Annotated[int, operator.add]

    # Triage metadata
    skip_security: bool
    skip_smell: bool
    risk_level: str   # "low" | "medium" | "high"
