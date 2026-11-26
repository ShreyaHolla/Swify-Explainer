"""Approved script -> lesson.json + code files. No AI here: the video says exactly what you approved.

Cues are word positions (an int = index into that scene's spoken words), computed from the script's own structure
(each code step, list item and compare side has its own sentence), so every reveal lands on the first word of the
sentence that explains it.
"""
import json
import re
from pathlib import Path

MAX_LINE = 40


def n_words(s):
    return len(s.split())


def check(script, fmt):
    """Deterministic checks shown in the review step. -> [{"where", "severity", "problem"}]"""
    out = []
    max_lines = 10 if fmt == "short" else 12
    chs = script.get("chapters") or []
    if not chs:
        return [{"where": "script", "severity": "error", "problem": "No chapters."}]
    for ci, ch in enumerate(chs, 1):
        total = 0
        for si, sc in enumerate(ch.get("scenes", []), 1):
            w = f"chapter {ci}, scene {si} ({sc.get('kind')})"
            err = lambda m, sev="error": out.append({"where": w, "severity": sev, "problem": m})
            k = sc.get("kind")
            says = [sc.get("say", "")] + [st.get("say", "") for st in sc.get("steps", [])] + [sc.get("output_say", ""),
                    sc.get("left_say", ""), sc.get("right_say", "")] + [it.get("say", "") for it in sc.get("items", []) if isinstance(it, dict)]
            for s in says:
                if s and s.strip()[-1:] not in ".!?":
                    err(f"Sentence should end with . ! or ?: \"{s[-40:]}\"", "warning")
                if s and re.search(r"`[^`]*\s[^`]*`", s):
                    err(f"Backticked code with spaces is read badly: \"{s[:60]}\"", "warning")
            total += sum(n_words(s) for s in says if s)
            if k not in ("intro", "idea", "code", "compare", "list", "outro"):
                err(f"Unknown scene kind '{k}'.")
            if k == "idea":
                if n_words(sc.get("on_screen", "")) > 8:
                    err("On-screen text is longer than 8 words.", "warning")
                hl = sc.get("highlight", "").lower()
                if hl and hl not in sc.get("on_screen", "").lower():
                    err(f"Highlight word '{hl}' is not in the on-screen text.", "warning")
            if k == "code":
                lines = sc.get("code", "").split("\n")
                if len(lines) > max_lines:
                    err(f"{len(lines)} lines of code; keep it to {max_lines} so it reads on a phone.")
                long = [i + 1 for i, l in enumerate(lines) if len(l) > MAX_LINE]
                if long:
                    err(f"Lines {long} are longer than {MAX_LINE} characters (too small on a phone).", "warning")
                for st in sc.get("steps", []):
                    bad = [n for n in st.get("lines", []) if not 1 <= n <= len(lines)]
                    if bad:
                        err(f"Step refers to lines {bad}, but the code has {len(lines)} lines.")
                if not sc.get("steps"):
                    err("Code scene has no steps.")
            if k == "list" and not 2 <= len(sc.get("items", [])) <= 4:
                err("Recap lists need 2 to 4 items.", "warning")
        if total > 230:
            out.append({"where": f"chapter {ci}", "severity": "warning", "problem": f"{total} spoken words: long for one chapter (aim 110-190)."})
    return out


def _start(parts, k):
    """word index where part k starts when parts are joined with spaces"""
    return sum(n_words(p) for p in parts[:k])


