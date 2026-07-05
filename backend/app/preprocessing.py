"""
preprocessing.py
----------------
Language-aware source normalization used before similarity comparison.

Steps applied to every source file:
  1. Strip comments (line + block, per-language syntax).
  2. Strip string/char literal *contents* (but keep a placeholder token,
     since literal contents are rarely meaningful for structural plagiarism
     and swapping them is the easiest evasion trick).
  3. Collapse all whitespace.
  4. Normalize identifiers: every variable/function/class name that is not a
     reserved keyword of the language is replaced by a positional token
     (ID1, ID2, ...) in order of first appearance *within that file*. This
     defeats "rename all my variables" plagiarism while preserving code
     structure, control flow, operators, and literals' shape.

The output of `normalize_source()` is itself not shown to the end user;
it purely feeds the tokenizer/similarity engine. Original source is kept
separately for the side-by-side diff view.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

SUPPORTED_LANGUAGES = {
    "python": {"extensions": [".py"]},
    "java": {"extensions": [".java"]},
    "c": {"extensions": [".c", ".h"]},
    "cpp": {"extensions": [".cpp", ".cc", ".cxx", ".hpp", ".hh"]},
    "javascript": {"extensions": [".js", ".jsx"]},
    "typescript": {"extensions": [".ts", ".tsx"]},
    "go": {"extensions": [".go"]},
    "csharp": {"extensions": [".cs"]},
}

# Reserved words are never renamed -> control-flow/keyword skeleton stays visible,
# which is exactly what should still "match" across renamed-variable plagiarism.
_KEYWORDS = {
    "python": {
        "False","None","True","and","as","assert","async","await","break","class",
        "continue","def","del","elif","else","except","finally","for","from",
        "global","if","import","in","is","lambda","nonlocal","not","or","pass",
        "raise","return","try","while","with","yield","self","print","len","range",
        "int","str","float","list","dict","set","tuple","bool","object","super",
    },
    "java": {
        "abstract","assert","boolean","break","byte","case","catch","char","class",
        "const","continue","default","do","double","else","enum","extends","final",
        "finally","float","for","goto","if","implements","import","instanceof","int",
        "interface","long","native","new","package","private","protected","public",
        "return","short","static","strictfp","super","switch","synchronized","this",
        "throw","throws","transient","try","void","volatile","while","String","System",
        "true","false","null","var",
    },
    "c": {
        "auto","break","case","char","const","continue","default","do","double",
        "else","enum","extern","float","for","goto","if","int","long","register",
        "return","short","signed","sizeof","static","struct","switch","typedef",
        "union","unsigned","void","volatile","while","printf","scanf","NULL",
    },
    "cpp": {
        "alignas","alignof","and","asm","auto","bool","break","case","catch","char",
        "class","const","constexpr","continue","decltype","default","delete","do",
        "double","else","enum","explicit","export","extern","false","float","for",
        "friend","goto","if","inline","int","long","mutable","namespace","new",
        "noexcept","nullptr","operator","private","protected","public","register",
        "return","short","signed","sizeof","static","struct","switch","template",
        "this","throw","true","try","typedef","typeid","typename","union",
        "unsigned","using","virtual","void","volatile","while","std","cout","cin",
        "endl","vector","string",
    },
    "javascript": {
        "break","case","catch","class","const","continue","debugger","default",
        "delete","do","else","export","extends","finally","for","function","if",
        "import","in","instanceof","new","return","super","switch","this","throw",
        "try","typeof","var","void","while","with","yield","let","async","await",
        "console","log","true","false","null","undefined",
    },
    "typescript": None,  # inherits javascript
    "go": {
        "break","case","chan","const","continue","default","defer","else",
        "fallthrough","for","func","go","goto","if","import","interface","map",
        "package","range","return","select","struct","switch","type","var",
        "true","false","nil","fmt","Println","Printf","string","int","bool",
        "error","nil",
    },
    "csharp": {
        "abstract","as","base","bool","break","byte","case","catch","char","checked",
        "class","const","continue","decimal","default","delegate","do","double",
        "else","enum","event","explicit","extern","false","finally","fixed","float",
        "for","foreach","goto","if","implicit","in","int","interface","internal",
        "is","lock","long","namespace","new","null","object","operator","out",
        "override","params","private","protected","public","readonly","ref",
        "return","sbyte","sealed","short","sizeof","stackalloc","static","string",
        "struct","switch","this","throw","true","try","typeof","uint","ulong",
        "unchecked","unsafe","ushort","using","virtual","void","volatile","while",
        "Console","WriteLine","var",
    },
}
_KEYWORDS["typescript"] = _KEYWORDS["javascript"]

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# (line_comment_prefixes, block_comment_pairs) per language
_COMMENT_SYNTAX = {
    "python": (["#"], []),
    "java": (["//"], [("/*", "*/")]),
    "c": (["//"], [("/*", "*/")]),
    "cpp": (["//"], [("/*", "*/")]),
    "javascript": (["//"], [("/*", "*/")]),
    "typescript": (["//"], [("/*", "*/")]),
    "go": (["//"], [("/*", "*/")]),
    "csharp": (["//"], [("/*", "*/")]),
}

_STRING_RE = re.compile(
    r'"""(?:\\.|[^"\\])*"""'      # python triple double
    r"|'''(?:\\.|[^'\\])*'''"     # python triple single
    r'|"(?:\\.|[^"\\\n])*"'       # double-quoted
    r"|'(?:\\.|[^'\\\n])*'",      # single-quoted
    re.DOTALL,
)


def language_for_extension(ext: str) -> str | None:
    ext = ext.lower()
    for lang, meta in SUPPORTED_LANGUAGES.items():
        if ext in meta["extensions"]:
            return lang
    return None


def strip_comments(source: str, language: str) -> str:
    """Remove block and line comments while leaving strings untouched
    (a naive regex would kill '//' inside a string literal, so we walk
    char by char, tracking whether we are inside a string)."""
    line_prefixes, block_pairs = _COMMENT_SYNTAX.get(language, (["//"], [("/*", "*/")]))
    out = []
    i, n = 0, len(source)
    in_string = None  # holds the quote char / triple-quote currently open
    while i < n:
        # Handle python triple-quoted strings
        if language == "python" and in_string is None and source[i:i+3] in ('"""', "'''"):
            triple = source[i:i+3]
            end = source.find(triple, i + 3)
            end = end + 3 if end != -1 else n
            out.append(source[i:end])
            i = end
            continue
        ch = source[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(source[i+1])
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            out.append(ch)
            i += 1
            continue
        # block comment
        matched_block = False
        for start_tok, end_tok in block_pairs:
            if source.startswith(start_tok, i):
                end = source.find(end_tok, i + len(start_tok))
                end = end + len(end_tok) if end != -1 else n
                out.append(" ")  # preserve token boundary
                i = end
                matched_block = True
                break
        if matched_block:
            continue
        # line comment
        matched_line = False
        for tok in line_prefixes:
            if source.startswith(tok, i):
                nl = source.find("\n", i)
                i = nl if nl != -1 else n
                matched_line = True
                break
        if matched_line:
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def mask_string_literals(source: str) -> str:
    """Replace literal contents with a fixed placeholder so that changing
    string constants doesn't create a false 'difference' signal, while the
    presence of a literal is still visible (helps flag copy-paste that only
    edits print messages)."""
    return _STRING_RE.sub('"STR"', source)


def normalize_identifiers(source: str, language: str) -> str:
    keywords = _KEYWORDS.get(language, set())
    mapping: dict[str, str] = {}
    counter = [0]

    def repl(m: re.Match) -> str:
        word = m.group(0)
        if word in keywords or word[0].isdigit():
            return word
        if word not in mapping:
            counter[0] += 1
            mapping[word] = f"ID{counter[0]}"
        return mapping[word]

    return _IDENTIFIER_RE.sub(repl, source)


def collapse_whitespace(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip()


@dataclass
class NormalizedFile:
    path: str
    language: str
    original_source: str
    normalized_source: str      # comments/strings/whitespace stripped, identifiers kept
    canonical_source: str        # + identifiers normalized -> used for similarity
    loc: int


def normalize_source(path: str, source: str, language: str) -> NormalizedFile:
    no_comments = strip_comments(source, language)
    masked = mask_string_literals(no_comments)
    normalized = collapse_whitespace(masked)
    canonical = collapse_whitespace(normalize_identifiers(masked, language))
    loc = len([l for l in source.splitlines() if l.strip()])
    return NormalizedFile(
        path=path,
        language=language,
        original_source=source,
        normalized_source=normalized,
        canonical_source=canonical,
        loc=loc,
    )
