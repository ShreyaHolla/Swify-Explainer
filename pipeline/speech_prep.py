"""Prepare script text for the voice, and map the voice's word timings back to the ORIGINAL words.

Why: a multilingual voice (e.g. en-AU-WilliamMultilingualNeural) reads Indian names well when they are written in
Devanagari, but then it switches to Hindi for bare digits too ("1857" came out in Hindi). So:
  - every number, year, date, percent and amount is spelled out in ENGLISH words before it goes to the voice
    ("1858" -> "eighteen fifty-eight", "22 May" -> "the twenty-second of May");
  - optionally, names found in pronunciations.json are written in Devanagari (only for voices that can read it);
  - captions still show the original text: align() merges the voice's word events back onto the original tokens.

prepare(text, names=None, hindi_names=False) -> [{"orig": "1858,", "spoken": "eighteen fifty-eight,"}, ...]
align(tokens, events) -> [{"text": orig, "start": s, "end": e}, ...]   (events: [{"text","start","end"}] from the voice)
"""
import re
import unicodedata

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
BIG_WORDS = {"hundred", "thousand", "million", "billion", "lakh", "lakhs", "crore", "crores"}
ORD_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
                 "twelve": "twelfth"}


def words(n):
    """Cardinal number in English words (0 .. 999,999,999,999)."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + words(n % 100) if n % 100 else "")
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand")):
        if n >= size:
            return words(n // size) + " " + name + (" " + words(n % size) if n % size else "")
    raise ValueError(n)


def ordinal(n):
    """22 -> twenty-second, 11 -> eleventh, 30 -> thirtieth, 105 -> one hundred fifth."""
    w = words(n)
    idx = max(w.rfind(" "), w.rfind("-"))
    head, last = (w[:idx + 1], w[idx + 1:]) if idx >= 0 else ("", w)
    last = ORD_IRREGULAR.get(last, (last[:-1] + "ieth") if last.endswith("y") else last + "th")
    return head + last


def year_words(n):
    if n == 2000:
        return "two thousand"
    if 2000 < n < 2010:
        return "two thousand " + words(n - 2000)
    hi, lo = divmod(n, 100)
    if lo == 0:
        return words(hi) + " hundred"
    if lo < 10:
        return words(hi) + " oh " + words(lo)
    return words(hi) + " " + words(lo)


def is_year(s):
    return bool(re.fullmatch(r"\d{4}", s)) and 1100 <= int(s) <= 2099


def num(s):
    return int(s.replace(",", ""))


def split_punct(tok):
    m = re.fullmatch(r"([\"'(\[]*)(.*?)([\"')\].,;:!?]*)", tok)
    return m.group(1), m.group(2), m.group(3)


def spell_core(core, prev, nxt):
    """English spoken form of one token core, or None if it is not a number-like token. prev/nxt are neighbours (lowercase)."""
    m = re.fullmatch(r"(\d[\d,]*)(\.\d+)?%", core)
    if m:
        return spell_core(m.group(1) + (m.group(2) or ""), prev, nxt) + " percent"
    m = re.fullmatch(r"(\d{4})s", core)
    if m and is_year(m.group(1)):                               # 1960s -> nineteen sixties, 1900s -> nineteen hundreds
        y = int(m.group(1))
        if y % 100 == 0:
            return words(y // 100) + " hundreds"
        base = year_words(y)
        return base[:-1] + "ies" if base.endswith("y") else base + "s"
    m = re.fullmatch(r"(\d{1,3})(st|nd|rd|th)", core)
    if m:
        return ordinal(int(m.group(1)))
    m = re.fullmatch(r"(\d{4})[-–](\d{2,4})", core)       # 1827-30 , 1827-1830
    if m and is_year(m.group(1)):
        a, b = m.group(1), m.group(2)
        b_full = b if len(b) == 4 else a[:2] + b
        return year_words(int(a)) + " to " + (year_words(int(b_full)) if is_year(b_full) else words(int(b)))
    m = re.fullmatch(r"(\d[\d,]*)[-–](\d[\d,]*)", core)   # 8-1 (a score), 5-10
    if m:
        return words(num(m.group(1))) + " to " + words(num(m.group(2)))
    m = re.fullmatch(r"([₹$])(\d[\d,]*)(\.\d+)?", core)    # rupee / dollar sign glued to the number
    if m:
        unit = "rupees" if m.group(1) == "₹" else "dollars"
        body = spell_core(m.group(2) + (m.group(3) or ""), prev, nxt)
        return body + ("" if nxt in BIG_WORDS else " " + unit)
    m = re.fullmatch(r"(\d[\d,]*)(\.\d+)?", core)
    if m:
        if m.group(2):
            return words(num(m.group(1))) + " point " + " ".join(words(int(d)) for d in m.group(2)[1:])
        n = num(m.group(1))
        if "," not in core and is_year(core):
            return year_words(n)
        if "," not in core and 1 <= n <= 31 and nxt in MONTHS:
            return "the " + ordinal(n) + " of"
        if "," not in core and 1 <= n <= 31 and prev in MONTHS:
            return ordinal(n)
        return words(n)
    return None


def prepare(text, names=None, hindi_names=False):
    toks = text.split()
    parts = [split_punct(t) for t in toks]
    lowers = [p[1].lower() for p in parts]
    out, pending = [], ""
    for i, (lead, core, trail) in enumerate(parts):
        prev = lowers[i - 1] if i else ""
        nxt = lowers[i + 1] if i + 1 < len(parts) else ""
        if core.lower() in ("rs", "rs.") and re.match(r"\d", nxt or "x"):
            spoken = "rupees"
        else:
            spoken = spell_core(core, prev, nxt)
            if spoken is None:
                spoken = core
                if hindi_names and names:
                    poss = core.endswith(("'s", "’s"))
                    base = core[:-2] if poss else core
                    dev = names.get(base.lower())
                    if dev:
                        # possessive: "मेहता's" makes the voice stop and read a separate "s" after a 0.6 s gap (heard in Harshad
                        # Mehta ep2), so the "s" is fused into the Devanagari word as ज़ ("z"), one word, no gap
                        spoken = dev + ("ज़" if poss else "")
        if pending:                       # "$6 million" -> "six" + "million dollars"
            spoken, pending = spoken + " " + pending, ""
        if re.fullmatch(r"[$₹]\d[\d,.]*", core) and nxt in BIG_WORDS:
            pending = "rupees" if core[0] == "₹" else "dollars"
        out.append({"orig": toks[i], "spoken": lead + spoken + trail})
    return out


def _norm(s):
    """Letters, marks and digits only (so punctuation, spaces and hyphens do not matter), lowercased."""
    return "".join(ch for ch in s.lower() if unicodedata.category(ch)[0] in "LMN")


def align(tokens, events):
    """Merge the voice's word events back onto the original tokens by position in the spoken character stream."""
    lens = [len(_norm(t["spoken"])) for t in tokens]
    ev = [(len(_norm(e["text"])), e) for e in events]
    ev_total, tok_total = sum(n for n, _ in ev), sum(lens)
    if not events or abs(ev_total - tok_total) > max(8, 0.04 * tok_total):
        raise ValueError(f"voice words do not match the text sent ({ev_total} vs {tok_total} characters); "
                         f"the voice re-read or skipped something")
    # cumulative character range of every event
    ranges, c = [], 0
    for n, e in ev:
        ranges.append((c, c + n, e))
        c += n
    out, pos = [], 0
    scale = ev_total / tok_total if tok_total else 1.0
    for t, n in zip(tokens, lens):
        a, b = pos * scale, (pos + n) * scale
        pos += n
        hit = [e for (lo, hi, e) in ranges if hi > a + 1e-6 and lo < b - 1e-6] if n else []
        if not hit:                        # a token with no letters (a lone dash): borrow the nearest event time
            nearest = min(ranges, key=lambda r: abs(r[0] - a))[2]
            hit = [nearest]
        out.append({"text": t["orig"], "start": hit[0]["start"], "end": hit[-1]["end"]})
    return out
