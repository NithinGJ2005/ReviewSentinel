# ReviewSentinel 🔍

**Automated, pedagogical code review feedback for CS courses — built on a multi-agent AI pipeline.**

CS instructors spend an enormous share of their grading time repeating the same feedback: the same off-by-one error, the same SQL injection pattern, the same untested edge case, across dozens of student submissions every week. That time doesn't go toward the conceptual teaching that actually needs a human.

ReviewSentinel automates the first pass. It reviews every pull request — or every student submission opened as a PR — and triages bugs, security vulnerabilities, and code smells using a multi-agent LangGraph pipeline backed by Gemini and traditional static analysis. With `--student-mode`, it doesn't just flag what's wrong — it explains the underlying concept, why it matters, and how to think about it next time, turning every review into a learning moment instead of a red mark.

**Built for EdTech 3.0 — Track 2: Assessment & Feedback Automation.**

---

## For Instructors

ReviewSentinel cuts the hours instructors spend manually catching the same logic errors, security mistakes, and style issues across dozens of student submissions. Instead of writing the same comment forty times, instructors get triaged, prioritized feedback per submission — freeing time for the conceptual teaching that actually needs a human. Every run is persisted to a SQLite history, so patterns across a whole class or semester are queryable, not just per-PR.

## For Students

Run with `--student-mode`, ReviewSentinel doesn't say "this is a bug" — it explains the underlying CS concept behind the issue, why it matters for your learning, and how to think about it next time. Feedback reads like a mentor's comment, not a linter's output, and it shows up the moment you open a pull request, not days later when the assignment is already due.

---

## How the Pipeline Maps to Assessment & Feedback Automation

| Pipeline stage | What it does for grading & feedback |
|---|---|
| **Triage** | Prioritizes which submissions or hunks need a human instructor's attention first, instead of treating every line as equally urgent |
| **Bug detector** | Catches logic errors before they become silent point deductions on an assignment |
| **Security scanner** | Builds secure-coding habits early, instead of only flagging them in a later professional setting |
| **Smell detector** | Reinforces style and maintainability lessons consistently, the same way every time, across every submission |
| **Fix suggester** | Models the corrected pattern directly, reinforcing the right way to write it rather than just naming what's wrong |

---

## Architecture

```
GitHub PR (opened/updated)
        │
        ▼
┌───────────────────┐
│  GitHub Actions   │  ← Trigger
│  review-on-pr.yml │
└────────┬──────────┘
         │
         ▼
┌───────────────────────────────────────────────────────┐
│                  ReviewPipeline                        │
│                                                        │
│  1. Fetch PR diff (GitHub API)                         │
│  2. Parse diff → DiffHunk objects (unidiff)            │
│  3. Fetch file context (GitHub API)                    │
│  4. Run static analysis (Bandit + Semgrep + ESLint)    │
│  5. LangGraph multi-agent pipeline ─────────────────┐  │
│     ┌──────────┐                                    │  │
│     │  Triage  │      (Gemini 2.5 Flash)            │  │
│     └────┬─────┘                                    │  │
│          │ (parallel fan-out)                       │  │
│    ┌─────┼────────┐                                 │  │
│    ▼     ▼        ▼                                 │  │
│  Bug  Security  Smell   (Gemini 2.5 Flash)          │  │
│    └─────┼────────┘                                 │  │
│          ▼                                          │  │
│      Fix Suggester (Gemini 2.5 Flash)               │  │
│          ▼                                          │  │
│      Aggregator (dedup + rank + format)             │  │
│          └────────────────────────────────────────┘  │
│  6. Post GitHub PR Review (inline + summary)          │
│  7. Persist to SQLite history                         │
└───────────────────────────────────────────────────────┘
```

---

## Features

