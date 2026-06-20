# Autonomous Code Review Agent — Implementation Plan

## 1. Project Summary

**Name:** ReviewSentinel (working title — rename freely)
**One-liner:** An AI agent that automatically reviews GitHub pull requests, detects bugs/security issues/code smells, suggests concrete fixes with explanations, and posts the review as PR comments via GitHub Actions.

**Core capabilities:**
- Triggered automatically on every PR open/update via a GitHub Action.
- Parses the PR diff, retrieves relevant surrounding code context using RAG over the repository.
- Runs a multi-agent pipeline (LangGraph) that splits review work across specialized agents: bug detection, security scanning, code-smell/style detection, and fix suggestion.
- Combines LLM judgment with traditional static analysis tools (Semgrep, Bandit, ESLint) so the system isn't relying on the LLM alone for security findings.
- Posts a structured, inline review comment on the PR (file + line level, not just a single summary blob) with severity tags and suggested diffs.
- Maintains a review history/vector store so the agent can recall prior review patterns and avoid repeating false positives.

**Why this project is a strong resume piece:** it combines agentic orchestration (LangGraph), RAG, real external API integration (GitHub), CI/CD (GitHub Actions), and a hybrid LLM + static-analysis architecture — which is a more defensible engineering story in interviews than "LLM wrapper" projects.

---

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Agent orchestration | LangGraph | State machine across review agents |
| LLM | Claude API (Sonnet for review reasoning, Haiku for cheap triage/classification) | Use Anthropic Python SDK |
| RAG / embeddings | ChromaDB + `sentence-transformers` or Claude-compatible embedding model | Local vector store, no external infra needed |
| Code parsing | `tree-sitter` (AST parsing) + `unidiff`/`whatthepatch` for diff parsing | Reuse approach from DevLens if helpful |
| Static analysis | Semgrep (security + bugs), Bandit (Python security), ESLint (JS/TS) | Run as subprocess, parse JSON output |
| GitHub integration | PyGithub or GitHub REST API directly + GitHub Actions workflow YAML | Webhook-free — Actions handles the trigger |
| Backend | Python 3.11, FastAPI (only if you want a standalone service; otherwise a CLI invoked by Actions is enough) | Start CLI-first, add FastAPI later if needed |
| Storage | SQLite for review history/metadata, ChromaDB for embeddings | No external DB dependency for MVP |
| CI/CD | GitHub Actions (`.yml` workflow) | This is also your *deployment target* |
| Testing | pytest | Cover diff parsing, agent routing, and prompt outputs |

---

## 3. System Architecture

### 3.1 High-level flow

1. Developer opens/updates a PR on GitHub.
2. GitHub Actions workflow triggers on `pull_request` event (`opened`, `synchronize`).
3. Action checks out the repo, installs the agent package, and runs `review-agent run --pr <number> --repo <owner/repo>`.
4. The agent:
   a. Fetches the PR diff via GitHub API.
   b. Parses the diff into changed files + changed hunks.
   c. For each changed file, retrieves relevant context (full file content, related files via import graph, and similar past-reviewed code via the vector store).
   d. Runs static analyzers (Semgrep/Bandit/ESLint as applicable) on changed files, captures findings.
   e. Passes diff + context + static analysis findings into the LangGraph pipeline.
   f. LangGraph routes through specialized agent nodes (see 3.3).
   g. Aggregator agent merges all findings into a structured review object (file, line, severity, category, explanation, suggested fix).
   h. Formatter renders this as Markdown PR review comments (inline where possible, summary comment otherwise).
   i. GitHub API posts the review (`POST /repos/{owner}/{repo}/pulls/{pr}/reviews` with inline comments).
5. Review history is persisted to SQLite + ChromaDB for future context.

### 3.2 Repository indexing (RAG layer)

- On first run (or via a separate "index" GitHub Action triggered on push to main), the agent walks the repo, chunks files by function/class using tree-sitter, and embeds each chunk.
- Chunks are stored in ChromaDB with metadata: file path, symbol name, language, last-modified commit SHA.
- On PR review, the agent queries ChromaDB for chunks related to the changed code (by import relationships and embedding similarity) to give the LLM enough context to judge correctness without needing the entire repo in the prompt.
- Re-index incrementally: only re-embed files that changed since the last indexed commit.

### 3.3 LangGraph agent pipeline

Represent the review as a `ReviewState` object passed through a graph:

```python
class ReviewState(TypedDict):
    pr_number: int
    repo: str
    diff_hunks: list[DiffHunk]
    file_context: dict[str, str]          # retrieved context per file
    static_findings: list[StaticFinding]  # from Semgrep/Bandit/ESLint
    bug_findings: list[Finding]
    security_findings: list[Finding]
    smell_findings: list[Finding]
    suggested_fixes: list[FixSuggestion]
    final_review: ReviewComment
```

