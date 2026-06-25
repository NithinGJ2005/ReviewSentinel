"""Top-level pipeline orchestrator — wires GitHub client, static analysis, and LangGraph."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from review_agent.diff_parser import parse_diff, group_hunks_by_file
from review_agent.github_client import GitHubClient
from review_agent.static_analysis.bandit_runner import run_bandit
from review_agent.static_analysis.semgrep_runner import run_semgrep
from review_agent.static_analysis.eslint_runner import run_eslint
from review_agent.agents.graph import build_graph
from review_agent.agents.state import ReviewState
from review_agent.formatting.review_formatter import format_as_json, format_as_markdown
from review_agent.storage.history_db import ReviewHistory
from review_agent.models import StaticFinding

logger = logging.getLogger(__name__)


class ReviewPipeline:
    """Orchestrates the full end-to-end PR review."""

    def __init__(
        self,
        repo: str,
        pr_number: int,
        dry_run: bool = False,
        cost_estimate: bool = False,
        output_mode: str = "github",
        student_mode: bool = False,
    ) -> None:
        self.repo = repo
        self.pr_number = pr_number
        self.dry_run = dry_run
        self.cost_estimate = cost_estimate
        self.output_mode = output_mode
        self.student_mode = student_mode

        self._gh = GitHubClient()
        self._history = ReviewHistory()
        self._graph = build_graph()

    def run(self) -> dict[str, Any]:
        """Execute the full pipeline and return a result summary dict."""
        try:
            return self._run_inner()
        except Exception as exc:
            logger.exception("Pipeline failed: %s", exc)
            return {"error": str(exc), "total_findings": 0}

    def _run_inner(self) -> dict[str, Any]:
        logger.info("Starting review for %s PR #%d", self.repo, self.pr_number)

        # 1. Fetch PR metadata + diff
        pr = self._gh.get_pull_request(self.repo, self.pr_number)
        head_sha = pr.head.sha
        raw_diff = self._gh.get_pr_diff_text(self.repo, self.pr_number)

        logger.info("Fetched diff (%d bytes) for PR #%d", len(raw_diff), self.pr_number)

        # 2. Parse diff → hunks
        hunks = parse_diff(raw_diff)
        if not hunks:
            logger.info("No hunks found — nothing to review.")
            return {"total_findings": 0, "message": "Empty diff."}

        by_file = group_hunks_by_file(hunks)
        changed_files = list(by_file.keys())
        logger.info("Parsed %d hunks across %d files.", len(hunks), len(changed_files))

        # 3. Fetch file context from GitHub
        file_context: dict[str, str] = {}
        for fpath in changed_files[:15]:  # limit to avoid API rate limits
            content = self._gh.get_file_content(self.repo, fpath, ref=head_sha)
            if content:
                file_context[fpath] = content

        # 4. Run static analysis (write changed file content to temp dir)
        static_findings = self._run_static_analysis(changed_files, file_context)
        logger.info("Static analysis: %d findings total.", len(static_findings))

        # 5. Build initial state and run LangGraph
        initial_state: ReviewState = {
            "pr_number": self.pr_number,
            "repo": self.repo,
            "dry_run": self.dry_run,
            "student_mode": self.student_mode,
            "diff_hunks": hunks,
            "file_context": file_context,
            "head_commit_sha": head_sha,
            "static_findings": static_findings,
            "bug_findings": [],
            "security_findings": [],
            "smell_findings": [],
            "suggested_fixes": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

        final_state: ReviewState = self._graph.invoke(initial_state)
        review = final_state.get("final_review")

        if not review:
            return {"error": "Graph produced no review output.", "total_findings": 0}

        # 6. Output / post review
        if self.output_mode == "json":
            print(format_as_json(review))
        elif self.output_mode == "markdown":
            print(format_as_markdown(review))
        else:
            # Post to GitHub
            self._gh.post_review(
                repo=self.repo,
                pr_number=self.pr_number,
                review_comment=review,
                commit_sha=head_sha,
                dry_run=self.dry_run,
            )

        # 7. Persist history
        findings_for_db = [
            {
                "file_path": ic.path,
                "line": ic.line,
                "severity": "unknown",
                "body": ic.body[:500],
            }
            for ic in review.inline_comments
        ]
        self._history.save_run(
            repo=self.repo,
            pr_number=self.pr_number,
            head_commit_sha=head_sha,
            findings=findings_for_db,
            estimated_cost_usd=review.estimated_cost_usd,
            dry_run=self.dry_run,
        )

        return {
            "total_findings": review.total_findings,
            "estimated_cost_usd": review.estimated_cost_usd,
            "inline_comments": len(review.inline_comments),
        }

    def _run_static_analysis(
        self,
        changed_files: list[str],
        file_context: dict[str, str],
    ) -> list[StaticFinding]:
        """Write changed file contents to a temp dir and run static tools."""
        findings: list[StaticFinding] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_paths: dict[str, str] = {}
            for fpath, content in file_context.items():
                safe_name = fpath.replace("/", "_").replace("\\", "_")
                tmp_file = Path(tmpdir) / safe_name
                try:
                    tmp_file.write_text(content, encoding="utf-8")
                    tmp_paths[fpath] = str(tmp_file)
                except Exception as exc:
                    logger.debug("Could not write temp file for %s: %s", fpath, exc)

            all_tmp = list(tmp_paths.values())
            findings.extend(run_bandit(all_tmp))
            findings.extend(run_semgrep(all_tmp))
            findings.extend(run_eslint(all_tmp))

            # Remap temp paths back to real file paths
            reverse_map = {v: k for k, v in tmp_paths.items()}
            for f in findings:
                if f.file_path in reverse_map:
                    f.file_path = reverse_map[f.file_path]

        return findings