- **Multi-agent LangGraph pipeline** — specialized agents for bugs, security, and code smells
- **`--student-mode`** — reframes every finding as learning feedback: the underlying concept, why it matters, how to think about it next time
- **Hybrid LLM + static analysis** — Semgrep, Bandit, and ESLint feed into the LLM for false-positive reduction
- **Inline PR comments** — file-level, line-anchored GitHub review comments
- **Severity triage** — 🔴 Critical / 🟡 Warning / 🔵 Suggestion
- **Fix suggestions** — concrete code patches with syntax validation
- **RAG context** — ChromaDB stores code chunks for semantic retrieval
- **Cost transparency** — `--cost-estimate` flag shows token/cost breakdown
- **Dry-run mode** — test without posting to GitHub
- **Review history** — SQLite persists all runs for trend analysis across a class or semester

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/NithinGJ2005/ReviewSentinel
cd ReviewSentinel
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in:
# GOOGLE_API_KEY=...
# GITHUB_TOKEN=...
```

### 3. Run a Review (dry-run)

```bash
review-agent run --pr 42 --repo owner/myrepo --dry-run
```

### 4. Run a Review in Student Mode

```bash
review-agent run --pr 42 --repo owner/student-assignment-repo --student-mode
```

### 5. Index a Repository (for RAG)

```bash
review-agent index --repo-path /path/to/your/repo
```

---

## GitHub Actions Setup

1. **Add secrets** to your repository:
   - `GOOGLE_API_KEY` — your Gemini API key from Google AI Studio (free tier works great!)
   - `GITHUB_TOKEN` — auto-provided by Actions (or a PAT for cross-repo)

2. **Copy the workflow files** to your target repository:
   ```bash
   cp -r .github/workflows/ /path/to/target-repo/.github/workflows/
   ```

3. **Open a pull request** — ReviewSentinel will automatically comment.

---

## CLI Reference

```
review-agent run --pr <PR_NUMBER> --repo <OWNER/REPO> [OPTIONS]

Options:
  --dry-run         Parse and analyze but do not post to GitHub
  --cost-estimate   Print estimated token cost
  --output          github|json|markdown (default: github)
  --student-mode    Reframe findings as learning feedback for students
  --log-level       DEBUG|INFO|WARNING (default: INFO)

review-agent index --repo-path <PATH> [OPTIONS]

Options:
  --chroma-path     Override ChromaDB storage path
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Gemini 2.5 Flash |
| RAG / Embeddings | ChromaDB + sentence-transformers |
| Code parsing | tree-sitter |
| Static analysis | Semgrep + Bandit + ESLint |
| GitHub integration | PyGithub + REST API |
| Storage | SQLite (SQLAlchemy) + ChromaDB |
| CLI | Click + Rich |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
review_agent/
├── cli.py                    # CLI entrypoint
├── pipeline.py               # Top-level orchestrator
├── github_client.py          # GitHub API wrapper
├── diff_parser.py            # Unified diff → DiffHunk objects
├── models.py                 # Shared Pydantic models
├── agents/
│   ├── graph.py              # LangGraph construction
│   ├── state.py              # ReviewState TypedDict
│   ├── triage.py             # Risk classification (Gemini)
│   ├── bug_detector.py       # Logic bug detection (Gemini)
│   ├── security_scanner.py   # Security analysis (Gemini)
│   ├── smell_detector.py     # Code smell detection (Gemini)
│   ├── fix_suggester.py      # Fix generation (Gemini)
│   └── aggregator.py         # Merge, rank, format
├── prompts/                  # System prompts for each agent (+ student_mode_suffix.txt)
├── static_analysis/          # Bandit, Semgrep, ESLint runners
├── indexing/                 # tree-sitter chunker + ChromaDB
├── formatting/               # GitHub review payload builder
└── storage/                  # SQLite history
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `GOOGLE_API_KEY` | Google Gemini API key | ✅ |
| `GITHUB_TOKEN` | GitHub personal access token or Actions token | ✅ |
| `CHROMA_DB_PATH` | Path to ChromaDB persistence directory | Optional |
| `SQLITE_DB_PATH` | Path to SQLite database file | Optional |
| `EMBEDDING_MODEL` | sentence-transformers model name | Optional |
| `DRY_RUN` | Set to `true` to prevent posting comments | Optional |
| `LOG_LEVEL` | Logging verbosity | Optional |

---

---

## Demo 

![https://nithingj2005.github.io/ReviewSentinel/dashboard/index.html](https://nithingj2005.github.io/ReviewSentinel/dashboard/index.html)


---

## License

MIT
