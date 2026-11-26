import React from "react";
import { Composition } from "remotion";
import { Lesson } from "./Lesson";
import type { LessonProps } from "./types";
import sample from "./sample.json";

// One composition renders any lesson in any format: size and length come from the props (build/props_*.json).
export const Root: React.FC = () => (
  <Composition
    id="Lesson"
    component={Lesson as unknown as React.FC<Record<string, unknown>>}
    defaultProps={sample as unknown as Record<string, unknown>}
    fps={30}
    width={1920}
    height={1080}
    durationInFrames={300}
    calculateMetadata={({ props }) => {
      const p = props as unknown as LessonProps;
      return { width: p.width, height: p.height, fps: p.fps, durationInFrames: p.durationInFrames };
    }}
  />
);
