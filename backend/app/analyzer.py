"""
analyzer.py
-----------
Orchestrates the full pipeline for one analysis job:

  clone repos -> extract files + commit history -> preprocess ->
  pairwise file similarity -> commit-level checks -> aggregate per repo-pair
  confidence score -> serializable result dict (stored in DB, served by API).

Designed so each stage is independently unit-testable (see tests/); this
module just wires them together and handles partial failures (e.g. one repo
fails to clone shouldn't abort the whole job).
"""
from __future__ import annotations
import itertools
import logging
from dataclasses import asdict
from typing import Dict, List

from .preprocessing import normalize_source, language_for_extension, SUPPORTED_LANGUAGES
from .similarity import compare_files, combined_score, FileSimilarity
from .commit_analysis import (
    CommitInfo, detect_large_commits, detect_similar_commit_messages,
)
from .git_service import clone_repo, extract_files, extract_commit_history, TempWorkdir, GitServiceError

logger = logging.getLogger("analyzer")

FILE_FLAG_THRESHOLD_DEFAULT = 0.75  # combined_score above which a file pair is "flagged"


def run_analysis(repo_urls: List[str], language: str, branch: str,
                  similarity_threshold: float = FILE_FLAG_THRESHOLD_DEFAULT,
                  progress_cb=None) -> Dict:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    if not (2 <= len(repo_urls) <= 20):
        raise ValueError("Provide between 2 and 20 repository URLs.")

    def progress(pct: int, msg: str):
        logger.info("[%s%%] %s", pct, msg)
        if progress_cb:
            progress_cb(pct, msg)

    repo_files: Dict[str, list] = {}
    repo_commits: Dict[str, List[CommitInfo]] = {}
    clone_errors: Dict[str, str] = {}

    with TempWorkdir() as workdir:
        for i, repo_url in enumerate(repo_urls):
            progress(int(5 + 40 * i / len(repo_urls)), f"Cloning {repo_url}")
            try:
                local_path = clone_repo(repo_url, branch, workdir)
                repo_files[repo_url] = extract_files(local_path, repo_url, language)
                repo_commits[repo_url] = extract_commit_history(local_path, repo_url, branch)
            except GitServiceError as exc:
                logger.warning(str(exc))
                clone_errors[repo_url] = str(exc)

    usable_repos = [r for r in repo_urls if r in repo_files]
    if len(usable_repos) < 2:
        return {
            "status": "failed",
            "error": "Fewer than 2 repositories could be cloned/analyzed.",
            "clone_errors": clone_errors,
        }

    progress(50, "Preprocessing source files")
    normalized_cache: Dict[str, list] = {}
    for repo_url in usable_repos:
        normalized_cache[repo_url] = [
            normalize_source(f.path, f.content, language) for f in repo_files[repo_url]
        ]

    progress(60, "Computing pairwise file similarity")
    pair_results: Dict[str, Dict] = {}
    repo_pairs = list(itertools.combinations(usable_repos, 2))
    for idx, (repo_a, repo_b) in enumerate(repo_pairs):
        file_sims: List[FileSimilarity] = []
        for fa in normalized_cache[repo_a]:
            for fb in normalized_cache[repo_b]:
                fs = compare_files(
                    fa.path, fa.canonical_source, fa.normalized_source,
                    fb.path, fb.canonical_source, fb.normalized_source,
                )
                fs_score = combined_score(fs)
                if fs_score > 0:
                    file_sims.append((fs, fs_score))

        file_sims.sort(key=lambda t: t[1], reverse=True)
        flagged = [
            {
                "file_a": fs.path_a, "file_b": fs.path_b,
                "containment": fs.containment, "jaccard": fs.jaccard,
                "matched_line_ratio": fs.matched_line_ratio,
                "score": score, "matching_blocks": fs.matching_blocks,
            }
            for fs, score in file_sims if score >= similarity_threshold
        ]

        # Repo-pair confidence: best signal per file in the smaller repo,
        # averaged, so one shared boilerplate file doesn't dominate.
        best_per_file: Dict[str, float] = {}
        for fs, score in file_sims:
            best_per_file[fs.path_a] = max(best_per_file.get(fs.path_a, 0.0), score)
        repo_score = round(sum(best_per_file.values()) / max(len(normalized_cache[repo_a]), 1), 4)

        commit_msg_matches = detect_similar_commit_messages(
            repo_commits.get(repo_a, []), repo_commits.get(repo_b, [])
        )

        pair_results[f"{repo_a}||{repo_b}"] = {
            "repo_a": repo_a, "repo_b": repo_b,
            "repo_similarity_score": repo_score,
            "flagged_file_pairs": flagged,
            "all_file_pairs_compared": len(file_sims),
            "commit_message_matches": [asdict(m) for m in commit_msg_matches],
        }
        progress(60 + int(30 * (idx + 1) / max(len(repo_pairs), 1)),
                 f"Compared {repo_a} vs {repo_b}")

    progress(92, "Analyzing commit history for large/suspicious commits")
    all_commits = [c for commits in repo_commits.values() for c in commits]
    large_commit_flags = detect_large_commits(all_commits)

    progress(97, "Aggregating results")
    similarity_matrix = {
        repo: {other: (1.0 if repo == other else 0.0) for other in usable_repos}
        for repo in usable_repos
    }
    for key, res in pair_results.items():
        a, b = res["repo_a"], res["repo_b"]
        similarity_matrix[a][b] = res["repo_similarity_score"]
        similarity_matrix[b][a] = res["repo_similarity_score"]

    flagged_pairs = sorted(
        [res for res in pair_results.values() if res["flagged_file_pairs"]],
        key=lambda r: r["repo_similarity_score"], reverse=True,
    )

    progress(100, "Done")
    return {
        "status": "completed",
        "language": language,
        "branch": branch,
        "similarity_threshold": similarity_threshold,
        "repos_analyzed": usable_repos,
        "clone_errors": clone_errors,
        "similarity_matrix": similarity_matrix,
        "repo_pairs": pair_results,
        "flagged_pairs_summary": [
            {"repo_a": r["repo_a"], "repo_b": r["repo_b"],
             "score": r["repo_similarity_score"],
             "flagged_files": len(r["flagged_file_pairs"])}
            for r in flagged_pairs
        ],
        "large_commit_flags": [asdict(f) for f in large_commit_flags],
    }
