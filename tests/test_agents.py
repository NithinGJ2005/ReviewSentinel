"""Tests for agent nodes — uses mocked Anthropic calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

from review_agent.models import DiffHunk, DiffLine, Finding, Severity, Category
from review_agent.agents.state import ReviewState


def make_hunk(
    file_path: str = "src/app.py",
    language: str = "python",
    added_content: str = "    return eval(user_input)\n",
) -> DiffHunk:
    return DiffHunk(
        file_path=file_path,
        language=language,
        source_start=10,
        source_length=3,
        target_start=10,
        target_length=4,
        lines=[
            DiffLine(line_type="context", target_line_no=9, value="def run(user_input):\n"),
            DiffLine(line_type="added", target_line_no=10, value=added_content),
        ],
    )


def make_state(**kwargs) -> ReviewState:
    base: ReviewState = {
        "pr_number": 42,
        "repo": "testorg/testrepo",
        "dry_run": True,
        "diff_hunks": [make_hunk()],
        "file_context": {},
        "head_commit_sha": "abc123",
        "static_findings": [],
        "bug_findings": [],
        "security_findings": [],
        "smell_findings": [],
        "suggested_fixes": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "skip_security": False,
        "skip_smell": False,
        "risk_level": "medium",
    }
    base.update(kwargs)
    return base


# -----------------------------------------------------------------------
# Triage node
# -----------------------------------------------------------------------

class TestTriageNode:
    def _mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(payload)
        usage = MagicMock()
        usage.prompt_token_count = 10
        usage.candidates_token_count = 5
        mock_resp.usage_metadata = usage
        return mock_resp

    def test_triage_returns_risk_level(self):
        from review_agent.agents.triage import triage_node

        payload = {"risk_level": "high", "skip_security": False, "skip_smell": False, "reasoning": "test"}
        with patch("review_agent.agents.triage._MODEL") as mock_model:
            mock_model.generate_content.return_value = self._mock_response(payload)
            state = make_state()
            result = triage_node(state)

        assert result["risk_level"] == "high"
        assert result["skip_security"] is False

    def test_triage_empty_hunks(self):
        from review_agent.agents.triage import triage_node

        state = make_state(diff_hunks=[])
        result = triage_node(state)
        assert result["risk_level"] == "low"
        assert result["skip_security"] is True

    def test_triage_graceful_failure(self):
        from review_agent.agents.triage import triage_node

        with patch("review_agent.agents.triage._MODEL") as mock_model:
            mock_model.generate_content.side_effect = Exception("API error")
            state = make_state()
            result = triage_node(state)

        # Should degrade to medium risk, not raise
        assert result["risk_level"] == "medium"


# -----------------------------------------------------------------------
# Bug detector node
# -----------------------------------------------------------------------

class TestBugDetectorNode:
    def _mock_response(self, findings: list):
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(findings)
        usage = MagicMock()
        usage.prompt_token_count = 20
        usage.candidates_token_count = 15
        mock_resp.usage_metadata = usage
        return mock_resp

    def test_bug_detector_parses_findings(self):
        from review_agent.agents.bug_detector import bug_detector_node

        raw_findings = [
            {
                "file_path": "src/app.py",
                "line_start": 10,
                "line_end": 10,
                "severity": "critical",
                "category": "bug",
                "explanation": "eval() is dangerous",
                "code_snippet": "return eval(user_input)",
                "confidence": 0.95,
            }
        ]
        with patch("review_agent.agents.bug_detector._MODEL") as mock_model:
            mock_model.generate_content.return_value = self._mock_response(raw_findings)
            state = make_state()
            result = bug_detector_node(state)

        findings = result["bug_findings"]
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL
        assert findings[0].category == Category.BUG

    def test_bug_detector_returns_empty_list_on_no_findings(self):
        from review_agent.agents.bug_detector import bug_detector_node

        with patch("review_agent.agents.bug_detector._MODEL") as mock_model:
            mock_model.generate_content.return_value = self._mock_response([])
            state = make_state()
            result = bug_detector_node(state)

        assert result["bug_findings"] == []

    def test_bug_detector_empty_hunks(self):
        from review_agent.agents.bug_detector import bug_detector_node

        state = make_state(diff_hunks=[])
        result = bug_detector_node(state)
        assert result["bug_findings"] == []

    def test_bug_detector_with_student_mode(self):
        from review_agent.agents.bug_detector import bug_detector_node

        with patch("review_agent.agents.bug_detector._MODEL") as mock_model:
            mock_model.generate_content.return_value = self._mock_response([])
            state = make_state(student_mode=True)
            bug_detector_node(state)

            # Check that generate_content was called with a prompt containing student mode suffix
            call_args = mock_model.generate_content.call_args[0][0]
            assert "STUDENT MODE" in call_args
            assert "pedagogical" in call_args or "CS student" in call_args


# -----------------------------------------------------------------------
# Aggregator node
# -----------------------------------------------------------------------

class TestAggregatorNode:
    def _make_finding(self, sev: Severity, cat: Category, line: int = 10) -> Finding:
        return Finding(
            file_path="src/app.py",
            line_start=line,
            line_end=line,
            severity=sev,
            category=cat,
            explanation="Test issue",
            confidence=0.9,
        )

    def test_aggregator_deduplicates(self):
        from review_agent.agents.aggregator import aggregator_node

        state = make_state(
            bug_findings=[
                self._make_finding(Severity.WARNING, Category.BUG, line=10),
                self._make_finding(Severity.CRITICAL, Category.BUG, line=10),  # same location
            ],
            security_findings=[],
            smell_findings=[],
            suggested_fixes=[],
        )
        result = aggregator_node(state)
        review = result["final_review"]
        # Should deduplicate to 1 (keep critical)
        assert review.total_findings == 1
        assert review.inline_comments[0].body.__contains__("CRITICAL")

    def test_aggregator_no_findings(self):
        from review_agent.agents.aggregator import aggregator_node

        state = make_state(
            bug_findings=[],
            security_findings=[],
            smell_findings=[],
            suggested_fixes=[],
        )
        result = aggregator_node(state)
        review = result["final_review"]
        assert review.total_findings == 0
        assert "No Issues Found" in review.summary

    def test_aggregator_sorts_critical_first(self):
        from review_agent.agents.aggregator import aggregator_node

        state = make_state(
            bug_findings=[
                self._make_finding(Severity.SUGGESTION, Category.BUG, line=5),
                self._make_finding(Severity.CRITICAL, Category.SECURITY, line=20),
                self._make_finding(Severity.WARNING, Category.SMELL, line=15),
            ],
            security_findings=[],
            smell_findings=[],
            suggested_fixes=[],
        )
        result = aggregator_node(state)
        comments = result["final_review"].inline_comments
        severities = [c.body for c in comments]
        # Critical should come first
        assert "CRITICAL" in severities[0]
