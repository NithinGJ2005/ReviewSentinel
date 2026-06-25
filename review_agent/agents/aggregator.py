"""Aggregator node — merges, deduplicates, ranks, and formats the final review."""

from __future__ import annotations

import logging
from collections import defaultdict

from review_agent.agents.state import ReviewState
from review_agent.models import (
    Finding,
    FixSuggestion,
    ReviewComment,
    InlineComment,
    Severity,
    Category,
)

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.SUGGESTION: 2,
}

_SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.WARNING: "🟡",
    Severity.SUGGESTION: "🔵",
}

_CATEGORY_LABEL = {
    Category.BUG: "Bug",
    Category.SECURITY: "Security",
    Category.SMELL: "Code Smell",
    Category.STYLE: "Style",
    Category.PERFORMANCE: "Performance",
}


def _dedup_findings(findings: list[Finding]) -> list[Finding]:
    """Deduplicate findings by (file, line_start, category) keeping highest severity."""
    seen: dict[tuple, Finding] = {}
    for f in findings:
        key = (f.file_path, f.line_start, f.category)
        existing = seen.get(key)
        if existing is None or _SEVERITY_ORDER[f.severity] < _SEVERITY_ORDER[existing.severity]:
            seen[key] = f
    return list(seen.values())


def _rank_findings(findings: list[Finding]) -> list[Finding]:
    """Sort by severity, then confidence descending."""
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER[f.severity], -f.confidence),
    )


def _format_summary(
    findings: list[Finding],
    fixes: list[FixSuggestion],
    repo: str,
    pr_number: int,
    student_mode: bool = False,
) -> str:
    """Build a Markdown summary comment for the PR."""
    if not findings:
        if student_mode:
            return (
                "## ✅ ReviewSentinel — No Issues Found\n\n"
                "Excellent job! No bugs, security issues, or code smells were detected in this submission. Keep up the great work! 🎓\n\n"
                "*Reviewed by [ReviewSentinel](https://github.com/features/actions) 🤖*"
            )
        else:
            return (
                "## ✅ ReviewSentinel — No Issues Found\n\n"
                "No bugs, security issues, or significant code smells were detected in this PR.\n\n"
                "*Reviewed by [ReviewSentinel](https://github.com/features/actions) 🤖*"
            )

    # Stats
    by_severity: dict[Severity, int] = defaultdict(int)
    by_category: dict[Category, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1
        by_category[f.category] += 1

    stats_lines = []
    for sev in [Severity.CRITICAL, Severity.WARNING, Severity.SUGGESTION]:
        count = by_severity.get(sev, 0)
        if count:
            stats_lines.append(f"- {_SEVERITY_EMOJI[sev]} **{sev.value.title()}**: {count}")

    # Table
    table_rows = []
    for f in findings[:30]:  # cap at 30 rows
        fix = next(
            (fx for fx in fixes if fx.file_path == f.file_path and fx.line_start == f.line_start),
            None,
        )
        has_fix = "✔" if fix and fix.suggested_code else "—"
        short_file = f.file_path.split("/")[-1]
        table_rows.append(
            f"| `{short_file}:{f.line_start}` "
            f"| {_SEVERITY_EMOJI[f.severity]} {f.severity.value} "
            f"| {_CATEGORY_LABEL.get(f.category, f.category.value)} "
            f"| {f.explanation[:80].rstrip()}{'…' if len(f.explanation) > 80 else ''} "
            f"| {has_fix} |"
        )

    if student_mode:
        header = f"## 🎓 ReviewSentinel — Student Feedback for `{repo}` PR #{pr_number}\n"
        section_title = "### Learning Summary\n"
        table_header = (
            "\n### Learning Opportunities\n\n"
            "| Location | Severity | Category | Feedback & Concepts | Fix Available |"
        )
        footer = (
            "\n---"
            "\n*Reviewed by [ReviewSentinel](https://github.com/features/actions) 🤖 | "
            "Inline comments below contain detailed conceptual explanations and suggested fixes.*"
        )
    else:
        header = f"## 🔍 ReviewSentinel — Code Review for `{repo}` PR #{pr_number}\n"
        section_title = "### Summary\n"
        table_header = (
            "\n### Findings\n\n"
            "| Location | Severity | Category | Issue | Fix Available |"
        )
        footer = (
            "\n---"
            "\n*Reviewed by [ReviewSentinel](https://github.com/features/actions) 🤖 | "
            "Inline comments below contain detailed explanations and suggested fixes.*"
        )

    lines = [
        header,
        section_title,
        *stats_lines,
        table_header,
        "|---|---|---|---|---|",
        *table_rows,
        footer,
    ]
    return "\n".join(lines)


def _build_inline_comment(finding: Finding, fix: FixSuggestion | None) -> str:
    """Render a single inline comment body."""
    emoji = _SEVERITY_EMOJI.get(finding.severity, "🔵")
    category = _CATEGORY_LABEL.get(finding.category, finding.category.value)
    body_parts = [
        f"**{emoji} [{finding.severity.value.upper()}] {category}**\n",
        finding.explanation,
    ]

    if finding.code_snippet:
        body_parts.append(f"\n```\n{finding.code_snippet}\n```")

    if fix and fix.suggested_code:
        validity = "✅ Syntax valid" if fix.syntax_valid else "⚠️ Syntax not verified"
        body_parts.append(
            f"\n**Suggested Fix** ({validity}):\n"
            f"```diff\n- {chr(10).join('- ' + l for l in fix.original_code.splitlines())}\n"
            f"+ {chr(10).join('+ ' + l for l in fix.suggested_code.splitlines())}\n```\n"
            f"*{fix.explanation}*"
        )

    return "\n".join(body_parts)


def aggregator_node(state: ReviewState) -> ReviewState:
    """Merge all findings, deduplicate, rank, and build the final ReviewComment."""
    all_findings = (
        list(state.get("bug_findings", []))
        + list(state.get("security_findings", []))
        + list(state.get("smell_findings", []))
    )

    fixes: list[FixSuggestion] = list(state.get("suggested_fixes", []))
    fix_map: dict[tuple, FixSuggestion] = {
        (fx.file_path, fx.line_start): fx for fx in fixes
    }

    deduped = _dedup_findings(all_findings)
    ranked = _rank_findings(deduped)

    repo = state.get("repo", "unknown/repo")
    pr_number = state.get("pr_number", 0)
    student_mode = state.get("student_mode", False)

    summary = _format_summary(ranked, fixes, repo, pr_number, student_mode=student_mode)

    # Build inline comments
    inline_comments: list[InlineComment] = []
    for finding in ranked:
        fix = fix_map.get((finding.file_path, finding.line_start))
        body = _build_inline_comment(finding, fix)
        inline_comments.append(
            InlineComment(
                path=finding.file_path,
                line=finding.line_start,
                body=body,
            )
        )

    # Cost estimate
    input_tokens = state.get("total_input_tokens", 0) or 0
    output_tokens = state.get("total_output_tokens", 0) or 0
    # claude-sonnet-4-5 pricing (approximate): $3/MTok in, $15/MTok out
    estimated_cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000

    final_review = ReviewComment(
        summary=summary,
        inline_comments=inline_comments,
        total_findings=len(ranked),
        estimated_cost_usd=estimated_cost,
    )

    logger.info(
        "Aggregator: %d findings → %d inline comments (est. cost $%.4f)",
        len(ranked),
        len(inline_comments),
        estimated_cost,
    )

    return {**state, "final_review": final_review}
