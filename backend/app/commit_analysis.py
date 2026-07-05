"""
commit_analysis.py
-------------------
Commit-level indicators of copying, independent of file-content similarity:

1. Large / sudden commits: a commit that adds a big chunk of code in one
   shot (little iterative history) is a classic sign of pasting in someone
   else's finished work rather than writing it incrementally.
2. Near-identical commit messages across *different* repositories (e.g. two
   candidates both commit "Implemented Dijkstra's algorithm using priority
   queue" almost verbatim) -- often the copied README/commit message goes
   along with the copied code.
3. Commit timing outliers (optional signal): a huge commit relative to the
   author's own historical average size is also flagged.
"""
from __future__ import annotations
import difflib
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, pstdev
from typing import List, Optional


@dataclass
class CommitInfo:
    repo: str
    sha: str
    author: str
    message: str
    timestamp: datetime
    lines_added: int
    lines_removed: int
    files_changed: List[str] = field(default_factory=list)


@dataclass
class LargeCommitFlag:
    repo: str
    sha: str
    message: str
    lines_added: int
    z_score: float
    reason: str


@dataclass
class CommitMessageMatch:
    repo_a: str
    sha_a: str
    message_a: str
    repo_b: str
    sha_b: str
    message_b: str
    similarity: float


LARGE_COMMIT_ABS_THRESHOLD = 150   # lines added, absolute floor
LARGE_COMMIT_Z_THRESHOLD = 2.0     # standard deviations above author's own mean
COMMIT_MESSAGE_SIMILARITY_THRESHOLD = 0.85


def detect_large_commits(commits: List[CommitInfo]) -> List[LargeCommitFlag]:
    """Flags commits that are unusually large relative to (a) an absolute
    floor and (b) the author's own historical commit-size distribution --
    a sudden 500-line commit from someone who otherwise commits ~20 lines
    at a time is a stronger signal than the same commit from someone who
    always commits in large chunks."""
    flags: List[LargeCommitFlag] = []
    by_author: dict[str, List[CommitInfo]] = {}
    for c in commits:
        by_author.setdefault((c.repo, c.author), []).append(c)

    for (repo, author), author_commits in by_author.items():
        for c in author_commits:
            # Leave-one-out baseline: compare this commit against the
            # author's *other* commits, so one giant commit can't inflate
            # its own baseline and mask itself.
            others = [o.lines_added for o in author_commits if o.sha != c.sha]
            if not others:
                if c.lines_added >= LARGE_COMMIT_ABS_THRESHOLD:
                    flags.append(LargeCommitFlag(
                        repo=repo, sha=c.sha, message=c.message,
                        lines_added=c.lines_added, z_score=0.0,
                        reason=f"{c.lines_added} lines added; author's only commit on record",
                    ))
                continue
            mu = mean(others)
            sigma = pstdev(others) if len(others) > 1 else max(mu * 0.5, 1.0)
            z = (c.lines_added - mu) / sigma if sigma > 0 else 0.0
            if c.lines_added >= LARGE_COMMIT_ABS_THRESHOLD and z >= LARGE_COMMIT_Z_THRESHOLD:
                reason = (
                    f"{c.lines_added} lines added in a single commit "
                    f"(author's typical commit: {mu:.0f} lines, z={z:.1f})"
                )
                flags.append(LargeCommitFlag(
                    repo=repo, sha=c.sha, message=c.message,
                    lines_added=c.lines_added, z_score=round(z, 2), reason=reason,
                ))
    return flags


def detect_similar_commit_messages(
    commits_a: List[CommitInfo], commits_b: List[CommitInfo],
    threshold: float = COMMIT_MESSAGE_SIMILARITY_THRESHOLD,
) -> List[CommitMessageMatch]:
    """Pairwise commit-message comparison across two repositories. O(n*m)
    is fine at the scale of a single repo's commit history (hundreds, not
    millions)."""
    matches: List[CommitMessageMatch] = []
    for ca in commits_a:
        msg_a = ca.message.strip().lower()
        if len(msg_a) < 8:
            continue  # too short to be meaningful ("fix", "wip", etc.)
        for cb in commits_b:
            msg_b = cb.message.strip().lower()
            if len(msg_b) < 8:
                continue
            ratio = difflib.SequenceMatcher(a=msg_a, b=msg_b).ratio()
            if ratio >= threshold:
                matches.append(CommitMessageMatch(
                    repo_a=ca.repo, sha_a=ca.sha, message_a=ca.message,
                    repo_b=cb.repo, sha_b=cb.sha, message_b=cb.message,
                    similarity=round(ratio, 3),
                ))
    return matches
