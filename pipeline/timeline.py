"""lesson.json + build/words.json + segments.json + code.json -> Remotion props for one video.

Every reveal is resolved from a CUE WORD to a frame, so the picture lands exactly when the word is spoken.
Cue search runs forward through the scene's narration, so repeated words resolve in order.

props(video) where video = {"format": "landscape"|"portrait", "chapters": [indices] or None (all), "hook": str}
"""
import json
import re
from pathlib import Path

FPS = 30
SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
norm = lambda w: re.sub(r"[^a-z0-9?]+", "", w.lower())


class CueError(SystemExit):
    pass


def _cue_finder(words):
    pos = [0]

    def find(cue, scene_title):
        c = norm(cue)
        for i in range(pos[0], len(words)):
            if norm(words[i]["text"]).startswith(c):
                pos[0] = i + 1
                return words[i]["start"]
        for i in range(0, len(words)):  # out of order: allow, but still must exist
            if norm(words[i]["text"]).startswith(c):
                return words[i]["start"]
        raise CueError(f"cue word '{cue}' is not spoken in scene '{scene_title}'")
    return find


def caption_chunks(words, max_words=4, max_chars=26):
    chunks, cur = [], []
    for w in words:
        trial = cur + [w]
        if cur and (len(trial) > max_words or len(" ".join(x["text"] for x in trial)) > max_chars
                    or cur[-1]["text"][-1:] in ".!?"):
            chunks.append(cur)
            cur = [w]
        else:
            cur = trial
    if cur:
        chunks.append(cur)
    return chunks


def build_props(lesson_dir: Path, channel_dir: Path, video: dict):
    lesson = json.loads((lesson_dir / "lesson.json").read_text(encoding="utf-8"))
    channel = json.loads((channel_dir / "channel.json").read_text(encoding="utf-8"))
    rig = json.loads((channel_dir / "mascot" / "rig.json").read_text(encoding="utf-8"))
    b = lesson_dir / "build"
    words = json.loads((b / "words.json").read_text(encoding="utf-8"))
    segs = json.loads((b / "segments.json").read_text(encoding="utf-8"))
    code = json.loads((b / "code.json").read_text(encoding="utf-8")) if (b / "code.json").exists() else {}

    flat = []  # (chapter index, chapter title, scene)
    for ci, ch in enumerate(lesson["chapters"]):
        for sc in ch["scenes"]:
            flat.append((ci, ch["title"], sc))
    scene_seg = {s["scene"]: s for s in segs if "line" not in s}
    line_segs = [s for s in segs if "line" in s]

    want = set(video.get("chapters") or range(len(lesson["chapters"])))
    idx = [i for i, (ci, _, _) in enumerate(flat) if ci in want]
    t0, t1 = scene_seg[idx[0]]["start"], scene_seg[idx[-1]]["end"]
    f = lambda t: int(round((t - t0) * FPS))

    scenes, chapters = [], []
    for i in idx:
        ci, ctitle, sc = flat[i]
        seg = scene_seg[i]
        sw = [w for w in words if w["scene"] == i and w["kind"] == "narration"]
        find = _cue_finder(sw)
        title = sc.get("title") or sc.get("eyebrow") or sc["type"]
        start = f(seg["start"])
        rel = lambda t: max(0, f(t) - start)
        d = {k: v for k, v in sc.items() if k not in ("say", "mascot", "cues", "reveal", "output", "hold")}
        d.update(type=sc["type"], chapter=ctitle, chapterIndex=ci, **{"from": start}, duration=f(seg["end"]) - start)
        cues = {}
        if sc["type"] == "concept":
            for k, w in sc.get("cues", {}).items():
                cues[k] = rel(find(w, title))
        elif sc["type"] == "compare":
            for k, w in sc.get("cues", {}).items():
                cues[k] = rel(find(w, title))
        elif sc["type"] == "list":
            cues["items"] = [rel(find(w, title)) for w in sc["cues"]]
        elif sc["type"] == "code":
            c = code[sc["file"]]
            d["lines"] = c["source"].split("\n")
            d["output"] = c["output"]
            d["verified"] = c["verified"]
            d["steps"] = [{"lines": r["lines"], "at": rel(find(r["cue"], title))} for r in sc["reveal"]]
            if sc.get("output"):
                cues["output"] = rel(find(sc["output"]["cue"], title))
        d["cues"] = cues
        if not chapters or chapters[-1]["index"] != ci:
            chapters.append({"index": ci, "title": ctitle, "from": start})
        scenes.append(d)

    # mascot: beats on cue words, lines with talk intervals
    beats, lines = [], []
    for i in idx:
        _, _, sc = flat[i]
        sw = [w for w in words if w["scene"] == i and w["kind"] == "narration"]
        find = _cue_finder(sw)
        for m in sc.get("mascot", []):
            if "beat" in m:
                at = find(m["cue"], sc.get("title") or sc["type"]) if m.get("cue") else scene_seg[i]["start"] + 0.3
                beats.append({"name": m["beat"], "at": f(at)})
        for ls in [s for s in line_segs if s["scene"] == i]:
            mw = [w for w in words if w["scene"] == i and w["kind"] == "mascot"]
            lines.append({"text": ls["line"], "from": max(0, f(ls["start"]) - 4), "to": max(f(ls["end"]) + 36, f(ls["start"]) + 54),
                          "talk": [[f(w["start"]), f(w["end"])] for w in mw]})
    beats.sort(key=lambda x: x["at"])
    kept, last = [], -999
    for bt in beats:  # at most one reaction every 4 s, so the mascot never distracts from the content
        if bt["at"] - last >= 4 * FPS:
            kept.append(bt)
            last = bt["at"]

    fmt = video["format"]
    W, H = SIZES[fmt]
    caps = []
    if fmt == "portrait":
        nw = [w for w in words if w["kind"] == "narration" and w["scene"] in idx]
        ch = caption_chunks(nw)
        for k, g in enumerate(ch):
            end = ch[k + 1][0]["start"] if k + 1 < len(ch) and ch[k + 1][0]["start"] - g[-1]["end"] < 0.6 else g[-1]["end"] + 0.25
            caps.append({"from": f(g[0]["start"]), "to": f(end),
                         "words": [{"text": w["text"], "from": f(w["start"]), "to": f(w["end"])} for w in g]})

    return {
        "format": fmt, "width": W, "height": H, "fps": FPS,
        "durationInFrames": f(t1),
        "audio": video.get("audio", "voice.wav"), "audioStartFrame": int(round(t0 * FPS)),
        "title": lesson["title"], "hook": video.get("hook"),
        "palette": channel["palette"], "channel": channel["name"],
        "scenes": scenes, "chapters": chapters, "captions": caps,
        "mascot": {"rig": rig, "base": video.get("mascot_base", "mascot"), "beats": kept, "lines": lines},
    }