def convert(script, lesson_dir: Path, channel: dict, fmt: str, code_results: dict):
    """Write lesson.json and code/*.swift (+ .expected) into lesson_dir. code_results: {"c1s3": {"output", "verified"}}"""
    lines_cfg = channel.get("mascot_lines", {"intro": "Hello world!", "outro": "Your turn: try it!"})
    code_dir = lesson_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    chapters = []
    for ci, ch in enumerate(script["chapters"]):
        scenes = []
        for si, sc in enumerate(ch["scenes"]):
            k = sc["kind"]
            key = f"c{ci + 1}s{si + 1}"
            if k == "intro":
                scenes.append({"type": "title", "title": script["title"], "hook": script.get("hook", ""), "say": sc["say"],
                               "mascot": [{"line": lines_cfg["intro"], "at": "start"}, {"beat": "wave", "cue": 0}]})
            elif k == "idea":
                say = sc["say"]
                ws = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in say.split()]
                hl = re.sub(r"[^a-z0-9]", "", sc.get("highlight", "").lower())
                hi = next((i for i, w in enumerate(ws) if hl and w.startswith(hl[:5])), 0)
                sents = re.split(r"(?<=[.!?])\s+", say.strip())
                sub_at = n_words(sents[0]) if len(sents) > 1 else max(0, len(ws) - 3)
                cues = {"highlight": hi}
                if sc.get("sub"):
                    cues["sub"] = sub_at
                scenes.append({"type": "concept", "eyebrow": sc.get("label", ""), "text": sc["on_screen"],
                               "highlight": sc.get("highlight", ""), "sub": sc.get("sub", ""), "say": say, "cues": cues,
                               "mascot": [{"beat": "think", "cue": hi}] + ([{"beat": "nod", "cue": sub_at}] if sc.get("sub") else [])})
            elif k == "code":
                parts = [st["say"] for st in sc["steps"]] + [sc.get("output_say", "")]
                parts = [p for p in parts if p]
                fname = f"code/{key}.swift"
                (lesson_dir / fname).write_text(sc["code"].rstrip("\n") + "\n", encoding="utf-8")
                res = code_results.get(key) or {}
                out_text = res.get("output", sc.get("expected_output", ""))
                (lesson_dir / fname).with_suffix(".expected").write_text(out_text + "\n", encoding="utf-8")
                reveal = [{"lines": st["lines"], "cue": _start(parts, i)} for i, st in enumerate(sc["steps"])]
                d = {"type": "code", "eyebrow": sc.get("label", ""), "file": fname, "say": " ".join(parts), "reveal": reveal,
                     "hold": 1.2, "mascot": [{"beat": "point", "cue": 0}]}
                if sc.get("output_say"):
                    d["output"] = {"cue": _start(parts, len(sc["steps"]))}
                    d["mascot"].append({"beat": "celebrate", "cue": d["output"]["cue"]})
                scenes.append(d)
            elif k == "compare":
                parts = [sc.get("left_say", ""), sc.get("right_say", "")]
                scenes.append({"type": "compare", "eyebrow": sc.get("label", ""),
                               "left": {**sc["left"], "tone": sc["left"].get("tone", "good")},
                               "right": {**sc["right"], "tone": sc["right"].get("tone", "bad")},
                               "say": " ".join(p for p in parts if p), "cues": {"left": 0, "right": _start(parts, 1)},
                               "mascot": [{"beat": "think", "cue": _start(parts, 1)}]})
            elif k == "list":
                items = sc["items"]
                parts = [it["say"] for it in items]
                scenes.append({"type": "list", "eyebrow": sc.get("label", "Recap"), "items": [it["text"] for it in items],
                               "say": " ".join(parts), "cues": [_start(parts, i) for i in range(len(items))],
                               "mascot": [{"beat": "nod", "cue": 0}]})
            elif k == "outro":
                sents = re.split(r"(?<=[.!?])\s+", sc["say"].strip())
                scenes.append({"type": "outro", "title": f"Next: {sc.get('next', '')}".strip(), "say": sc["say"],
                               "mascot": [{"line": lines_cfg["outro"], "at": "start"},
                                          {"beat": "wave", "cue": _start(sents, len(sents) - 1)}]})
        chapters.append({"title": ch["title"], "standalone": True, "scenes": scenes})

    lesson = {"title": script["title"], "channel": channel["id"], "chapters": chapters,
              "landscape": fmt != "short",
              "shorts": [{"chapter": i, "mode": "cut", "hook": c["title"]} for i, c in enumerate(chapters)] if fmt != "short"
              else [{"chapter": 0, "mode": "cut", "hook": script.get("hook") or script["title"]}]}
    (lesson_dir / "lesson.json").write_text(json.dumps(lesson, indent=2), encoding="utf-8")
    return lesson
