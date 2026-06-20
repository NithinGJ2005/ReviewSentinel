"""SQLite review history storage using SQLAlchemy."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Float,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo = Column(String(255), nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_commit_sha = Column(String(40))
    run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    total_findings = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    suggestion_count = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    findings_json = Column(Text)   # JSON-serialized list of findings
    dry_run = Column(Integer, default=0)  # SQLite bool


class ReviewHistory:
    """Persists review run metadata to SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        path = db_path or os.environ.get("SQLITE_DB_PATH", "./data/review_history.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def save_run(
        self,
        repo: str,
        pr_number: int,
        head_commit_sha: str,
        findings: list[dict[str, Any]],
        estimated_cost_usd: float = 0.0,
        dry_run: bool = False,
    ) -> int:
        """Persist a review run and return its ID."""
        by_severity: dict[str, int] = {"critical": 0, "warning": 0, "suggestion": 0}
        for f in findings:
            sev = f.get("severity", "suggestion")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        run = ReviewRun(
            repo=repo,
            pr_number=pr_number,
            head_commit_sha=head_commit_sha,
            total_findings=len(findings),
            critical_count=by_severity["critical"],
            warning_count=by_severity["warning"],
            suggestion_count=by_severity["suggestion"],
            estimated_cost_usd=estimated_cost_usd,
            findings_json=json.dumps(findings),
            dry_run=int(dry_run),
        )
        with self._Session() as session:
            session.add(run)
            session.commit()
            run_id = run.id

        logger.info("Saved review run #%d for %s PR #%d", run_id, repo, pr_number)
        return run_id

    def get_recent_runs(self, repo: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent review runs for a repo."""
        with self._Session() as session:
            rows = (
                session.query(ReviewRun)
                .filter(ReviewRun.repo == repo)
                .order_by(ReviewRun.run_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "pr_number": r.pr_number,
                    "run_at": r.run_at.isoformat() if r.run_at else None,
                    "total_findings": r.total_findings,
                    "critical": r.critical_count,
                    "warning": r.warning_count,
                    "suggestion": r.suggestion_count,
                    "cost": r.estimated_cost_usd,
                }
                for r in rows
            ]
