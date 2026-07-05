# Case File — GitHub Commit Plagiarism Detection System

A web app that clones multiple GitHub repositories, normalizes and compares
their source code and commit history, and reports explainable, file-level
and commit-level similarity signals across repository pairs.

## What it actually detects

| Signal | How |
|---|---|
| Renamed-variable / restructured copying | Comment/whitespace stripping + identifier normalization (`x`, `total`, `helper()` → `ID1`, `ID2`, `ID3` in order of appearance) before comparison, so cosmetic renames don't hide a copy. |
| Partial copy-paste (one function lifted into an otherwise original file) | Winnowing k-gram fingerprinting (Schleimer/Wilkerson/Aiken — the same family of algorithm behind MOSS/JPlag) with **containment** similarity (shared fingerprints ÷ smaller file's fingerprints), which doesn't get diluted by unrelated surrounding code. |
| Exact / near-exact duplication | Jaccard similarity over the same fingerprint sets, plus a line-level `difflib` alignment used to drive the side-by-side diff view. |
| Sudden large commits | Per-author, per-repo, **leave-one-out** z-score on commit size (a commit is compared against the author's *other* commits, not a mean that includes itself) — flags "pasted in one shot" commits vs. gradual, iterative work. |
| Shared/copied commit messages | Pairwise fuzzy string matching (`difflib.SequenceMatcher`) between commit messages across two repositories. |

Every score is explainable: the detail view and the downloadable report show
*which* files matched, *which* lines matched, and *why* a commit was flagged
(with the actual numbers), by design — see the Constraints section of the
original brief ("focus on detection and reporting, not enforcement").

## Architecture

```
plagiarism-detector/
├── backend/
│   ├── app/
│   │   ├── preprocessing.py     # comment/whitespace strip + identifier normalization (7 languages)
│   │   ├── similarity.py        # tokenizer, winnowing fingerprints, containment/Jaccard/line-ratio
│   │   ├── commit_analysis.py   # large-commit z-score, commit-message fuzzy matching
│   │   ├── git_service.py       # GitPython clone + commit/file extraction
│   │   ├── analyzer.py          # orchestrates the full pipeline for one job
│   │   ├── database.py          # SQLite job store (stdlib sqlite3, no ORM)
│   │   ├── report.py            # self-contained downloadable HTML report
│   │   ├── schemas.py           # Pydantic request/response models + validation
│   │   ├── main.py              # FastAPI app, serves API + static frontend
│   │   └── routes/analyze.py    # POST /api/analyze, job polling, report download
│   ├── tests/test_core_engine.py  # 13 unit tests, stdlib-only, no network needed
│   └── requirements.txt
├── frontend/                    # vanilla HTML/CSS/JS dashboard (no build step, no CDN JS deps)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── docker-compose.yml
└── backend/Dockerfile
```

No frontend build step (no npm/webpack) — it's plain HTML/CSS/JS served
directly by FastAPI's `StaticFiles`, which keeps the whole system to one
container and one command to run.

## Running it

### Fastest: Docker

```bash
docker compose up --build
```
Then open **http://localhost:8000**.

### Local dev (without Docker)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Open **http://localhost:8000** (the frontend is served from the same origin,
so there's no CORS configuration to fight with in dev either).

## Using it

1. Paste 2–20 `https://github.com/...` repository URLs.
2. Pick the language to analyze (only one language per run, per the brief's
   constraint — mixed-language repos are filtered to matching files only).
3. Set the branch (defaults to `main`) and a similarity threshold (0.1–1.0).
4. **Run analysis.** A progress bar tracks clone → preprocess → compare →
   aggregate.
5. The dashboard shows a repository similarity matrix (diagonal-hatched
   cells = above your threshold) and a ranked list of flagged pairs.
6. Click a flagged pair for file-wise scores and commit-message matches.
7. **Download report** for a self-contained HTML file (print it to PDF from
   any browser — no server-side PDF dependency needed).

## Verifying the detection engine (no GitHub access needed)

The similarity/preprocessing/commit-analysis modules are pure Python
(stdlib only) and fully unit-tested without touching the network:

```bash
cd backend
python3 -m unittest tests.test_core_engine -v
```

This proves, with real assertions, that:
- identical files score ≈1.0,
- **renamed-variable plagiarism still scores ≥0.75** (the actual core
  requirement of this project),
- unrelated code scores <0.3,
- a genuinely sudden large commit gets flagged (and normal ones don't),
- near-identical commit messages across repos get matched (and unrelated
  ones don't).

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/analyze` | POST | Submit a job. Body: `{repo_urls, language, branch, similarity_threshold}`. Returns `{job_id, status}`. |
| `/api/jobs/{id}` | GET | Poll status: `{status, progress, progress_message}`. |
| `/api/jobs/{id}/result` | GET | Full JSON result once `status == completed`. |
| `/api/jobs/{id}/report` | GET | Downloadable HTML summary report. |
| `/api/languages` | GET | Supported languages list. |
| `/api/health` | GET | Liveness check. |

Interactive Swagger docs are auto-served at `/docs` (FastAPI default).

## Constraints implemented per the brief

- Single language per analysis run (file extension filter applied at
  extraction time).
- Up to 20 repositories per job (enforced by request validation).
- Purely detection/reporting — no automated "plagiarism verdict"; the report
  explicitly states scores need human review, and the UI's own copy avoids
  language like "guilty"/"cheating."

## Known limitations / honest caveats

- **This sandbox had no outbound network access**, so `git_service.py`
  (actual GitHub cloning) could not be exercised end-to-end here — only
  compiled and code-reviewed. Every other module (preprocessing, similarity,
  commit analysis, the orchestrator, the DB layer, and the report generator)
  was executed and asserted against real inputs, including a full pipeline
  run with a mocked git layer that reproduces exactly the plagiarism/
  no-plagiarism scenarios you'd see with real repos. Before your first real
  run, do one smoke test with two small public repos you know the outcome
  for.
- Fingerprinting works at the token level, not a real AST/parse tree — it's
  deliberately language-agnostic (same engine handles Python/Java/C/C++/JS/
  TS/Go/C#) rather than needing a parser per language. This is the same
  tradeoff MOSS/JPlag-style tools make; it will not catch semantic-only
  plagiarism (same logic, totally different syntax/idioms).
- SQLite job store is fine for a single instance; see below to scale out.
- No auth/rate-limiting is included — add a reverse proxy (nginx/Caddy) with
  basic auth or an API key check in `main.py` before exposing this publicly,
  since it clones arbitrary GitHub URLs on your server's behalf (SSRF-style
  risk if left open to the internet).

## Scaling beyond a single instance

Swap `app/database.py`'s sqlite3 calls for a Postgres connection (schema is
one flat `jobs` table, trivial to port) and move `_execute_job` from FastAPI
`BackgroundTasks` to a real queue (Celery/RQ + Redis) if you need multiple
worker processes or need jobs to survive a server restart mid-run. The
analyzer/similarity/preprocessing modules don't change at all — only the
job-orchestration plumbing does.

## Adding a language

Add an entry to `SUPPORTED_LANGUAGES` and `_KEYWORDS` in
`backend/app/preprocessing.py` and a line/block comment pair in
`_COMMENT_SYNTAX`. No other file needs to change — the tokenizer,
fingerprinting, and commit analysis are language-agnostic.
