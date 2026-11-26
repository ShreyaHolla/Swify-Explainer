"""Narration with word timings: AI voice (Edge TTS online, Kokoro offline) or the user's own recording.

Every engine writes the same files into <lesson>/build/:
  voice.wav   the whole narration, 48 kHz mono
  words.json  [{"text", "start", "end", "scene", "kind"}]  kind = "narration" | "mascot"
  segments.json  per scene: {"scene", "start", "end"} and each mascot line: {"scene", "line", "start", "end"}

Order inside a scene: the mascot's line (if any, "at": "start") is spoken first, then the narration.
Words keep their DISPLAY text (e.g. "Int?") while the voice hears the spoken form ("optional Int"); see speech_prep_code.

Engines
  edge    Edge TTS (free, online). Word timings come from the engine's word-boundary events.
  kokoro  Kokoro (free, offline, Apache-2.0). Synthesised per sentence; word times are spread over each
          sentence's voiced span in proportion to each word's phoneme count (good to about +-80 ms).
  mine    Your own recording(s): <lesson>/voice/scene_<n>.wav (one file per scene, easiest for retakes) or one
          voice.wav plus a transcript. Word times come from a local speech recogniser (faster-whisper) aligned
          to the script; sentences that differ from the script are reported so you re-record only that scene.
"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from speech_prep_code import tokens_for  # noqa: E402

SR = 48000
PAUSE_SENTENCE = 0.28   # seconds between sentences
PAUSE_SCENE = 0.55      # seconds of air at the end of each scene
PAUSE_AFTER_LINE = 0.35  # after the mascot's line, before the narration


# ---------------------------------------------------------------- audio helpers
def decode(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def trim(x, thr=0.012, keep=0.03):
    """Cut leading and trailing silence, keeping a few ms; returns (audio, samples cut at the start)."""
    on = np.where(np.abs(x) > thr)[0]
    if len(on) == 0:
        return x, 0
    a = max(0, on[0] - int(keep * SR))
    b = min(len(x), on[-1] + int(keep * 2 * SR))
    return x[a:b], a


def pitch_up(x, semis):
    """Raise pitch (and pace slightly) for the mascot's voice by resampling."""
    if not semis:
        return x
    k = 2 ** (semis / 12)
    n = int(len(x) / k)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


# ---------------------------------------------------------------- engines: one sentence -> (audio, word times)
class Kokoro:
    def __init__(self, model_dir):
        from kokoro_onnx import Kokoro as K
        self.k = K(str(Path(model_dir) / "kokoro.onnx"), str(Path(model_dir) / "voices.bin"))

    def say(self, tokens, voice, speed):
        spoken = " ".join(t["spoken"] for t in tokens)
        a, sr = self.k.create(spoken, voice=voice, speed=speed, lang="en-us")
        x = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR / sr)), np.arange(len(a)), a).astype(np.float32)
        x, _ = trim(x)
        # spread the voiced span over the words by phoneme count (+1 so short words still get a beat)
        weights = [max(1, len(self.k.tokenizer.phonemize(t["spoken"], "en-us").replace(" ", ""))) + 1 for t in tokens]
        total, dur = sum(weights), len(x) / SR
        t, times = 0.02, []
        for w in weights:
            d = (dur - 0.05) * w / total
            times.append((t, t + d * 0.92))
            t += d
        return x, times


