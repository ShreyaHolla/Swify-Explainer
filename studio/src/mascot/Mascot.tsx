import React from "react";
import { Img, staticFile, interpolate, spring } from "remotion";
import type { LessonProps, Palette } from "../types";
import type { Layout } from "../layout";
import { SANS } from "../scenes/common";

// Small, calm motion only: idle (breathe, bob, blink, soft wing drift) is always on; reactions are short and
// spaced out (timeline.py keeps them >= 4 s apart). Wing angles: + = up. Upward travel is capped (UP_MAX)
// because a part cut from one flat image shows its seam if lifted too far.
const UP_MAX = 6, DOWN_MAX = 11;
const clampWing = (a: number) => Math.max(-DOWN_MAX, Math.min(UP_MAX, a));
const TAU = Math.PI * 2;
const DUR: Record<string, number> = { wave: 40, point: 34, nod: 26, hop: 22, celebrate: 44, think: 52, flap: 30 };

type Pose = { x: number; y: number; rot: number; sx: number; sy: number; wl: number; wr: number; think: number; sparkle: number };

function pose(f: number, fps: number, beats: { name: string; at: number }[], talking: boolean, lean: number, enterAt: number): Pose {
  const t = f / fps;
  const p: Pose = {
    x: 0,
    y: -7 * Math.sin(TAU * 0.45 * t),                    // hover bob
    rot: 0,
    sx: 1, sy: 1 + 0.012 * Math.sin(TAU * 0.4 * t),      // breathing
    wl: 2.5 * Math.sin(TAU * 0.9 * t), wr: 2.5 * Math.sin(TAU * 0.9 * t + 0.4),
    think: 0, sparkle: 0,
  };
  if (talking) { const k = Math.abs(Math.sin(f * 0.55)); p.sy += 0.03 * k; p.sx -= 0.012 * k; p.y -= 3 * k; }
  for (const b of beats) {
    const u = f - b.at, d = DUR[b.name] ?? 30;
    if (u < 0 || u > d) continue;
    const q = u / d, env = Math.sin(Math.PI * q);           // 0 -> 1 -> 0 over the beat
    switch (b.name) {
      case "wave": {                                        // the wing away from the content flaps 3 times
        const a = 9 * Math.sin(TAU * 3 * q) * env;
        if (lean < 0) p.wr += a; else p.wl += a;
        p.rot += -3 * lean * env; break;
      }
      case "point":                                         // lean toward the content, near wing raised
        p.rot += 6 * lean * env; p.x += 14 * lean * env;
        if (lean < 0) p.wl += 6 * env; else p.wr += 6 * env; break;
      case "nod": p.y += 9 * Math.abs(Math.sin(TAU * q)) * env; p.sy -= 0.02 * env; break;
      case "hop": {
        p.y -= 46 * Math.sin(Math.PI * q);
        const land = q > 0.85 ? Math.sin(Math.PI * (q - 0.85) / 0.15) : 0;
        p.sy -= 0.06 * land; p.sx += 0.04 * land; p.wl += 8 * env; p.wr += 8 * env; break;
      }
      case "celebrate": {
        p.y -= 34 * Math.abs(Math.sin(TAU * q));
        const a = 10 * Math.sin(TAU * 4 * q) * env; p.wl += a; p.wr += a; p.sparkle = env; break;
      }
      case "think": p.rot += -7 * lean * env; p.think = env; break;
      case "flap": { const a = 10 * Math.sin(TAU * 2 * q) * env; p.wl += a; p.wr += a; break; }
    }
  }
  // pop in on the first frame of the video
  const e = spring({ frame: f - enterAt, fps, config: { damping: 12, stiffness: 140 } });
  p.sx *= e; p.sy *= e;
  p.wl = clampWing(p.wl); p.wr = clampWing(p.wr);
  return p;
}

const Sparkle: React.FC<{ x: number; y: number; s: number; c: string }> = ({ x, y, s, c }) => (
  <svg style={{ position: "absolute", left: x - s / 2, top: y - s / 2, width: s, height: s }} viewBox="-10 -10 20 20">
    <path d="M0 -10 L2.4 -2.4 L10 0 L2.4 2.4 L0 10 L-2.4 2.4 L-10 0 L-2.4 -2.4 Z" fill={c} />
  </svg>
);

