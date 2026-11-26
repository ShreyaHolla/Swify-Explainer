"""Grounding: the official text a lesson is written from, so facts and code come from the source, not from memory.

For Swift, the source is The Swift Programming Language (the Swift book), read as Markdown from its official
repository (github.com/swiftlang/swift-book). A chapter is split into its sections and the sections that best match
the topic are kept, up to a size the free LLM tiers accept. You can always paste your own notes instead or as well.
"""
import re

import requests

BOOK_RAW = "https://raw.githubusercontent.com/swiftlang/swift-book/main/TSPL.docc/LanguageGuide/{}.md"
BOOK_WEB = "https://docs.swift.org/swift-book/documentation/the-swift-programming-language/{}/"

# chapter title -> file name in the book's repository
SWIFT_BOOK = {
    "The Basics": "TheBasics", "Basic Operators": "BasicOperators", "Strings and Characters": "StringsAndCharacters",
    "Collection Types": "CollectionTypes", "Control Flow": "ControlFlow", "Functions": "Functions",
    "Closures": "Closures", "Enumerations": "Enumerations", "Structures and Classes": "ClassesAndStructures",
    "Properties": "Properties", "Methods": "Methods", "Subscripts": "Subscripts", "Inheritance": "Inheritance",
    "Initialization": "Initialization", "Deinitialization": "Deinitialization", "Optional Chaining": "OptionalChaining",
    "Error Handling": "ErrorHandling", "Concurrency": "Concurrency", "Macros": "Macros", "Type Casting": "TypeCasting",
    "Nested Types": "NestedTypes", "Extensions": "Extensions", "Protocols": "Protocols", "Generics": "Generics",
    "Opaque and Boxed Types": "OpaqueTypes", "Automatic Reference Counting": "AutomaticReferenceCounting",
    "Memory Safety": "MemorySafety", "Access Control": "AccessControl", "Advanced Operators": "AdvancedOperators",
}

# extra words that point to a chapter (topic words are matched against titles and these)
HINTS = {
    "The Basics": "optional optionals nil unwrap if let guard constant variable let var type annotation tuple int string bool",
    "Basic Operators": "operator ternary nil-coalescing ?? range ... ..< remainder",
    "Strings and Characters": "string character interpolation unicode substring",
    "Collection Types": "array arrays set sets dictionary dictionaries collection",
    "Control Flow": "for-in while repeat switch if else break continue fallthrough guard loop",
    "Functions": "function func parameter argument label return inout variadic",
    "Closures": "closure closures trailing capture escaping autoclosure sorted map filter $0",
    "Enumerations": "enum enumeration case associated raw value",
    "Structures and Classes": "struct structure class value type reference type identity",
    "Properties": "property properties computed stored lazy observer willset didset wrapper static",
    "Error Handling": "error throw throws try catch do result",
    "Concurrency": "async await task actor concurrency sendable",
    "Protocols": "protocol conformance delegate",
    "Generics": "generic generics where associatedtype",
    "Optional Chaining": "optional chaining ?.",
    "Extensions": "extension extend",
    "Initialization": "init initializer initialization",
    "Automatic Reference Counting": "arc memory weak unowned retain cycle",
    "Access Control": "private public internal fileprivate open",
}

# phrases people say -> the words the book uses
SYNONYMS = {
    "if let": "optional binding", "guard let": "optional binding early exit", "unwrap": "optional binding force unwrapping",
    "??": "nil-coalescing operator", "struct": "structures", "class": "classes", "array": "arrays",
    "dictionary": "dictionaries", "async": "asynchronous functions", "await": "asynchronous functions",
    "try": "handling errors", "catch": "do-catch", "capture": "capturing values", "trailing": "trailing closures",
    "escaping": "escaping closures", "weak": "strong reference cycles", "lazy": "lazy stored properties",
}

MAX_CHARS = 9000  # about 2,600 tokens: leaves room for the answer within an 8,000 tokens-per-minute free tier


def words(s):
    return set(re.findall(r"[a-z$?.]+", s.lower()))


def stems(s):
    """Crude stems (first 5 letters) so 'unwrapping' meets 'unwrap' and 'closures' meets 'closure'."""
    return {w[:5] for w in words(s) if len(w) > 2}


def expand(topic):
    t = topic.lower()
    return t + " " + " ".join(v for k, v in SYNONYMS.items() if k in t)


def suggest_chapter(topic):
    """Best-matching Swift book chapter for a topic (by title and hint words)."""
    tw = words(expand(topic))
    best, score = "The Basics", 0
    for title in SWIFT_BOOK:
        cw = words(title + " " + HINTS.get(title, ""))
        s = len(tw & cw) * 2 + sum(1 for w in tw if any(w in c or c in w for c in cw if len(c) > 3))
        if s > score:
            best, score = title, s
    return best


def fetch_chapter(title, timeout=20):
    r = requests.get(BOOK_RAW.format(SWIFT_BOOK[title]), timeout=timeout, headers={"User-Agent": "swify-explainer"})
    r.raise_for_status()
    md = re.sub(r"<!--.*?-->", "", r.text, flags=re.S)   # test-only code and editor notes
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md


def sections(md):
    """[(heading, text)] split at ## and ### headings; the chapter intro comes first."""
    parts, head, buf = [], "Introduction", []
    for line in md.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                parts.append((head, "\n".join(buf).strip()))
            head, buf = m.group(2).strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    if "".join(buf).strip():
        parts.append((head, "\n".join(buf).strip()))
    return parts


def excerpt(title, topic, max_chars=MAX_CHARS):
    """The sections most relevant to the topic, in book order, within max_chars. Returns (text, url, used headings)."""
    parts = sections(fetch_chapter(title))
    ts = stems(expand(topic)) - {"swift", "the", "and", "with", "using"}
    scored = []
    for i, (h, t) in enumerate(parts):
        hs, bs = stems(h), stems(t)
        s = 4 * len(ts & hs) + len(ts & bs) / 3 + (2 if i == 0 else 0) - i * 0.05  # headings count most; intro favoured
        scored.append((s, i))
    keep, size = set(), 0
    for s, i in sorted(scored, reverse=True):
        h, t = parts[i]
        if s < 1 and i != 0:  # unrelated sections are left out rather than used as filler
            continue
        if size + len(t) + len(h) + 8 > max_chars:
            continue
        keep.add(i)
        size += len(t) + len(h) + 8
    used = [parts[i][0] for i in sorted(keep)]
    text = "\n\n".join(f"## {parts[i][0]}\n{parts[i][1]}" for i in sorted(keep))
    url = BOOK_WEB.format(SWIFT_BOOK[title].lower())
    return text, url, used


if __name__ == "__main__":
    import sys
    t = " ".join(sys.argv[1:]) or "closures capturing values"
    ch = suggest_chapter(t)
    text, url, used = excerpt(ch, t)
    print(ch, url, len(text), used)
