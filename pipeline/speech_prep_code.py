"""Make code words speakable while captions keep the code as written.

Write code in narration between backticks: `Int?`, `value!`, `print()`. Only backticked words get the code
rules (so a sentence ending in "crashes!" is read normally); the backticks are removed from the caption text.
Symbol-only tokens such as ?? or == are always spoken by name.

tokens_for("Use `Int?` and ?? here.") ->
  [{"text": "Use", "spoken": "Use"}, {"text": "Int?", "spoken": "optional Int"}, {"text": "and", ...},
   {"text": "??", "spoken": "double question mark"}, {"text": "here.", "spoken": "here."}]

Add channel-specific words to SAY (exact token) or to the pattern rules below.
"""
import re

# exact tokens (punctuation at the end is kept and re-attached)
SAY = {
    "??": "double question mark",
    "==": "equals equals",
    "!=": "not equal",
    "->": "returns",
    "=>": "arrow",
    "&&": "and",
    "||": "or",
    "!": "exclamation mark",
    "nil": "nil",
    "func": "func",
    "var": "var",
    "let": "let",
    "struct": "struct",
    "enum": "enum",
    "SwiftUI": "Swift U I",
    "UIKit": "U I kit",
    "Xcode": "X code",
    "iOS": "i O S",
    "macOS": "mac O S",
    "async": "a-sink",
    "JSON": "jason",
    "API": "A P I",
}

RULES = [
    (re.compile(r"^([A-Z][A-Za-z0-9]*)\?$"), lambda m: f"optional {m.group(1)}"),      # Int? -> optional Int
    (re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)!$"), lambda m: f"{m.group(1)} force unwrapped"),  # value!
    (re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)$"), lambda m: m.group(1)),              # print() -> print
    (re.compile(r"^\.([a-z][A-Za-z0-9]*)$"), lambda m: f"dot {m.group(1)}"),              # .count -> dot count
]

TRAIL = re.compile(r"^(.*?)([,.;:!?]*)$")


SYMBOLS = re.compile(r"^[?=!<>&|+\-*/%]+$")
CODE = re.compile(r"^`([^`]+)`([,.;:!?]*)$")


def speak(token):
    """-> (caption text, spoken text)"""
    m = CODE.match(token)
    if m:
        code, punct = m.groups()
        if code in SAY:
            return code + punct, SAY[code] + punct
        for pat, fn in RULES:
            r = pat.match(code)
            if r:
                return code + punct, fn(r) + punct
        return code + punct, code + punct
    if SYMBOLS.match(token) and token in SAY:
        return token, SAY[token]
    core, punct = TRAIL.match(token).groups()
    if core in SAY and core not in ("!",):
        return token, SAY[core] + punct
    return token, token


def tokens_for(sentence):
    out = []
    for t in sentence.split():
        text, spoken = speak(t)
        out.append({"text": text, "spoken": spoken})
    return out


if __name__ == "__main__":
    for s in ["Use `Int?` and ?? to stay safe.", "Never write `value!` in production, it crashes!",
              "Call `print()` on it.", "Check `.count` first.", "Is it an Int?"]:
        print([(t["text"], t["spoken"]) for t in tokens_for(s)])
