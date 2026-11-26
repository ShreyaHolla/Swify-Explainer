import React from "react";
import { appear, rise, Eyebrow, SANS, MONO } from "./common";
import type { Palette, Scene } from "../types";
import type { Layout } from "../layout";

// ---- a small Swift highlighter (enough for teaching snippets; swap per language via KEYWORDS)
const KEYWORDS = new Set([
  "let", "var", "func", "if", "else", "guard", "return", "struct", "class", "enum", "case", "switch", "default",
  "for", "in", "while", "nil", "true", "false", "import", "protocol", "extension", "init", "self", "try", "catch",
  "throw", "throws", "async", "await", "some", "any", "private", "public", "static", "where", "do", "break", "continue",
]);
type Tok = { t: string; k: keyof Palette["syntax"] };
const RX = /(\/\/.*$)|("(?:[^"\\]|\\.)*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|(.)/g;
export const highlight = (line: string): Tok[] => {
  const out: Tok[] = [];
  let m: RegExpExecArray | null;
  RX.lastIndex = 0;
  while ((m = RX.exec(line))) {
    const [all, com, str, num, id] = m;
    if (com) out.push({ t: all, k: "comment" });
    else if (str) out.push({ t: all, k: "string" });
    else if (num) out.push({ t: all, k: "number" });
    else if (id) {
      const next = line.slice(RX.lastIndex).trimStart()[0];
      out.push({ t: all, k: KEYWORDS.has(id) ? "keyword" : /^[A-Z]/.test(id) ? "type" : next === "(" ? "call" : "plain" });
    } else out.push({ t: all, k: "plain" });
  }
  return out;
};

/** Code card: lines type in on their cue word, the newest step is highlighted and earlier lines dim; on the
 *  output cue everything brightens and the real program output slides up underneath. */
export const Code: React.FC<{ s: Scene; f: number; pal: Palette; L: Layout }> = ({ s, f, pal, L }) => {
  const fs = L.type.code;
  const lines: string[] = s.lines;
  const steps: { lines: number[]; at: number }[] = s.steps;
  const outAt: number | undefined = s.cues.output;
  const showOut = outAt != null && f >= outAt;
  const firstAt: Record<number, number> = {};
  steps.forEach((st) => st.lines.forEach((n) => { if (firstAt[n] == null || st.at < firstAt[n]) firstAt[n] = st.at; }));
  const current = [...steps].reverse().find((st) => f >= st.at);
  const filename = (s.file || "main.swift").split("/").pop();

  return (
    <div style={{ position: "absolute", left: L.content.x, top: L.content.y, width: L.content.w, height: L.content.h, display: "flex", flexDirection: "column", justifyContent: "center", gap: 30 }}>
      <Eyebrow text={s.eyebrow} pal={pal} size={L.type.eyebrow} p={appear(f, 0, 10)} />
      <div style={{ background: pal.surface, borderRadius: 28, border: `2px solid ${pal.line}`, overflow: "hidden", ...rise(appear(f, 2, 12), 18) }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "20px 28px", borderBottom: `2px solid ${pal.line}` }}>
          {[pal.bad, pal.accent, pal.good].map((c, i) => <div key={i} style={{ width: 16, height: 16, borderRadius: 8, background: c, opacity: 0.7 }} />)}
          <div style={{ marginLeft: 12, fontFamily: MONO, fontSize: fs * 0.62, color: pal.muted }}>{filename}</div>
        </div>
        <div style={{ padding: `${fs * 0.7}px 0`, fontFamily: MONO, fontWeight: 500, fontSize: fs, lineHeight: 1.6, whiteSpace: "pre" }}>
          {lines.map((line, i) => {
            const n = i + 1;
            const at = firstAt[n];
            const blank = line.trim() === "";
            const shown = blank || (at != null && f >= at);
            const typeFrames = Math.min(18, Math.max(6, line.length * 0.6));
            const chars = at == null ? line.length : Math.floor(Math.min(1, (f - at) / typeFrames) * line.length);
            const focus = !showOut && current && current.lines.includes(n);
            const dim = !showOut && current && !focus && !blank;
            let left = blank ? line : line.slice(0, chars);
            const toks = highlight(left);
            return (
              <div key={i} style={{ position: "relative", padding: `0 ${fs * 1.0}px 0 ${fs * 2.6}px`, opacity: shown ? (dim ? 0.42 : 1) : 0, background: focus ? `${pal.accent}1F` : "transparent", borderLeft: `6px solid ${focus ? pal.accent : "transparent"}`, minHeight: fs * 1.6 }}>
                <span style={{ position: "absolute", left: fs * 0.6, width: fs * 1.4, textAlign: "right", color: pal.muted, opacity: 0.55 }}>{n}</span>
                {toks.map((t, j) => <span key={j} style={{ color: pal.syntax[t.k] }}>{t.t}</span>)}
                {shown && !blank && chars < line.length && <span style={{ display: "inline-block", width: fs * 0.55, height: fs * 1.1, marginBottom: -fs * 0.2, background: pal.accent }} />}
              </div>
            );
          })}
        </div>
      </div>
      {outAt != null && (
        <div style={{ display: "flex", gap: 20, alignItems: "stretch", ...rise(appear(f, outAt, 10), 20) }}>
          <div style={{ width: 8, borderRadius: 4, background: pal.good }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: fs * 0.62, letterSpacing: 3, textTransform: "uppercase", color: pal.muted }}>
              Output
            </div>
            <div style={{ fontFamily: MONO, fontWeight: 500, fontSize: fs, lineHeight: 1.45, color: pal.text, whiteSpace: "pre" }}>{s.output}</div>
          </div>
        </div>
      )}
    </div>
  );
};
