"""Review formatter — converts ReviewState into GitHub PR review payload."""

from __future__ import annotations

import json
import logging
from typing import Any

from review_agent.models import ReviewComment, Finding, FixSuggestion

logger = logging.getLogger(__name__)


def format_as_json(review: ReviewComment) -> str:
    """Serialize the review as JSON (for --output json mode)."""
    return json.dumps(
        {
            "summary": review.summary,
            "total_findings": review.total_findings,
            "estimated_cost_usd": review.estimated_cost_usd,
            "inline_comments": [
                {"path": c.path, "line": c.line, "body": c.body}
                for c in review.inline_comments
            ],
        },
        indent=2,
    )


def format_as_markdown(review: ReviewComment) -> str:
    """Return the review as standalone Markdown (for --output markdown mode)."""
    parts = [review.summary, ""]
    for ic in review.inline_comments:
        parts.append(f"### `{ic.path}` line {ic.line}")
        parts.append(ic.body)
        parts.append("")
    return "\n".join(parts)


def build_github_review_payload(
    review: ReviewComment,
    commit_sha: str,
) -> dict[str, Any]:
    """Build the payload dict for GitHub's POST /pulls/{pr}/reviews endpoint.

    Args:
        review: The final ReviewComment from the aggregator.
        commit_sha: The head commit SHA of the PR.

    Returns:
        A dict matching GitHub's review creation API.
    """
    comments = []
    for ic in review.inline_comments:
        comments.append(
            {
                "path": ic.path,
                "line": ic.line,
                "side": "RIGHT",
                "body": ic.body,
            }
        )

    return {
        "commit_id": commit_sha,
        "body": review.summary,
        "event": "COMMENT",
        "comments": comments,
    }
