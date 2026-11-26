export type Palette = {
  bg: string; surface: string; line: string; accent: string; accent_soft: string; text: string; muted: string;
  teal: string; good: string; bad: string;
  syntax: { keyword: string; type: string; string: string; number: string; comment: string; plain: string; call: string };
};
export type Format = "landscape" | "portrait";
export type Scene = {
  type: "title" | "concept" | "code" | "compare" | "list" | "outro";
  from: number; duration: number; chapter: string; chapterIndex: number; cues: Record<string, any>;
  [k: string]: any;
};
export type RigPart = { name: string; file: string; pivot: [number, number]; z: number };
export type Rig = {
  name: string; width: number; height: number; mode: "parts" | "card"; parts: RigPart[];
  eyes: { cx: number; cy: number; rx: number; ry: number }[]; lid_color: string; lash_color: string;
};
export type Caption = { from: number; to: number; words: { text: string; from: number; to: number }[] };
export type LessonProps = {
  format: Format; width: number; height: number; fps: number; durationInFrames: number;
  audio: string; audioStartFrame: number; title: string; hook?: string; channel: string;
  palette: Palette; scenes: Scene[]; chapters: { index: number; title: string; from: number }[]; captions: Caption[];
  mascot: { rig: Rig; base: string; beats: { name: string; at: number }[]; lines: { text: string; from: number; to: number; talk: [number, number][] }[] };
};
