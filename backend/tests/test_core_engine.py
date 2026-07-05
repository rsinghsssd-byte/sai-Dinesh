import sys
import os
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.preprocessing import normalize_source, strip_comments, language_for_extension
from app.similarity import compare_files, combined_score, tokenize, winnow_fingerprints
from app.commit_analysis import CommitInfo, detect_large_commits, detect_similar_commit_messages


ORIGINAL = """
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

RENAMED = """
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

UNRELATED = """
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)
"""


class TestPreprocessing(unittest.TestCase):
    def test_extension_mapping(self):
        self.assertEqual(language_for_extension(".py"), "python")
        self.assertEqual(language_for_extension(".cpp"), "cpp")
        self.assertIsNone(language_for_extension(".xyz"))

    def test_comment_stripping_preserves_strings(self):
        src = 'x = "http://not-a-comment.com"  # real comment\n'
        stripped = strip_comments(src, "python")
        self.assertIn('"http://not-a-comment.com"', stripped)
        self.assertNotIn("real comment", stripped)

    def test_identifier_normalization_defeats_renaming(self):
        a = normalize_source("a.py", ORIGINAL, "python")
        b = normalize_source("b.py", RENAMED, "python")
        self.assertEqual(a.canonical_source, b.canonical_source)

    def test_unrelated_code_normalizes_differently(self):
        a = normalize_source("a.py", ORIGINAL, "python")
        c = normalize_source("c.py", UNRELATED, "python")
        self.assertNotEqual(a.canonical_source, c.canonical_source)


class TestSimilarity(unittest.TestCase):
    def test_identical_files_score_1(self):
        fs = compare_files("a", *[normalize_source("a", ORIGINAL, "python").canonical_source,
                                    normalize_source("a", ORIGINAL, "python").normalized_source],
                            "a2", *[normalize_source("a2", ORIGINAL, "python").canonical_source,
                                     normalize_source("a2", ORIGINAL, "python").normalized_source])
        self.assertGreaterEqual(combined_score(fs), 0.99)

    def test_renamed_identifiers_still_flagged(self):
        na = normalize_source("a.py", ORIGINAL, "python")
        nb = normalize_source("b.py", RENAMED, "python")
        fs = compare_files(na.path, na.canonical_source, na.normalized_source,
                            nb.path, nb.canonical_source, nb.normalized_source)
        score = combined_score(fs)
        self.assertGreaterEqual(score, 0.75, "Renamed-variable plagiarism must still be flagged")

    def test_unrelated_code_scores_low(self):
        na = normalize_source("a.py", ORIGINAL, "python")
        nc = normalize_source("c.py", UNRELATED, "python")
        fs = compare_files(na.path, na.canonical_source, na.normalized_source,
                            nc.path, nc.canonical_source, nc.normalized_source)
        self.assertLess(combined_score(fs), 0.3)

    def test_winnowing_handles_short_token_streams(self):
        # regression guard: very short files shouldn't crash the winnowing loop
        fps = winnow_fingerprints(tokenize("x = 1"))
        self.assertIsInstance(fps, set)

    def test_tokenize_splits_punctuation(self):
        toks = tokenize("a += 1;")
        self.assertIn("+", toks)
        self.assertIn(";", toks)


class TestCommitAnalysis(unittest.TestCase):
    def test_large_commit_flagged_via_leave_one_out(self):
        commits = [
            CommitInfo("r", "s1", "alice", "init", datetime.now(), 20, 0),
            CommitInfo("r", "s2", "alice", "helpers", datetime.now(), 15, 2),
            CommitInfo("r", "s3", "alice", "paste solution", datetime.now(), 480, 0),
        ]
        flags = detect_large_commits(commits)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].sha, "s3")

    def test_normal_commits_not_flagged(self):
        commits = [
            CommitInfo("r", "s1", "alice", "init", datetime.now(), 20, 0),
            CommitInfo("r", "s2", "alice", "helpers", datetime.now(), 25, 2),
            CommitInfo("r", "s3", "alice", "more helpers", datetime.now(), 22, 1),
        ]
        self.assertEqual(detect_large_commits(commits), [])

    def test_similar_commit_messages_detected(self):
        a = [CommitInfo("r1", "s1", "a", "Implemented Dijkstra shortest path using a priority queue", datetime.now(), 10, 0)]
        b = [CommitInfo("r2", "t1", "b", "Implemented Dijkstras shortest path algorithm with priority queue", datetime.now(), 10, 0)]
        matches = detect_similar_commit_messages(a, b)
        self.assertEqual(len(matches), 1)
        self.assertGreaterEqual(matches[0].similarity, 0.85)

    def test_dissimilar_commit_messages_not_matched(self):
        a = [CommitInfo("r1", "s1", "a", "Fix off-by-one bug in loop boundary", datetime.now(), 5, 1)]
        b = [CommitInfo("r2", "t1", "b", "Add unit tests for the payment gateway", datetime.now(), 40, 0)]
        self.assertEqual(detect_similar_commit_messages(a, b), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
