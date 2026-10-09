"use client";

import { useEffect, useRef } from "react";
import { MODE_FRAMES, type OrbState, resolvePreset, scaleCounts, scaleRadii } from "thinking-orbs";
import { paintFrame } from "thinking-orbs/engine";

/** A thinking orb at any size (the package ships 20, 32 and 64 px). Draws the same engine frames straight onto a canvas
 *  of the requested size, so it stays crisp instead of upscaling a 64 px canvas. */
export function BigOrb({ state, size, dark = true, density = 1.6, className }: { state: OrbState; size: number; dark?: boolean; density?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    const { mode, speed, opts: base } = resolvePreset(state, 64);
    const opts = scaleRadii(scaleCounts(base, density), size / 64);
    const frameFn = MODE_FRAMES[mode];
    const draw = (t: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      paintFrame(ctx, frameFn(size, t * speed, opts), dark);
    };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      draw(0.6);
      return;
    }
    let raf = 0;
    const loop = () => {
      draw(performance.now() / 1000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [state, size, dark, density]);
  return <canvas ref={ref} role="img" aria-label={`KAIROS is ${state}`} className={className} style={{ width: size, height: size }} />;
}
