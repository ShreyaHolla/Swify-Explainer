import type { Format } from "./types";

// Where things live in each frame. Content gets the lion's share; the mascot keeps to its corner and never
// overlaps the content box; Shorts keep clear of the YouTube UI (right edge, bottom 20%).
export type Box = { x: number; y: number; w: number; h: number };
export type Layout = {
  content: Box;
  mascot: { cx: number; baseY: number; scale: number; lean: 1 | -1 };   // lean: which way "toward the content" is
  bubble: { x: number; y: number; align: "right" | "left"; maxW: number };
  captionY: number;
  type: { eyebrow: number; title: number; hook: number; concept: number; sub: number; code: number; list: number; compare: number; bubble: number; caption: number };
  stacked: boolean; // compare columns stacked (portrait) or side by side
};

export const LAYOUTS: Record<Format, Layout> = {
  landscape: {
    content: { x: 120, y: 110, w: 1300, h: 860 },
    mascot: { cx: 1665, baseY: 985, scale: 0.72, lean: -1 },
    bubble: { x: 1575, y: 560, align: "right", maxW: 420 },
    captionY: 0,
    type: { eyebrow: 28, title: 104, hook: 44, concept: 82, sub: 40, code: 40, list: 54, compare: 38, bubble: 34, caption: 0 },
    stacked: false,
  },
  portrait: {
    content: { x: 70, y: 200, w: 940, h: 950 },
    mascot: { cx: 220, baseY: 1415, scale: 0.5, lean: 1 },
    bubble: { x: 390, y: 1215, align: "left", maxW: 560 },
    captionY: 1488,
    type: { eyebrow: 30, title: 96, hook: 46, concept: 76, sub: 40, code: 38, list: 52, compare: 38, bubble: 38, caption: 54 },
    stacked: true,
  },
};
