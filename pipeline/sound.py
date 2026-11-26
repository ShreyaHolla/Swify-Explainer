"""Generate a simple original soundtrack for a story: a dark ambient bed + soft pulse, a whoosh on every cut and a hit on
every info card. Synthesised with numpy/scipy (no downloads, no licences). The bed is ducked under the narration.

Usage: python sound.py <story_dir>       (needs props.json from build_props.py)
Writes <story_dir>/bed.wav (48 kHz stereo, length = voice + tail). Then: assemble.py <dir> <picture.mp4> --bed <dir>/bed.wav
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
FPS = 30


def lowpass(x, hz, order=2):
    sos = signal.butter(order, hz, "lowpass", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def highpass(x, hz, order=2):
    sos = signal.butter(order, hz, "highpass", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def put(buf, x, t):
    """add x into buf starting at t seconds (clipped to the buffer)"""
    i = int(t * SR)
    if i >= len(buf) or i < 0:
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]


def whoosh(rng, dur=0.45):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    # band sweeping up then down: filter in blocks with a moving cutoff
    out = np.zeros(n)
    blk = 512
    for a in range(0, n, blk):
        fc = 300 + 3200 * np.sin(np.pi * min(1, a / n)) ** 1.5
        out[a:a + blk] = lowpass(noise[a:a + blk], min(fc, SR / 2 - 100), 1)
    env = np.sin(np.pi * t) ** 2
    return out * env * 0.5


def hit(kind, rng):
    if kind == "stamp":        # short click + low thump
        n = int(0.35 * SR); t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * (110 * np.exp(-t * 9) + 40) * t) * np.exp(-t * 11)
        click = highpass(rng.standard_normal(n), 2500) * np.exp(-t * 90) * 0.35
        return thump * 0.8 + click
    if kind == "headline":     # paper slap: filtered noise burst
        n = int(0.28 * SR); t = np.arange(n) / SR
        return highpass(lowpass(rng.standard_normal(n), 5000), 700) * np.exp(-t * 16) * 0.7
    n = int(0.7 * SR); t = np.arange(n) / SR   # number / stat: deep impact with a short rising tick
    boom = np.sin(2 * np.pi * (70 * np.exp(-t * 4) + 32) * t) * np.exp(-t * 4.5)
    tick = np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 40) * 0.12
    return boom * 0.9 + tick


def ambient(total, rng, pulse_on=True):
    n = int(total * SR); t = np.arange(n) / SR
    root = 55.0                                  # A1, a dark held chord: root, fifth, minor third above
    pad = np.zeros(n)
    for f, g in ((root, 1.0), (root * 1.5, 0.6), (root * 2.378, 0.35), (root * 3.0, 0.25)):
        for det in (-0.35, 0.0, 0.35):
            pad += g * np.sin(2 * np.pi * (f + det) * t + rng.uniform(0, 6.28))
    pad *= 0.5 + 0.5 * (0.6 + 0.4 * np.sin(2 * np.pi * t / 11.0))          # slow breathing
    air = lowpass(rng.standard_normal(n), 900) * (0.25 + 0.15 * np.sin(2 * np.pi * t / 7.0))
    # soft pulse: one low thump per second, stronger every fourth beat
    pulse = np.zeros(n)
    tt = np.arange(int(0.4 * SR)) / SR
    beat = np.sin(2 * np.pi * (70 * np.exp(-tt * 8) + 38) * tt) * np.exp(-tt * 9)
    for k in range(int(total) if pulse_on else 0):      # --no-pulse: music.py supplies the rhythm, a thump would fight it
        put(pulse, beat * (0.8 if k % 4 == 0 else 0.45), k + 0.0)
    return pad * 0.05 + air * 0.05 + pulse * 0.55


def duck_curve(words, total, depth_db=-4.0):
    n = int(total * SR)
    g = np.ones(n)
    for w in words:
        a, b = int(max(0, w["start"] - 0.08) * SR), int(min(total, w["end"] + 0.12) * SR)
        g[a:b] = 10 ** (depth_db / 20)
    win = int(0.25 * SR)
    return np.convolve(g, np.ones(win) / win, mode="same")


def main(story_dir, pulse_on=True):
    d = Path(story_dir)
    props = json.loads((d / "props.json").read_text(encoding="utf-8"))
    words, story, vdur = props["words"], props["story"], props["voiceDur"]
    total = vdur + story["tail"]
    rng = np.random.default_rng(11)
    mono = ambient(total, rng, pulse_on) * duck_curve(words, total)
    fx = np.zeros(int(total * SR))
    shots = story["shots"]
    starts = [0.0] + [words[min(s["from"], len(words) - 1)]["start"] for s in shots[1:]]
    for i, s in enumerate(shots):
        if i > 0:
            put(fx, whoosh(rng) * 0.9, max(0.0, starts[i] - 0.30))
        for c in s.get("cards") or []:
            put(fx, hit(c["type"], rng) * 0.8, starts[i] + c.get("at", 0.2))
    mix = mono + fx
    fade = int(0.8 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    # tiny stereo decorrelation so it is not dead centre
    left = mix + 0.15 * np.roll(mix, 37)
    right = mix + 0.15 * np.roll(mix, -41)
    st = np.stack([left, right], axis=1)
    rms = np.sqrt(np.mean(st ** 2))
    st *= (10 ** (-20 / 20)) / max(rms, 1e-9)          # bed at about -20 dBFS RMS; assemble.py mixes it much lower
    peak = np.abs(st).max()
    if peak > 0.9:
        st *= 0.9 / peak
    wavfile.write(d / "bed.wav", SR, (st * 32767).astype(np.int16))
    print(f"bed.wav: {total:.2f} s, {len(shots)} shots, {sum(len(s.get('cards') or []) for s in shots)} card hits")


if __name__ == "__main__":
    main(sys.argv[1], pulse_on="--no-pulse" not in sys.argv)
