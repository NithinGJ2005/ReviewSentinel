"""Shared Pydantic models / dataclasses used across the agent."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    SMELL = "smell"
    STYLE = "style"
    PERFORMANCE = "performance"


# ------------------------------------------------------------------
# Diff models
# ------------------------------------------------------------------

class DiffLine(BaseModel):
    line_type: str  # "added", "removed", "context"
    source_line_no: int | None = None
    target_line_no: int | None = None
    value: str


class DiffHunk(BaseModel):
    file_path: str
    language: str = "unknown"
    source_start: int
    source_length: int
    target_start: int
    target_length: int
    lines: list[DiffLine] = Field(default_factory=list)

    @property
    def added_lines(self) -> list[DiffLine]:
        return [l for l in self.lines if l.line_type == "added"]

    @property
    def removed_lines(self) -> list[DiffLine]:
        return [l for l in self.lines if l.line_type == "removed"]

    @property
    def hunk_text(self) -> str:
        """Return the hunk as a unified diff string."""
        lines = []
        for ln in self.lines:
            prefix = {"added": "+", "removed": "-", "context": " "}.get(ln.line_type, " ")
            lines.append(f"{prefix}{ln.value}")
        return "".join(lines)


# ------------------------------------------------------------------
# Static analysis models
# ------------------------------------------------------------------

class StaticFinding(BaseModel):
    tool: str  # "semgrep" | "bandit" | "eslint"
    file_path: str
    line: int
    column: int = 0
    rule_id: str
    message: str
    severity: Severity
    category: Category = Category.SECURITY


# ------------------------------------------------------------------
# LLM agent findings
# ------------------------------------------------------------------

class Finding(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    severity: Severity
    category: Category
    explanation: str
    code_snippet: str = ""
    confidence: float = 1.0  # 0–1


class FixSuggestion(BaseModel):
    finding_ref: str  # e.g., "security:file.py:42"
    file_path: str
    line_start: int
    line_end: int
    original_code: str
    suggested_code: str
    explanation: str
    syntax_valid: bool = False


# ------------------------------------------------------------------
# Output models
# ------------------------------------------------------------------

class InlineComment(BaseModel):
    path: str
    line: int
    body: str


class ReviewComment(BaseModel):
    summary: str
    inline_comments: list[InlineComment] = Field(default_factory=list)
    total_findings: int = 0
    estimated_cost_usd: float = 0.0