**Nodes:**
- `triage_node` — classifies each changed file by risk/size, decides which downstream agents to invoke (skip security agent for a docs-only PR, for instance). Use a cheap model (Haiku) here.
- `bug_detector_node` — LLM agent focused purely on logic errors, off-by-one, null handling, race conditions. Prompted with diff + retrieved context.
- `security_scanner_node` — combines Semgrep/Bandit output with an LLM pass that explains *why* each flagged line is risky and whether it's a true positive given the surrounding code (reduces static-analyzer false-positive noise — this is a good interview talking point).
- `smell_detector_node` — code smells, duplication, naming, complexity (can use `radon` for cyclomatic complexity as a cheap signal feeding into the LLM prompt).
- `fix_suggester_node` — for every finding from the three nodes above, generates a concrete suggested diff/patch with an explanation, validated by re-parsing the suggested code with tree-sitter to make sure it's syntactically valid.
- `aggregator_node` — merges, deduplicates, ranks by severity, and produces the final structured review.

**Graph edges:** `triage → [bug_detector, security_scanner, smell_detector] → fix_suggester → aggregator → END`. The three middle nodes run as parallel branches in LangGraph, merging at `fix_suggester`.

### 3.4 Output format

Post review as a GitHub "Review" with inline comments where the API supports line-anchoring, falling back to a single summary comment with a Markdown table (File | Line | Severity | Category | Issue | Suggested Fix) for hunks that can't be cleanly anchored (e.g., multi-line stylistic issues).

Severity levels: `critical` (security/correctness blocker), `warning` (should fix), `suggestion` (nice-to-have/style).

---

## 4. Project Structure

```
review-agent/
├── .github/
│   └── workflows/
│       ├── review-on-pr.yml        # main trigger workflow
│       └── index-on-push.yml       # re-index repo on push to main
├── review_agent/
│   ├── __init__.py
│   ├── cli.py                      # entrypoint: `review-agent run --pr N --repo owner/repo`
│   ├── github_client.py            # PR diff fetch, posting reviews, auth
│   ├── diff_parser.py              # unidiff parsing → DiffHunk objects
│   ├── indexing/
│   │   ├── chunker.py              # tree-sitter based function/class chunking
│   │   ├── embedder.py             # embedding generation
│   │   └── vector_store.py         # ChromaDB wrapper
│   ├── static_analysis/
│   │   ├── semgrep_runner.py
│   │   ├── bandit_runner.py
│   │   └── eslint_runner.py
│   ├── agents/
│   │   ├── state.py                 # ReviewState TypedDict
│   │   ├── graph.py                 # LangGraph construction
│   │   ├── triage.py
│   │   ├── bug_detector.py
│   │   ├── security_scanner.py
│   │   ├── smell_detector.py
│   │   ├── fix_suggester.py
│   │   └── aggregator.py
│   ├── prompts/
│   │   ├── bug_detector_prompt.txt
│   │   ├── security_scanner_prompt.txt
│   │   ├── smell_detector_prompt.txt
│   │   └── fix_suggester_prompt.txt
│   ├── formatting/
│   │   └── review_formatter.py      # ReviewState → GitHub review payload
│   └── storage/
│       └── history_db.py            # SQLite review history
├── tests/
│   ├── test_diff_parser.py
│   ├── test_agents.py
│   ├── test_formatting.py
│   └── fixtures/
│       └── sample_diffs/
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 5. Build Phases (Suggested 6-Week Sprint Plan)

### Phase 1 — Foundations (Week 1)
- Set up repo, `pyproject.toml`, package skeleton above.
- Implement `github_client.py`: authenticate via GitHub App or PAT, fetch PR diff, list changed files.
- Implement `diff_parser.py` with `unidiff` — convert raw diff text into `DiffHunk` objects (file, start_line, end_line, added/removed lines).
- Write a minimal GitHub Action (`review-on-pr.yml`) that just checks out the repo and runs the CLI in a no-op/dry-run mode, printing the parsed diff. **Goal: prove the trigger → fetch → parse loop works end to end before adding any AI.**

### Phase 2 — Static Analysis Layer (Week 2)
- Implement `semgrep_runner.py`, `bandit_runner.py`, `eslint_runner.py` as subprocess wrappers that return normalized `StaticFinding` objects.
- Run these on changed files only (filter by file extension/language).
- Test against a deliberately vulnerable sample repo (e.g., OWASP's vulnerable Python/JS sample apps) to validate signal quality.

### Phase 3 — RAG / Indexing Layer (Week 3)
- Implement tree-sitter chunking by function/class.
- Implement embedding + ChromaDB storage.
- Build the `index-on-push.yml` workflow for incremental re-indexing.
- Implement context retrieval: given a changed file, pull (a) the full file, (b) imported/related files, (c) top-k semantically similar chunks from history.

### Phase 4 — LangGraph Agent Pipeline (Weeks 4–5)
- Define `ReviewState` and build the graph in `graph.py`.
- Implement each node with carefully engineered prompts (see Section 6). Start with `bug_detector` and `security_scanner` since they have the clearest evaluation criteria.
- Implement `fix_suggester` with syntax validation (re-parse suggested patch with tree-sitter; discard/flag invalid suggestions rather than posting broken code).
- Implement `aggregator` to dedupe and rank.
- Unit test each node against fixed input/output pairs using a handful of hand-crafted PR diffs with known issues (this becomes your evaluation set — keep it, it's useful for the resume/demo too).

### Phase 5 — Output + GitHub Posting (Week 5)
- Implement `review_formatter.py`: map `ReviewState.final_review` to the GitHub "create review" API payload, anchoring comments to diff lines correctly (this is fiddly — GitHub requires the comment to reference the correct diff position, not just the file line number).
- Wire posting into the CLI and full GitHub Action.
- Test on a real scratch repo with intentionally buggy/insecure PRs.

### Phase 6 — Polish, History, Demo (Week 6)
- Implement `history_db.py` (SQLite) to log every review run, findings, and whether a human later resolved/dismissed them (sets up future "learn from feedback" extension).
- Add a `--dry-run` and `--cost-estimate` flag (token/cost transparency is a nice demo touch and shows engineering maturity).
- Record a demo: open a PR with seeded bugs/security issues in a sample repo, show the Action running and the review appearing live.
- Write the README with architecture diagram, setup instructions, and example output screenshots.

---

## 6. Prompt Design Notes

Each agent prompt should follow this shape (adapt per node):

```
SYSTEM: You are a {role} reviewing a single GitHub pull request hunk.
You will receive: the diff hunk, surrounding file context, and (where relevant) static analysis findings.
Only flag issues you are reasonably confident about — do not invent issues to seem thorough.
For each issue, output: file, line range, severity (critical|warning|suggestion), category, a one-paragraph explanation, and (if applicable) a minimal suggested code change.
Respond ONLY in the specified JSON schema below, no prose outside it.
```

Use structured JSON output (Section: Structured Outputs) so the aggregator can merge results programmatically rather than re-parsing free text. Keep each node's prompt narrowly scoped — a security-only prompt produces meaningfully fewer false positives than one general "review this code" prompt, and this scoping is itself worth calling out as a design decision in your write-up/interview.

---

## 7. GitHub Actions Workflow (Reference Skeleton)

`.github/workflows/review-on-pr.yml`:

```yaml
name: AI Code Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install agent
        run: pip install -e .
      - name: Run review agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: review-agent run --pr ${{ github.event.pull_request.number }} --repo ${{ github.repository }}
