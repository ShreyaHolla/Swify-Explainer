import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, interpolate } from "remotion";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/500.css";
import type { LessonProps, Scene, Palette } from "./types";
import { LAYOUTS, Layout } from "./layout";
import { sceneFade, SANS, appear, rise } from "./scenes/common";
import { Title, Concept, List, Compare, Outro } from "./scenes/TextScenes";
import { Code } from "./scenes/Code";
import { Mascot, Bubbles } from "./mascot/Mascot";

const SCENES: Record<string, React.FC<{ s: Scene; f: number; pal: Palette; L: Layout }>> = {
  title: Title, concept: Concept, code: Code, compare: Compare, list: List, outro: Outro,
};

const SceneHost: React.FC<{ s: Scene; pal: Palette; L: Layout }> = ({ s, pal, L }) => {
  const f = useCurrentFrame();
  const C = SCENES[s.type];
  return <AbsoluteFill style={{ opacity: sceneFade(f, s.duration) }}><C s={s} f={f} pal={pal} L={L} /></AbsoluteFill>;
};

/** One-line captions for Shorts: the spoken word turns accent-coloured; fixed position, never jumps. */
const Captions: React.FC<{ p: LessonProps; f: number; L: Layout; pal: Palette }> = ({ p, f, L, pal }) => {
  const c = p.captions.find((x) => f >= x.from && f < x.to);
  if (!c) return null;
  const fs = L.type.caption;
  const active = c.words.reduce((k, w, i) => (f >= w.from ? i : k), -1); // exactly one word: the one being spoken
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: L.captionY - fs, display: "flex", justifyContent: "center" }}>
      <div style={{ background: `${pal.bg}EE`, border: `2px solid ${pal.line}`, borderRadius: fs * 0.5, padding: `${fs * 0.22}px ${fs * 0.55}px`, fontFamily: SANS, fontWeight: 700, fontSize: fs, color: pal.text, letterSpacing: -0.5, whiteSpace: "nowrap" }}>
        {c.words.map((w, i) => (
          <span key={i} style={{ color: i === active ? pal.accent : pal.text }}>{w.text}{i < c.words.length - 1 ? " " : ""}</span>
        ))}
      </div>
    </div>
  );
};

export const Lesson: React.FC<LessonProps> = (p) => {
  const f = useCurrentFrame();
  const pal = p.palette;
  const L = LAYOUTS[p.format];
  const scene = [...p.scenes].reverse().find((s) => f >= s.from);
  const hookP = p.hook ? Math.min(appear(f, 4, 10), interpolate(f, [80, 92], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) : 0;
  return (
    <AbsoluteFill style={{ background: pal.bg }}>
      {/* barely-there warmth so the flat background does not look dead */}
      <AbsoluteFill style={{ background: `radial-gradient(120% 80% at 50% 0%, #FFFFFF55 0%, transparent 60%)` }} />
      <Audio src={staticFile(p.audio)} trimBefore={p.audioStartFrame} />
      {p.scenes.map((s, i) => (
        <Sequence key={i} from={s.from} durationInFrames={s.duration} layout="none">
          <SceneHost s={s} pal={pal} L={L} />
        </Sequence>
      ))}
      {p.format === "portrait" && scene && (
        <div style={{ position: "absolute", left: L.content.x, top: 110, fontFamily: SANS, fontWeight: 600, fontSize: 30, color: pal.muted, opacity: 1 - hookP }}>
          {p.channel} · {scene.chapter}
        </div>
      )}
      {hookP > 0 && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 92, display: "flex", justifyContent: "center", ...rise(hookP, 12) }}>
          <div style={{ background: pal.accent, color: "#FFFDF8", fontFamily: SANS, fontWeight: 700, fontSize: 46, padding: "14px 34px", borderRadius: 40 }}>{p.hook}</div>
        </div>
      )}
      <Mascot p={p} f={f} L={L} pal={pal} />
      <Bubbles p={p} f={f} L={L} pal={pal} />
      {p.format === "portrait" && <Captions p={p} f={f} L={L} pal={pal} />}
      {p.format === "landscape" && (
        <div style={{ position: "absolute", left: 0, bottom: 0, height: 6, width: `${(f / p.durationInFrames) * 100}%`, background: pal.accent, opacity: 0.55 }} />
      )}
    </AbsoluteFill>
  );
};
