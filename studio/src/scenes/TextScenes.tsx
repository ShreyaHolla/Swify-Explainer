import React from "react";
import { appear, rise, Eyebrow, SANS, MONO } from "./common";
import type { Palette, Scene } from "../types";
import type { Layout } from "../layout";

type P = { s: Scene; f: number; pal: Palette; L: Layout };
const col = (L: Layout, extra: React.CSSProperties = {}): React.CSSProperties => ({
  position: "absolute", left: L.content.x, top: L.content.y, width: L.content.w, height: L.content.h,
  display: "flex", flexDirection: "column", justifyContent: "center", ...extra,
});

export const Title: React.FC<P> = ({ s, f, pal, L }) => {
  const a = appear(f, 2, 14), b = appear(f, 10, 14), c = appear(f, 18, 12);
  return (
    <div style={col(L, { gap: L.type.title * 0.28 })}>
      <div style={{ width: 96 * c, height: 10, borderRadius: 5, background: pal.accent }} />
      <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: L.type.title, lineHeight: 1.04, letterSpacing: -L.type.title * 0.025, color: pal.text, ...rise(a, 20) }}>
        {s.title}
      </div>
      {s.hook && <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: L.type.hook, color: pal.muted, ...rise(b) }}>{s.hook}</div>}
    </div>
  );
};

/** One big idea; the highlighted word gets a soft marker sweep when it is spoken. */
export const Concept: React.FC<P> = ({ s, f, pal, L }) => {
  const words: string[] = s.text.split(" ");
  const hl = (s.highlight || "").toLowerCase();
  const sweep = s.cues.highlight != null ? appear(f, s.cues.highlight, 12) : 0;
  const sub = s.cues.sub != null ? appear(f, s.cues.sub, 10) : 0;
  return (
    <div style={col(L, { gap: 36 })}>
      <Eyebrow text={s.eyebrow} pal={pal} size={L.type.eyebrow} p={appear(f, 0, 10)} />
      <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: L.type.concept, lineHeight: 1.12, letterSpacing: -L.type.concept * 0.02, color: pal.text, ...rise(appear(f, 4, 14), 18) }}>
        {words.map((w, i) => {
          const isHl = w.toLowerCase().replace(/[^a-z0-9]/g, "") === hl;
          return (
            <span key={i} style={{ position: "relative", display: "inline-block", marginRight: "0.26em" }}>
              {isHl && (
                <span style={{ position: "absolute", left: "-0.08em", bottom: "0.06em", height: "0.42em", width: `calc(${sweep * 100}% + ${sweep * 0.16}em)`, background: pal.accent_soft, borderRadius: 6, zIndex: 0 }} />
              )}
              <span style={{ position: "relative", color: isHl && sweep > 0.5 ? pal.accent : undefined }}>{w}</span>
            </span>
          );
        })}
      </div>
      {s.sub && (
        <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: L.type.sub, color: pal.muted, ...rise(sub) }}>
          {s.sub.split(/(nil)/).map((part: string, i: number) =>
            part === "nil" ? <span key={i} style={{ fontFamily: MONO, color: pal.teal, background: pal.surface, padding: "0.05em 0.3em", borderRadius: 8 }}>nil</span> : part)}
        </div>
      )}
    </div>
  );
};

/** Up to three points, one per cue word. */
export const List: React.FC<P> = ({ s, f, pal, L }) => (
  <div style={col(L, { gap: L.type.list * 0.62 })}>
    <Eyebrow text={s.eyebrow} pal={pal} size={L.type.eyebrow} p={appear(f, 0, 10)} />
    {s.items.map((it: string, i: number) => {
      const p = appear(f, s.cues.items?.[i] ?? 0, 10);
      const parts = it.split(/(\?\?|if let)/);
      return (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: L.type.list * 0.5, ...rise(p) }}>
          <div style={{ flex: "none", width: L.type.list * 1.1, height: L.type.list * 1.1, borderRadius: "50%", background: pal.accent, color: pal.bg, fontFamily: SANS, fontWeight: 700, fontSize: L.type.list * 0.55, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {i + 1}
          </div>
          <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: L.type.list, color: pal.text, letterSpacing: -L.type.list * 0.01 }}>
            {parts.map((x, j) => (x === "??" || x === "if let" ? <span key={j} style={{ fontFamily: MONO, color: pal.teal }}>{x}</span> : x))}
          </div>
        </div>
      );
    })}
  </div>
);

/** Two columns (side by side in 16:9, stacked in 9:16); each side appears on its cue word. */
export const Compare: React.FC<P> = ({ s, f, pal, L }) => {
  const side = (k: "left" | "right") => {
    const d = s[k];
    const p = appear(f, s.cues[k] ?? 0, 12);
    const tone = d.tone === "bad" ? pal.bad : pal.good;
    return (
      <div key={k} style={{ flex: 1, background: pal.surface, borderRadius: 28, padding: L.type.compare * 1.1, display: "flex", flexDirection: "column", gap: L.type.compare * 0.7, borderTop: `8px solid ${tone}`, ...rise(p, 20) }}>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: L.type.compare * 1.15, color: tone }}>{d.title}</div>
        {d.items.map((it: string, i: number) => {
          const code = /[!?=]|if let/.test(it);
          return (
            <div key={i} style={{ fontVariantLigatures: "none", fontFamily: code ? MONO : SANS, fontWeight: code ? 500 : 600, fontSize: L.type.compare, color: pal.text }}>{it}</div>
          );
        })}
      </div>
    );
  };
  return (
    <div style={col(L, { gap: 40 })}>
      <Eyebrow text={s.eyebrow} pal={pal} size={L.type.eyebrow} p={appear(f, 0, 10)} />
      <div style={{ display: "flex", flexDirection: L.stacked ? "column" : "row", gap: 32 }}>
        {side("left")}
        {side("right")}
      </div>
    </div>
  );
};

export const Outro: React.FC<P> = ({ s, f, pal, L }) => (
  <div style={col(L, { gap: 28 })}>
    <Eyebrow text="Up next" pal={pal} size={L.type.eyebrow} p={appear(f, 0, 10)} />
    <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: L.type.title * 0.8, lineHeight: 1.06, letterSpacing: -2, color: pal.text, ...rise(appear(f, 6, 14), 18) }}>
      {s.title}
    </div>
    <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: L.type.hook * 0.9, color: pal.muted, ...rise(appear(f, 16, 12)) }}>{s.cta || "Subscribe for more lessons"}</div>
  </div>
);
