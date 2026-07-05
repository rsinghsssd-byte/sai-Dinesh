"""
git_service.py
---------------
Clones repositories and extracts (a) the current file tree for the target
branch/language and (b) full commit history with per-commit diff stats.

Requires `gitpython` (pip install gitpython) and outbound network access to
reach GitHub -- both available in a normal deployment; this sandbox used to
author this project has neither, so this module is exercised by integration
tests only in an environment with network access (see tests/test_integration_MANUAL.md).
"""
from __future__ import annotations
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import List

from .preprocessing import SUPPORTED_LANGUAGES, language_for_extension
from .commit_analysis import CommitInfo

try:
    import git  # GitPython
except ImportError:  # pragma: no cover - allows unit tests to import module without the dep
    git = None

MAX_REPO_SIZE_MB = 500
CLONE_TIMEOUT_SECONDS = 300


@dataclass
class RepoFile:
    repo_url: str
    path: str
    content: str


class GitServiceError(Exception):
    pass


def _require_gitpython():
    if git is None:
        raise GitServiceError(
            "GitPython is not installed in this environment. "
            "Run `pip install gitpython` (see backend/requirements.txt)."
        )


def clone_repo(repo_url: str, branch: str, workdir: str) -> str:
    """Shallow-clones a single branch of repo_url into workdir. Returns the
    local path. Depth is unbounded (full=False) only when commit history is
    needed for commit-level analysis; callers pass depth explicitly."""
    _require_gitpython()
    local_path = os.path.join(workdir, _safe_dirname(repo_url))
    try:
        git.Repo.clone_from(
            repo_url, local_path, branch=branch, single_branch=True,
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the API layer
        raise GitServiceError(f"Failed to clone {repo_url} (branch={branch}): {exc}") from exc
    return local_path


def _safe_dirname(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].replace(".git", "") + "_" + str(abs(hash(repo_url)) % 10_000)


def extract_files(local_path: str, repo_url: str, language: str) -> List[RepoFile]:
    """Walks the working tree and returns every file matching the target
    language's extensions, skipping vendored/dependency directories."""
    exts = tuple(SUPPORTED_LANGUAGES[language]["extensions"])
    ignore_dirs = {".git", "node_modules", "venv", ".venv", "vendor", "dist",
                   "build", "target", "__pycache__", ".idea", ".vscode"}
    files: List[RepoFile] = []
    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(exts):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, local_path)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                except OSError:
                    continue
                if content.strip():
                    files.append(RepoFile(repo_url=repo_url, path=rel, content=content))
    return files


def extract_commit_history(local_path: str, repo_url: str, branch: str,
                            max_commits: int = 500) -> List[CommitInfo]:
    _require_gitpython()
    repo = git.Repo(local_path)
    commits: List[CommitInfo] = []
    try:
        commit_iter = repo.iter_commits(branch, max_count=max_commits)
    except Exception as exc:  # noqa: BLE001
        raise GitServiceError(f"Failed to read commit history for {repo_url}: {exc}") from exc

    for c in commit_iter:
        try:
            stats = c.stats.total
        except Exception:  # noqa: BLE001
            stats = {"insertions": 0, "deletions": 0}
        files_changed = list(c.stats.files.keys()) if hasattr(c.stats, "files") else []
        commits.append(CommitInfo(
            repo=repo_url,
            sha=c.hexsha[:10],
            author=c.author.name or c.author.email or "unknown",
            message=c.message.strip(),
            timestamp=datetime.fromtimestamp(c.committed_date),
            lines_added=stats.get("insertions", 0),
            lines_removed=stats.get("deletions", 0),
            files_changed=files_changed,
        ))
    return commits


class TempWorkdir:
    """Context manager that guarantees clone directories are cleaned up
    even if analysis raises partway through."""
    def __enter__(self) -> str:
        self.path = tempfile.mkdtemp(prefix="plagcheck_")
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
