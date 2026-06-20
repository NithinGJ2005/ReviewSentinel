"""GitHub API client — fetch PR diffs, post reviews, authenticate."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from github import Github, GithubException
from github.PullRequest import PullRequest
from tenacity import retry, stop_after_attempt, wait_exponential

from review_agent.models import DiffHunk, ReviewComment, InlineComment

logger = logging.getLogger(__name__)


class GitHubClient:
    """Wraps PyGithub + raw REST calls for PR diff fetching and review posting."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ["GITHUB_TOKEN"]
        self._gh = Github(self._token)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._base_url = "https://api.github.com"

    # ------------------------------------------------------------------
    # PR metadata
    # ------------------------------------------------------------------

    def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Return a PyGithub PullRequest object."""
        return self._gh.get_repo(repo).get_pull(pr_number)

    # ------------------------------------------------------------------
    # Diff fetching
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_pr_diff_text(self, repo: str, pr_number: int) -> str:
        """Fetch the raw unified diff for a PR."""
        url = f"{self._base_url}/repos/{repo}/pulls/{pr_number}"
        resp = self._session.get(url, headers={"Accept": "application/vnd.github.v3.diff"})
        resp.raise_for_status()
        return resp.text

    def get_file_content(self, repo: str, path: str, ref: str) -> str:
        """Fetch raw file content at a given ref (commit SHA or branch)."""
        gh_repo = self._gh.get_repo(repo)
        try:
            content = gh_repo.get_contents(path, ref=ref)
            if isinstance(content, list):
                raise ValueError(f"Path {path!r} is a directory, not a file.")
            return content.decoded_content.decode("utf-8", errors="replace")
        except GithubException as exc:
            logger.warning("Could not fetch %s@%s: %s", path, ref, exc)
            return ""

    def get_changed_files(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Return list of changed file dicts (filename, status, additions, deletions)."""
        pr = self.get_pull_request(repo, pr_number)
        return [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch or "",
            }
            for f in pr.get_files()
        ]

    # ------------------------------------------------------------------
    # Review posting
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def post_review(
        self,
        repo: str,
        pr_number: int,
        review_comment: ReviewComment,
        commit_sha: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Post a GitHub pull request review with inline comments."""
        if dry_run:
            logger.info("[DRY-RUN] Would post review to %s#%d", repo, pr_number)
            logger.info("[DRY-RUN] Body preview:\n%s", review_comment.summary[:500])
            for ic in review_comment.inline_comments[:3]:
                logger.info("[DRY-RUN] Inline: %s line %s — %s", ic.path, ic.line, ic.body[:120])
            return {"dry_run": True, "review_id": None}

        comments_payload = [
            {
                "path": ic.path,
                "line": ic.line,
                "side": "RIGHT",
                "body": ic.body,
            }
            for ic in review_comment.inline_comments
        ]

        payload: dict[str, Any] = {
            "commit_id": commit_sha,
            "body": review_comment.summary,
            "event": "COMMENT",
            "comments": comments_payload,
        }

        url = f"{self._base_url}/repos/{repo}/pulls/{pr_number}/reviews"
        resp = self._session.post(url, json=payload)
        if not resp.ok:
            logger.error("GitHub review post failed: %s %s", resp.status_code, resp.text[:400])
            resp.raise_for_status()

        data = resp.json()
        logger.info("Posted review #%s to %s#%d", data.get("id"), repo, pr_number)
        return data
