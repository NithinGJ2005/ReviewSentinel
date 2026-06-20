# ReviewSentinel 🔍

**An autonomous AI code review agent for GitHub pull requests.**

ReviewSentinel automatically reviews every PR, detecting bugs, security vulnerabilities, and code smells using a multi-agent LangGraph pipeline backed by Claude AI + traditional static analysis tools.

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
│     │  Triage  │ (Claude Haiku — cheap classification)│  │
│     └────┬─────┘                                    │  │
│          │ (parallel fan-out)                       │  │
│    ┌─────┼────────┐                                 │  │
│    ▼     ▼        ▼                                 │  │
│  Bug  Security  Smell   (Claude Sonnet — reasoning) │  │
│    └─────┼────────┘                                 │  │
│          ▼                                          │  │
│      Fix Suggester (Claude Sonnet)                  │  │
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
- **Hybrid LLM + static analysis** — Semgrep, Bandit, and ESLint feed into the LLM for false-positive reduction
- **Inline PR comments** — file-level, line-anchored GitHub review comments
- **Severity triage** — 🔴 Critical / 🟡 Warning / 🔵 Suggestion
- **Fix suggestions** — concrete code patches with syntax validation
- **RAG context** — ChromaDB stores code chunks for semantic retrieval
- **Cost transparency** — `--cost-estimate` flag shows token/cost breakdown
- **Dry-run mode** — test without posting to GitHub
- **Review history** — SQLite persists all runs for trend analysis

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/your-org/review-sentinel
cd review-sentinel
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in:
# ANTHROPIC_API_KEY=...
# GITHUB_TOKEN=...
```

### 3. Run a Review (dry-run)

```bash
review-agent run --pr 42 --repo owner/myrepo --dry-run
```

### 4. Index a Repository (for RAG)

```bash
review-agent index --repo-path /path/to/your/repo
```

---

## GitHub Actions Setup

1. **Add secrets** to your repository:
   - `ANTHROPIC_API_KEY` — your Anthropic API key
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
| LLM | Claude Sonnet (review) + Claude Haiku (triage) |
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
│   ├── triage.py             # Risk classification (Haiku)
│   ├── bug_detector.py       # Logic bug detection (Sonnet)
│   ├── security_scanner.py   # Security analysis (Sonnet)
│   ├── smell_detector.py     # Code smell detection (Sonnet)
│   ├── fix_suggester.py      # Fix generation (Sonnet)
│   └── aggregator.py         # Merge, rank, format
├── prompts/                  # System prompts for each agent
├── static_analysis/          # Bandit, Semgrep, ESLint runners
├── indexing/                 # tree-sitter chunker + ChromaDB
├── formatting/               # GitHub review payload builder
└── storage/                  # SQLite history
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key | ✅ |
| `GITHUB_TOKEN` | GitHub personal access token or Actions token | ✅ |
| `CHROMA_DB_PATH` | Path to ChromaDB persistence directory | Optional |
| `SQLITE_DB_PATH` | Path to SQLite database file | Optional |
| `EMBEDDING_MODEL` | sentence-transformers model name | Optional |
| `DRY_RUN` | Set to `true` to prevent posting comments | Optional |
| `LOG_LEVEL` | Logging verbosity | Optional |

---

## License

MIT
