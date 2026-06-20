"""Tests for review formatter."""

import json
import pytest
from review_agent.formatting.review_formatter import (
    format_as_json,
    format_as_markdown,
    build_github_review_payload,
)
from review_agent.models import ReviewComment, InlineComment


def make_review(n_comments: int = 2) -> ReviewComment:
    inline = [
        InlineComment(path=f"src/file{i}.py", line=10 + i, body=f"Issue #{i}")
        for i in range(n_comments)
    ]
    return ReviewComment(
        summary="## Test Summary\n\nFound 2 issues.",
        inline_comments=inline,
        total_findings=n_comments,
        estimated_cost_usd=0.001,
    )


def test_format_as_json_is_valid():
    review = make_review()
    output = format_as_json(review)
    data = json.loads(output)
    assert data["total_findings"] == 2
    assert len(data["inline_comments"]) == 2
    assert "summary" in data


def test_format_as_markdown_contains_comments():
    review = make_review()
    md = format_as_markdown(review)
    assert "Test Summary" in md
    assert "src/file0.py" in md
    assert "Issue #1" in md


def test_build_github_payload_structure():
    review = make_review()
    payload = build_github_review_payload(review, "abc123sha")
    assert payload["commit_id"] == "abc123sha"
    assert payload["event"] == "COMMENT"
    assert len(payload["comments"]) == 2
    comment = payload["comments"][0]
    assert "path" in comment
    assert "line" in comment
    assert "side" in comment
    assert comment["side"] == "RIGHT"


def test_empty_review():
    review = ReviewComment(summary="All clear.", inline_comments=[], total_findings=0)
    payload = build_github_review_payload(review, "sha")
    assert payload["comments"] == []
    assert payload["body"] == "All clear."
