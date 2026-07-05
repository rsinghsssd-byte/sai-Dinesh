"""
similarity.py
--------------
Structural, token-based similarity engine (same family of technique used by
MOSS/JPlag):

1. Tokenize the *canonical* (comment-stripped, whitespace-collapsed,
   identifier-normalized) source into a flat token stream.
2. Build k-grams ("shingles") over the token stream.
3. Hash every k-gram, then apply the *winnowing* algorithm (Schleimer,
   Wilkerson & Aiken, 2003) to pick a robust, position-independent subset of
   hashes ("fingerprints") per document. Winnowing guarantees that any shared
   substring of length >= k between two documents produces at least one
   shared fingerprint, while keeping the fingerprint set small.
4. Compare fingerprint sets between two files with containment similarity
   (shared fingerprints / fingerprints of the smaller doc) -- this is more
   robust than plain Jaccard when one file is a subset of a much larger one
   (e.g. one suspicious function pasted into an otherwise original file).
5. For explainability, also compute a line-level alignment (difflib) on the
   *normalized* (not identifier-renamed) source so the UI can show a
   side-by-side diff with the actually matching lines highlighted.
"""
from __future__ import annotations
import difflib
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

K_GRAM_SIZE = 5          # tokens per shingle
WINDOW_SIZE = 4          # winnowing window (in shingles)


def tokenize(canonical_source: str) -> List[str]:
    """Canonical source is already whitespace-collapsed; splitting on
    whitespace approximates a token stream cheaply and language-agnostically
    while operators/punctuation remain attached where relevant (e.g. '+=').
    For finer-grained tokens we also split off standalone punctuation."""
    import re
    return re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", canonical_source)


def _hash_gram(tokens: Tuple[str, ...]) -> int:
    h = hashlib.md5(" ".join(tokens).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def winnow_fingerprints(tokens: List[str], k: int = K_GRAM_SIZE,
                         window: int = WINDOW_SIZE) -> Set[int]:
    """Returns the set of winnowed fingerprint hashes for a token stream."""
    if len(tokens) < k:
        return {_hash_gram(tuple(tokens))} if tokens else set()

    grams = [tuple(tokens[i:i + k]) for i in range(len(tokens) - k + 1)]
    hashes = [_hash_gram(g) for g in grams]

    fingerprints: Set[int] = set()
    if len(hashes) < window:
        fingerprints.update(hashes)
        return fingerprints

    # sliding window minimum hash selection (winnowing)
    prev_min_pos = -1
    for i in range(len(hashes) - window + 1):
        win = hashes[i:i + window]
        min_val = min(win)
        # rightmost occurrence of min in window -> fewer duplicate picks
        min_pos = i + max(idx for idx, v in enumerate(win) if v == min_val)
        if min_pos != prev_min_pos:
            fingerprints.add(min_val)
            prev_min_pos = min_pos
    return fingerprints


@dataclass
class FileSimilarity:
    path_a: str
    path_b: str
    containment: float          # shared fingerprints / smaller doc's fingerprints
    jaccard: float               # shared / union
    matched_line_ratio: float    # difflib ratio on normalized (non-renamed) source
    matching_blocks: List[Tuple[int, int, int]] = field(default_factory=list)


def compare_fingerprints(fp_a: Set[int], fp_b: Set[int]) -> Tuple[float, float]:
    if not fp_a or not fp_b:
        return 0.0, 0.0
    shared = fp_a & fp_b
    union = fp_a | fp_b
    containment = len(shared) / min(len(fp_a), len(fp_b))
    jaccard = len(shared) / len(union)
    return containment, jaccard


def line_level_matches(norm_a: str, norm_b: str) -> Tuple[float, List[Tuple[int, int, int]]]:
    """Line-based longest-matching-block detection for the side-by-side
    diff view. Returns overall ratio + list of (a_start, b_start, length)
    matching blocks (in "lines", after splitting normalized source on the
    boundary markers we re-insert)."""
    lines_a = norm_a.split(". ") if norm_a else []
    lines_b = norm_b.split(". ") if norm_b else []
    sm = difflib.SequenceMatcher(a=lines_a, b=lines_b, autojunk=False)
    ratio = sm.ratio()
    blocks = [
        (b.a, b.b, b.size)
        for b in sm.get_matching_blocks()
        if b.size >= 2  # ignore trivial 1-token coincidences
    ]
    return ratio, blocks


def compare_files(path_a: str, canonical_a: str, normalized_a: str,
                   path_b: str, canonical_b: str, normalized_b: str) -> FileSimilarity:
    tokens_a = tokenize(canonical_a)
    tokens_b = tokenize(canonical_b)
    fp_a = winnow_fingerprints(tokens_a)
    fp_b = winnow_fingerprints(tokens_b)
    containment, jaccard = compare_fingerprints(fp_a, fp_b)
    ratio, blocks = line_level_matches(normalized_a, normalized_b)
    return FileSimilarity(
        path_a=path_a, path_b=path_b,
        containment=round(containment, 4),
        jaccard=round(jaccard, 4),
        matched_line_ratio=round(ratio, 4),
        matching_blocks=blocks,
    )


def combined_score(fs: FileSimilarity) -> float:
    """Single explainable 0-1 score per file pair: weighted toward
    containment (robust to partial copy-paste) with jaccard and line-ratio
    as corroborating signals."""
    return round(0.55 * fs.containment + 0.25 * fs.jaccard + 0.20 * fs.matched_line_ratio, 4)
