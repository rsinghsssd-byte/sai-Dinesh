"""
demo_offline.py
----------------
Runs the full analysis pipeline (preprocessing -> similarity ->
commit analysis -> aggregation -> report) against three synthetic
"repositories" with no network access required. Useful for a quick
sanity check right after `pip install -r requirements.txt`, before
you point the app at real GitHub URLs.

Run with:  python3 tests/demo_offline.py
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.analyzer as analyzer
from app.git_service import RepoFile
from app.commit_analysis import CommitInfo
from app.report import generate_html_report

ORIGINAL_SRC = """
def binary_search(arr, target):
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
"""

COPYCAT_SRC = """
def bsearch(data, key):
    lo, hi = 0, len(data) - 1
    while lo <= hi:
        m = (lo + hi) // 2
        if data[m] == key:
            return m
        elif data[m] < key:
            lo = m + 1
        else:
            hi = m - 1
    return -1
"""

INDEPENDENT_SRC = """
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)
"""

FILES = {
    "https://github.com/x/original": [RepoFile("https://github.com/x/original", "main.py", ORIGINAL_SRC)],
    "https://github.com/y/copycat": [RepoFile("https://github.com/y/copycat", "solution.py", COPYCAT_SRC)],
    "https://github.com/z/independent": [RepoFile("https://github.com/z/independent", "utils.py", INDEPENDENT_SRC)],
}

COMMITS = {
    "https://github.com/x/original": [
        CommitInfo("https://github.com/x/original", "a1", "alice",
                    "Implemented Dijkstra shortest path using a priority queue",
                    datetime.now(), 20, 0),
    ],
    "https://github.com/y/copycat": [
        CommitInfo("https://github.com/y/copycat", "b1", "bob",
                    "Implemented Dijkstras shortest path algorithm with priority queue",
                    datetime.now(), 420, 0),
        CommitInfo("https://github.com/y/copycat", "b0", "bob", "init", datetime.now(), 10, 0),
    ],
    "https://github.com/z/independent": [
        CommitInfo("https://github.com/z/independent", "c1", "carol",
                    "add factorial util", datetime.now(), 12, 0),
    ],
}


def fake_clone_repo(url, branch, workdir):
    return "/fake/" + url


def fake_extract_files(local_path, repo_url, language):
    return FILES[repo_url]


def fake_extract_commit_history(local_path, repo_url, branch, max_commits=500):
    return COMMITS[repo_url]


def main():
    analyzer.clone_repo = fake_clone_repo
    analyzer.extract_files = fake_extract_files
    analyzer.extract_commit_history = fake_extract_commit_history

    result = analyzer.run_analysis(
        repo_urls=list(FILES.keys()),
        language="python",
        branch="main",
        similarity_threshold=0.5,
    )

    print("=== JSON RESULT (truncated) ===")
    print(json.dumps(result, indent=2, default=str)[:1500], "...\n")

    html_report = generate_html_report("demo-job", {"language": "python", "branch": "main", "similarity_threshold": 0.5}, result)
    out_path = os.path.join(os.path.dirname(__file__), "demo_report.html")
    with open(out_path, "w") as f:
        f.write(html_report)
    print(f"HTML report written to: {out_path}")

    assert result["flagged_pairs_summary"], "Expected the original/copycat pair to be flagged"
    assert result["large_commit_flags"], "Expected the 420-line commit to be flagged"
    print("\nDemo assertions passed: plagiarism correctly detected, innocent repo correctly cleared.")


if __name__ == "__main__":
    main()