export const Mascot: React.FC<{ p: LessonProps; f: number; L: Layout; pal: Palette }> = ({ p, f, L, pal }) => {
  const { rig, base, beats, lines } = p.mascot;
  const talking = lines.some((l) => l.talk.some(([a, b]) => f >= a && f <= b));
  const lean = L.mascot.lean;
  const ps = pose(f, p.fps, beats, talking, lean, 0);
  const s = L.mascot.scale;
  const W = rig.width, H = rig.height;
  const body = rig.parts.find((x) => x.name === "body" || x.name === "card")!;
  const origin = `${body.pivot[0]}px ${body.pivot[1]}px`;

  // blink: ~every 3.6 s, 7 frames, closed in the middle
  const cyc = (f + 23) % 108;
  const lid = cyc < 7 ? Math.sin((Math.PI * cyc) / 7) : 0;

  const partStyle = (name: string, pivot: [number, number]): React.CSSProperties => {
    // CSS rotate is clockwise: left wing up = clockwise, right wing up = counter-clockwise
    const a = name === "wing_l" ? ps.wl : name === "wing_r" ? -ps.wr : 0;
    return { position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: `${pivot[0]}px ${pivot[1]}px`, transform: `rotate(${a}deg)` };
  };

  return (
    <div style={{ position: "absolute", left: L.mascot.cx - (W * s) / 2, top: L.mascot.baseY - H * s, width: W * s, height: H * s }}>
      {/* soft contact shadow */}
      <div style={{ position: "absolute", left: W * s * 0.3, top: H * s * 0.97, width: W * s * 0.4, height: 16 * s * 2, borderRadius: "50%", background: pal.text, opacity: 0.08 * (1 - Math.min(1, Math.max(0, -ps.y) / 80)), filter: "blur(6px)" }} />
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: "0 0", transform: `scale(${s})` }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: origin, transform: `translate(${ps.x}px, ${ps.y}px) rotate(${ps.rot}deg) scale(${ps.sx}, ${ps.sy})` }}>
          {[...rig.parts].sort((a, b) => a.z - b.z).map((part) => (
            <Img key={part.name} src={staticFile(`${base}/${part.file}`)} style={partStyle(part.name, part.pivot)} />
          ))}
          {lid > 0.02 && (
            <svg style={{ position: "absolute", left: 0, top: 0 }} width={W} height={H}>
              <defs>
                {rig.eyes.map((e, i) => (
                  <clipPath key={i} id={`eye${i}`}><ellipse cx={e.cx} cy={e.cy} rx={e.rx + 3} ry={e.ry + 3} /></clipPath>
                ))}
              </defs>
              {rig.eyes.map((e, i) => {
                const top = e.cy - e.ry - 3, h = (2 * e.ry + 6) * lid;
                return (
                  <g key={i} clipPath={`url(#eye${i})`}>
                    <rect x={e.cx - e.rx - 4} y={top} width={2 * e.rx + 8} height={h} fill={rig.lid_color} />
                    <path d={`M ${e.cx - e.rx - 2} ${top + h} Q ${e.cx} ${top + h + 5 * lid} ${e.cx + e.rx + 2} ${top + h}`} stroke={rig.lash_color} strokeWidth={3.5} fill="none" strokeLinecap="round" />
                  </g>
                );
              })}
            </svg>
          )}
        </div>
      </div>
      {ps.think > 0.05 && (
        <div style={{ position: "absolute", left: lean < 0 ? -10 : W * s - 50, top: -20 - 10 * ps.think, opacity: ps.think, fontFamily: SANS, fontWeight: 700, fontSize: 64 * s * 1.6, color: pal.teal }}>?</div>
      )}
      {ps.sparkle > 0.05 && [[-0.05, 0.15, 1], [1.02, 0.1, 0.8], [0.12, -0.08, 0.7], [0.9, -0.12, 0.9]].map(([x, y, k], i) => (
        <div key={i} style={{ opacity: ps.sparkle, transform: `scale(${0.6 + 0.4 * ps.sparkle})` }}>
          <Sparkle x={x * W * s} y={y * H * s + 30} s={44 * k} c={i % 2 ? pal.accent : pal.teal} />
        </div>
      ))}
    </div>
  );
};

/** Speech bubble for the mascot's short lines, styled after the one in the source art. */
export const Bubbles: React.FC<{ p: LessonProps; f: number; L: Layout; pal: Palette }> = ({ p, f, L, pal }) => (
  <>
    {p.mascot.lines.map((ln, i) => {
      if (f < ln.from || f > ln.to) return null;
      const inP = interpolate(f, [ln.from, ln.from + 8], [0, 1], { extrapolateRight: "clamp" });
      const outP = interpolate(f, [ln.to - 8, ln.to], [1, 0], { extrapolateLeft: "clamp" });
      const o = Math.min(inP, outP);
      const fs = L.type.bubble;
      const right = L.bubble.align === "right";
      return (
        <div key={i} style={{ position: "absolute", top: L.bubble.y, ...(right ? { right: 1920 - L.bubble.x } : { left: L.bubble.x }), maxWidth: L.bubble.maxW, opacity: o, transform: `scale(${0.92 + 0.08 * o})`, transformOrigin: right ? "100% 100%" : "0% 100%" }}>
          <div style={{ position: "relative", background: "#FFFDF8", border: `3px solid ${pal.line}`, borderRadius: fs * 0.7, padding: `${fs * 0.42}px ${fs * 0.75}px`, fontFamily: SANS, fontWeight: 700, fontSize: fs, color: pal.text, boxShadow: `0 6px 0 ${pal.line}` }}>
            {ln.text}
            <div style={{ position: "absolute", width: fs * 0.7, height: fs * 0.7, background: "#FFFDF8", borderRight: `3px solid ${pal.line}`, borderBottom: `3px solid ${pal.line}`, transform: "rotate(45deg)", ...(right ? { right: fs * 1.1, bottom: -fs * 0.38 } : { left: -fs * 0.38, top: "40%", transform: "rotate(135deg)" }) }} />
          </div>
        </div>
      );
    })}
  </>
);
