# Explainer engine

Content-first animated explainer videos with a small mascot (e.g. Swify, who explains Swift).
One lesson becomes a long YouTube video (16:9) and Shorts (9:16). Forked from `animated-history-shorts`:
the LLM client (`llm/`), sound bed (`pipeline/sound.py`) and pronunciation helpers come from there; the 3D sets
and character cards are replaced by a 2D scene kit and a mascot layer.

```
lesson.json -> code check -> narration + word timings -> timeline (cue words -> frames) -> Remotion render -> loudness + exports
```

## Setup
Python 3.11+, Node 20+, FFmpeg, Chrome or Chromium. For Swift lessons, install the Swift toolchain (`swiftc`) so every sample is compiled and its real output shown.

```bash
pip install edge-tts kokoro-onnx soundfile numpy scipy pillow
cd studio && npm install && cd ..
# optional offline voice: put kokoro.onnx + voices.bin (github.com/thewh1teagle/kokoro-onnx releases) in models/
```

## Make a video
```bash
python pipeline/import_mascot.py channels/swify        # once per mascot: cut-out, parts, preview.jpg
python make.py lessons/swift-optionals --voice edge     # or --voice kokoro (offline)
python make.py lessons/swift-optionals --still 60,400   # quick PNG check of chosen frames
cd studio && npm run studio                             # live preview of the last long video
```
Outputs land in `lessons/<slug>/out/`: `_youtube.mp4`, `_short1.mp4`, `_youtube.srt`, `_metadata.txt` (chapters).

## Writing a lesson
See `lessons/swift-optionals/lesson.json`. Scenes: `title`, `concept`, `code`, `compare`, `list`, `outro`.
Every reveal names a **cue word** from that scene's `say` text and appears exactly when it is spoken.
Mascot: `{"beat": "wave|point|nod|hop|celebrate|think|flap", "cue": "word"}` and at most one short `{"line": "..."}` per scene.
Write code in narration between backticks (`` `Int?` ``) so it is spoken correctly ("optional Int").

## Adding a mascot
Put one image in `channels/<name>/source/`, describe it in `mascot.json` (copy Swify's), run `import_mascot.py`.
With a `parts` block the wings (or arms) are cut out and animated; without it the mascot runs in card mode.

## Status
Done: scene kit, 16:9 and 9:16 layouts, Swify import with wing parts, blink, idle and reactions, speech bubbles,
AI voice (Edge, Kokoro) with word timing, cue-word timeline, code check, captions, chapters, .srt, loudness.
Next: own-voice recording path, LLM lesson writer + director, Shorts rewrite mode, diagram scene, thumbnails.
