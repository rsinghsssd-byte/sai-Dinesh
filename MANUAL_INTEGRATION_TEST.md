# Manual Integration Test — Real GitHub Repositories

The unit tests and `tests/demo_offline.py` prove the detection engine
(preprocessing, similarity, commit analysis, aggregation, reporting) with
real assertions and no network access required. The one piece that could
not be exercised in the environment this project was built in is the actual
`git clone` against GitHub (that sandbox had outbound networking disabled).
Do this 10-minute checklist once, in your real deployment environment,
before relying on the tool:

## 1. Install & run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 2. Positive control — known-plagiarized pair

Pick (or create) two small public repos where you already know the answer.
Easiest: fork a small public repo, change nothing (or rename a few
variables), push it under your own account, then analyze the original +
your fork together.

- [ ] Job reaches `status: completed` within a reasonable time for repo size.
- [ ] The forked pair shows a **high** similarity score (matrix cell +
      flagged pairs list).
- [ ] Clicking the pair shows the actual file(s) that matched.
- [ ] If you renamed variables in your fork, confirm the score is still high
      (this is the whole point of identifier normalization).

## 3. Negative control — unrelated repos

Analyze two unrelated small repos (e.g. two different course starter
templates from different topics, or two of your own unrelated side
projects).

- [ ] Similarity score is low (near 0) for the pair.
- [ ] No file pairs are flagged.

## 4. Commit-level signals

- [ ] Push one commit to a test repo that pastes in a large (150+ line)
      chunk of code in one shot. Confirm it appears in "Unusually large /
      sudden commits" after analysis.
- [ ] Use a near-identical commit message on two different repos ("Add
      binary search implementation using recursion" vs "Add binary search
      implementation with recursion"). Confirm it's picked up as a commit
      message match on the pair's detail view.

## 5. Edge cases worth checking once

- [ ] A private repo URL (should fail cleanly with an error surfaced in the
      job status / `clone_errors`, not crash the whole job — the other repos
      in the batch should still be analyzed).
- [ ] A non-default branch name.
- [ ] The maximum repo count (20) and minimum (2) — both should be accepted;
      21 or 1 should be rejected by the form/API validation.
- [ ] A very large repository — confirm clone time and analysis time are
      acceptable, or add a repo-size limit (see `MAX_REPO_SIZE_MB` /
      `CLONE_TIMEOUT_SECONDS` constants in `app/git_service.py` — currently
      defined but not yet wired to an enforced abort; wire them to a
      `git clone --depth` limit and a wall-clock timeout if you expect
      very large student/candidate repos).
- [ ] Download the HTML report for a completed job and confirm it opens and
      prints to PDF cleanly from your browser.

## What "pass" looks like

Positive control clearly separates from negative control by a wide margin
(e.g. ≥0.7 vs ≤0.2), commit signals fire on the deliberately-large commit
and deliberately-similar message, and a bad repo URL degrades gracefully
instead of failing the whole batch. If any of these don't hold in your
environment, check `clone_errors` in the job result first — most first-run
issues are GitHub auth/rate-limiting (add a `GITHUB_TOKEN`-based auth header
to `git_service.clone_repo` if you're hitting rate limits on many repos).
