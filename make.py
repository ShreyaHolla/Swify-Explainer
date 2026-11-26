"""One command from lesson to finished videos.

  python make.py lessons/swift-optionals --voice edge            # AI voice, online (default on your machine)
  python make.py lessons/swift-optionals --voice kokoro          # AI voice, offline
  python make.py lessons/swift-optionals --voice mine            # your recordings in <lesson>/voice/ (next milestone)
  options: --only landscape|shorts   --still 120,600   --allow-unverified   --no-render

Steps: code check -> narration + word timings -> timeline (props per video) -> Remotion render -> loudness + exports.
Outputs in <lesson>/out/: <slug>_youtube.mp4, <slug>_short1.mp4 ..., <slug>_youtube.srt, <slug>_metadata.txt
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "pipeline"))
import code_check  # noqa: E402
import timeline  # noqa: E402
import voice  # noqa: E402

STUDIO = ROOT / "studio"


def ts(sec, srt=False):
    h, m, s = int(sec // 3600), int(sec % 3600 // 60), sec % 60
    if srt:
        return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
    return f"{h}:{m:02d}:{int(s):02d}" if h else f"{m}:{int(s):02d}"


def render(props_file: Path, public: Path, out: Path, still_frames=None):
    cmd = ["npx", "remotion"]
    base = ["src/index.ts", "Lesson"]
    opts = [f"--props={props_file}", f"--public-dir={public}", "--log=error"]
    chrome = os.environ.get("REMOTION_CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
    if chrome:
        opts.append(f"--browser-executable={chrome}")
    if still_frames:
        for fr in still_frames:
            png = out.with_name(f"{out.stem}_f{fr}.png")
            subprocess.run(cmd + ["still"] + base + [str(png), f"--frame={fr}"] + opts, cwd=STUDIO, check=True)
        return
    subprocess.run(cmd + ["render"] + base + [str(out), "--codec=h264", "--crf=18", "--concurrency=2"] + opts, cwd=STUDIO, check=True)


def finish(raw: Path, final: Path):
    """Loudness to -14 LUFS (YouTube's reference), keep video untouched."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)], check=True)
    raw.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lesson")
    ap.add_argument("--voice", default="edge", choices=["edge", "kokoro", "mine"])
    ap.add_argument("--only", choices=["landscape", "shorts"])
    ap.add_argument("--still", help="comma-separated frames: render PNG stills instead of videos (quick look)")
    ap.add_argument("--allow-unverified", action="store_true", help="render even if code could not be compiled here")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--reuse-voice", action="store_true", help="keep build/voice.wav and words.json from the last run")
    ap.add_argument("--models", default=os.environ.get("KOKORO_DIR", str(ROOT / "models")))
    a = ap.parse_args()

    ld = Path(a.lesson).resolve()
    lesson = json.loads((ld / "lesson.json").read_text(encoding="utf-8"))
    cd = ROOT / "channels" / lesson["channel"]
    channel = json.loads((cd / "channel.json").read_text(encoding="utf-8"))
    slug = ld.name
    build, out = ld / "build", ld / "out"
    build.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)

    print("1/4 code check")
    code = code_check.run(ld, channel["code"]["lang"])
    unverified = [k for k, v in code.items() if not v["verified"]]
    if unverified and not a.allow_unverified:
        raise SystemExit(f"Unverified code ({', '.join(unverified)}): install {channel['code']['runner']} or pass --allow-unverified")

    print(f"2/4 narration ({a.voice})")
    if not (a.reuse_voice and (build / "words.json").exists()):
        voice.build(ld, a.voice, channel, Path(a.models))

    print("3/4 timeline")
    public = build / "public"
    if public.exists():
        shutil.rmtree(public)
    public.mkdir()
    shutil.copy(build / "voice.wav", public / "voice.wav")
    shutil.copytree(cd / "mascot", public / "mascot", ignore=shutil.ignore_patterns("preview.jpg"))
    videos = []
    if a.only != "shorts":
        videos.append(("youtube", {"format": "landscape"}))
    if a.only != "landscape":
        for k, sh in enumerate(lesson.get("shorts", []), 1):
            if sh.get("mode", "cut") != "cut":
                print(f"  short {k}: rewrite mode is not built yet, skipped")
                continue
            videos.append((f"short{k}", {"format": "portrait", "chapters": [sh["chapter"]], "hook": sh.get("hook")}))
    for name, v in videos:
        props = timeline.build_props(ld, cd, v)
        pf = build / f"props_{name}.json"
        pf.write_text(json.dumps(props), encoding="utf-8")
        print(f"  {name}: {props['width']}x{props['height']}, {props['durationInFrames'] / props['fps']:.1f}s, {len(props['scenes'])} scenes")
        if name == "youtube":
            (STUDIO / "src" / "sample.json").write_text(json.dumps(props), encoding="utf-8")
            words = json.loads((build / "words.json").read_text(encoding="utf-8"))
            srt, n, cur = [], 0, []
            for w in [w for w in words if w["kind"] == "narration"]:
                cur.append(w)
                if len(cur) == 7 or w["text"][-1:] in ".!?":
                    n += 1
                    srt.append(f"{n}\n{ts(cur[0]['start'], True)} --> {ts(cur[-1]['end'] + 0.2, True)}\n{' '.join(x['text'] for x in cur)}\n")
                    cur = []
            (out / f"{slug}_youtube.srt").write_text("\n".join(srt), encoding="utf-8")
            chap = "\n".join(f"{ts(c['from'] / props['fps'])} {c['title']}" for c in props["chapters"])
            (out / f"{slug}_metadata.txt").write_text(
                f"Title: {lesson['title']}\n\nChapters:\n{chap}\n\nCode verified: {'yes' if not unverified else 'NO: ' + ', '.join(unverified)}\n",
                encoding="utf-8")

    if a.no_render:
        return
    print("4/4 render")
    for name, _ in videos:
        pf = build / f"props_{name}.json"
        if a.still:
            render(pf, public, out / f"{slug}_{name}.png", [int(x) for x in a.still.split(",")])
            continue
        raw = out / f"{slug}_{name}_raw.mp4"
        render(pf, public, raw)
        finish(raw, out / f"{slug}_{name}.mp4")
        print(f"  -> {out / f'{slug}_{name}.mp4'}")
    if unverified:
        print(f"WARNING: code not compiled here ({', '.join(unverified)}); review before publishing.")


if __name__ == "__main__":
    main()
