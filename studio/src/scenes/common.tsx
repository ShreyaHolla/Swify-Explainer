import React from "react";
import { interpolate, Easing } from "remotion";
import type { Palette } from "../types";

export const SANS = "'Inter', sans-serif";
export const MONO = "'JetBrains Mono', monospace";
const ease = Easing.bezier(0.22, 1, 0.36, 1);

/** 0 -> 1 over `dur` frames starting at `at` (ease-out). The whole kit animates with this one curve. */
export const appear = (frame: number, at: number, dur = 10) =>
  interpolate(frame, [at, at + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });

/** small rise + fade: the only entrance used for text blocks (movement <= 24 px) */
export const rise = (p: number, px = 16): React.CSSProperties => ({ opacity: p, transform: `translateY(${(1 - p) * px}px)` });

/** whole-scene envelope: in over 10 frames, out over the last 8 */
export const sceneFade = (frame: number, duration: number) =>
  Math.min(appear(frame, 0, 10), interpolate(frame, [duration - 8, duration], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));

export const Eyebrow: React.FC<{ text?: string; pal: Palette; size: number; p: number }> = ({ text, pal, size, p }) =>
  text ? (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.5, ...rise(p, 10) }}>
      <div style={{ width: size * 1.4, height: 4, borderRadius: 2, background: pal.accent }} />
      <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: size, letterSpacing: size * 0.12, textTransform: "uppercase", color: pal.muted }}>
        {text}
      </div>
    </div>
  ) : null;