class Edge:
    async def _run(self, text, voice, rate, pitch, mp3):
        import edge_tts
        com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
        ev = []
        with open(mp3, "wb") as f:
            async for e in com.stream():
                if e["type"] == "audio":
                    f.write(e["data"])
                elif e["type"] == "WordBoundary":
                    s = e["offset"] / 1e7
                    ev.append((s, s + e["duration"] / 1e7))
        return ev

    def say(self, tokens, voice, speed, pitch="+0Hz"):
        import tempfile
        spoken_words = []
        owner = []
        for i, t in enumerate(tokens):
            for w in t["spoken"].split():
                spoken_words.append(w)
                owner.append(i)
        rate = f"{int(round((speed - 1) * 100)):+d}%"
        with tempfile.TemporaryDirectory() as td:
            mp3 = Path(td) / "s.mp3"
            ev = asyncio.run(self._run(" ".join(spoken_words), voice, rate, pitch, mp3))
            x = decode(mp3)
        x, cut = trim(x)
        off = cut / SR
        times = [None] * len(tokens)
        for (s, e), i in zip(ev, owner):  # a display token spans all of its spoken words
            s, e = s - off, e - off
            times[i] = (s, e) if times[i] is None else (times[i][0], e)
        for i in range(len(times)):  # boundary events can skip punctuation-only tokens
            if times[i] is None:
                times[i] = times[i - 1] if i else (0.0, 0.1)
        return x, times


# ---------------------------------------------------------------- build
def build(lesson_dir: Path, engine: str, channel: dict, model_dir: Path):
    lesson = json.loads((lesson_dir / "lesson.json").read_text(encoding="utf-8"))
    out = lesson_dir / "build"
    out.mkdir(exist_ok=True)
    if engine == "mine":
        raise SystemExit("--voice mine: put your recordings in <lesson>/voice/ (see align_voice.py); not run here.")
    v = channel["voices"][engine]
    eng = Kokoro(model_dir) if engine == "kokoro" else Edge()

    chunks, words, segments, t = [], [], [], 0.0

    def speak(text, scene_i, kind, voice, speed, semis=0):
        nonlocal t
        for sent in split_sentences(text):
            toks = tokens_for(sent)
            x, times = eng.say(toks, voice, speed)
            if semis:
                k = 2 ** (semis / 12)
                x = pitch_up(x, semis)
                times = [(a / k, b / k) for a, b in times]
            for tok, (a, b) in zip(toks, times):
                words.append({"text": tok["text"], "start": round(t + a, 3), "end": round(t + b, 3), "scene": scene_i, "kind": kind})
            chunks.append(x)
            t += len(x) / SR
            chunks.append(np.zeros(int(PAUSE_SENTENCE * SR), np.float32))
            t += PAUSE_SENTENCE

    scenes = [s for ch in lesson["chapters"] for s in ch["scenes"]]
    for i, sc in enumerate(scenes):
        start = t
        for m in sc.get("mascot", []):
            if "line" in m and m.get("at", "start") == "start" and m.get("voiced", True):
                a = t
                mv = channel["voices"]["mascot"][engine]
                speak(m["line"], i, "mascot", mv["voice"], mv.get("speed", 1.0), mv.get("pitch_semitones", 0))
                segments.append({"scene": i, "line": m["line"], "start": round(a, 3), "end": round(t - PAUSE_SENTENCE, 3)})
                chunks.append(np.zeros(int(PAUSE_AFTER_LINE * SR), np.float32))
                t += PAUSE_AFTER_LINE
        if sc.get("say"):
            speak(sc["say"], i, "narration", v["voice"], v.get("speed", 1.0))
        hold = sc.get("hold", 0)  # extra seconds on screen (e.g. reading time for code output)
        if hold:
            chunks.append(np.zeros(int(hold * SR), np.float32))
            t += hold
        chunks.append(np.zeros(int(PAUSE_SCENE * SR), np.float32))
        t += PAUSE_SCENE
        segments.append({"scene": i, "start": round(start, 3), "end": round(t, 3)})
        print(f"  scene {i + 1:2d} {sc['type']:8s} {t - start:5.1f}s")

    y = np.concatenate(chunks)
    y = y / max(1e-6, np.abs(y).max()) * 0.89
    from scipy.io import wavfile
    wavfile.write(out / "voice.wav", SR, (y * 32767).astype(np.int16))
    (out / "words.json").write_text(json.dumps(words, indent=1), encoding="utf-8")
    (out / "segments.json").write_text(json.dumps(segments, indent=1), encoding="utf-8")
    print(f"voice: {engine}, {t:.1f}s, {len(words)} words -> {out}")