```

---

## 8. Evaluation Plan

To make this defensible in interviews/resume bullets, don't just demo it — measure it:
- Build a small benchmark of ~15–20 PR diffs with known, labeled issues (mix of real CVE-style bugs and synthetic ones).
- Track precision/recall of the agent's findings against the labeled set per category (bug, security, smell).
- Track false-positive rate of the LLM-augmented security findings vs. raw Semgrep/Bandit output alone — this is your strongest quantifiable claim ("reduced false positives by X% by combining static analysis with LLM verification").
- Track latency and approximate token cost per PR review (useful for a "is this practical at scale" discussion).

---

## 9. Stretch Goals (if time permits)

- Slack/Discord notification integration alongside the PR comment.
- A small Streamlit dashboard showing review history and trend metrics (leverages your existing Streamlit experience).
- "Learn from dismissals" loop: if a human marks a finding as a false positive, store it and use it as a few-shot example to suppress similar future findings.
- Support for auto-applying low-risk suggested fixes as a follow-up commit (behind a flag, opt-in only).

---

## 10. Environment / Secrets Setup Checklist

- [ ] `ANTHROPIC_API_KEY` — Anthropic API key, stored as a GitHub repo secret.
- [ ] `GITHUB_TOKEN` — usually auto-provided by Actions; if cross-repo posting is needed, use a GitHub App or PAT with `pull_requests: write` scope instead.
- [ ] Local `.env` for development with the same variables plus `CHROMA_DB_PATH` and `SQLITE_DB_PATH`.
- [ ] A scratch/sandbox GitHub repo to test against without risking a real project's PRs.

---

## 11. Instructions for the Build Agent (Antigravity)

When implementing this plan:
1. Build and test Phase 1 fully end-to-end (trigger → diff fetch → parse, printed to logs) before writing any LLM or LangGraph code — this isolates GitHub API/auth issues early.
2. Use structured JSON outputs from every LLM call; never parse free-text LLM responses with regex.
3. Keep static analysis and LLM review as separable, independently testable layers — the security scanner node should work even if the LLM call fails (degrade to raw Semgrep/Bandit output).
4. Write unit tests alongside each phase, not at the end; the fixture diffs in `tests/fixtures/sample_diffs/` should be created in Phase 1 and reused throughout.
5. Default to Claude Sonnet for the four review-reasoning nodes (`bug_detector`, `security_scanner`, `smell_detector`, `fix_suggester`) and Claude Haiku for `triage`, to control cost.
6. Validate every suggested fix's syntax with tree-sitter before including it in the posted review.
