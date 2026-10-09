"use client";

import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useRef, useState } from "react";
import { useClient } from "@/app/providers";
import { type Box, hash2, layoutKairos } from "@/lib/desktop/kairos";
import { FOLDER_HUES } from "@/lib/desktop/palette";
import { strList } from "@/lib/events";
import { useAllDocs } from "./hooks";

type Flare = { t0: number; kind: "read" | "flagged" | "stale" | "changed" };
const FLARE_MS: Record<Flare["kind"], number> = { read: 2400, flagged: 9000, stale: 12000, changed: 3000 };
const FLARE_RGB: Record<Flare["kind"], string> = { read: "20,184,166", flagged: "239,68,68", stale: "245,158,11", changed: "59,130,246" };

interface Tessera {
  path: string;
  title: string;
  folder: string;
  col: number;
  row: number;
  hue: string;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, r: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, s, s, r);
}

/** The desktop is a tiled floor. Every cell is a pale tile; every /org document is one coloured tessera, each folder
 *  a patch in its own colour, ringed around the Ask bar. When an agent reads a document its tessera lights up. Painted
 *  once; only lit tesserae animate, on a separate layer and only while one is lit. */
export function Wallpaper({ avoid }: { avoid?: Box[] }) {
  const base = useRef<HTMLCanvasElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const flares = useRef(new Map<string, Flare>());
  const kick = useRef<() => void>(() => {});
  const client = useClient();
  const router = useRouter();
  const docs = useAllDocs().data;
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<Tessera | null>(null);
  const cell = size.w < 700 ? 24 : 30;

  useEffect(() => {
    let t = 0;
    const measure = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    const on = () => {
      clearTimeout(t);
      t = window.setTimeout(measure, 120);
    };
    measure();
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);

  const layout = useMemo(() => {
    if (!docs || !size.w) return null;
    if (size.w < 1100) return layoutKairos(docs, size.w, size.h, cell);
    // A border of patches round the space the widget column leaves, the Ask bar in the calm middle.
    const right = avoid?.find((b) => b[1] <= 0 && b[3] >= 1)?.[0] ?? 1;
    return layoutKairos(docs, size.w, size.h, cell, { frame: [0.06, 0.1, right - 0.06, 0.8], avoid });
  }, [docs, size.w, size.h, cell, avoid]);
  const tesserae: Tessera[] = useMemo(
    () => (layout?.tiles ?? []).map((t) => ({ path: t.path, title: t.title ?? t.path, folder: t.folder, col: t.col, row: t.row, hue: FOLDER_HUES[t.folder] ?? "#8a94a6" })),
    [layout],
  );
  const byPath = useMemo(() => new Map(tesserae.map((n) => [n.path, n])), [tesserae]);
  const byCell = useMemo(() => new Map(tesserae.map((n) => [`${n.col},${n.row}`, n])), [tesserae]);

  // The static layer: the pale floor, the documents' tesserae, the folder names. Redrawn only when data, size or theme change.
  useEffect(() => {
    const c = base.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx || !size.w) return;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    c.width = Math.round(size.w * dpr);
    c.height = Math.round(size.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);
    const cols = Math.ceil(size.w / cell);
    const rows = Math.ceil(size.h / cell);
    const gap = 3;
    const s = cell - gap * 2;
    // The floor: pale tiles, a little uneven like laid stone, fading out towards the middle where the Ask bar sits.
    const ink = dark ? "226,232,240" : "30,41,59";
    const mx = size.w / 2;
    const my = size.h * 0.4;
    const reach = Math.hypot(size.w, size.h) * 0.42;
    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {
        if (byCell.has(`${q},${r}`)) continue;
        const x = q * cell + gap;
        const y = r * cell + gap;
        const d = Math.min(1, Math.hypot(x - mx, y - my) / reach);
        const a = (0.022 + 0.03 * hash2(q, r)) * (0.25 + 0.75 * d * d) * (dark ? 1.3 : 1);
        ctx.fillStyle = `rgba(${ink},${a.toFixed(3)})`;
        roundRect(ctx, x, y, s, 5);
        ctx.fill();
      }
    }
    // The documents: solid tesserae in their folder's colour, with a faint top light.
    for (const n of tesserae) {
      const x = n.col * cell + gap;
      const y = n.row * cell + gap;
      const shade = 0.7 + 0.3 * hash2(n.col + 3, n.row + 7);
      ctx.globalAlpha = (dark ? 0.78 : 0.86) * shade;
      ctx.fillStyle = n.hue;
      roundRect(ctx, x, y, s, 5);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(255,255,255,0.22)";
      ctx.fillRect(x + 4, y + 1, s - 8, 1);
    }
    // Folder names, small and quiet, above each patch.
    const mono = getComputedStyle(document.documentElement).getPropertyValue("--font-jetbrains-mono").trim() || "monospace";
    ctx.font = `600 10.5px ${mono}, monospace`;
    ctx.textAlign = "center";
    ctx.fillStyle = dark ? "rgba(226,232,240,0.5)" : "rgba(15,23,42,0.42)";
    for (const l of layout?.labels ?? []) ctx.fillText(`/${l.folder}`, l.x, l.y);
  }, [tesserae, byCell, layout, size.w, size.h, cell, dark]);

  // Live light from the kernel's events, on the overlay; the loop runs only while a tessera is lit.
  useEffect(
    () =>
      client.events(
        (e) => {
          const now = performance.now();
          const add = (paths: string[], kind: Flare["kind"]) => paths.forEach((p) => flares.current.set(p, { t0: now, kind }));
          if (e.type === "knowledge.retrieved") {
            const flagged = strList(e, "flagged");
            add(strList(e, "paths").filter((p) => !flagged.includes(p)), "read");
            add(flagged, "flagged");
          } else if (e.type === "memory.invalidated" && typeof e.payload?.source === "string") add([e.payload.source], "stale");
          else if (e.type === "knowledge.changed" && typeof e.payload?.path === "string") add([e.payload.path], "changed");
          else return;
          kick.current();
        },
        { types: ["knowledge.retrieved", "memory.invalidated", "knowledge.changed"] },
      ),
    [client],
  );

  useEffect(() => {
    const c = overlay.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx || !size.w) return;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    c.width = Math.round(size.w * dpr);
    c.height = Math.round(size.h * dpr);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const draw = () => {
      const now = performance.now();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.w, size.h);
      let live = false;
      for (const [path, f] of flares.current) {
        const n = byPath.get(path);
        const age = now - f.t0;
        if (!n || age > FLARE_MS[f.kind]) {
          flares.current.delete(path);
          continue;
        }
        live = true;
        const fade = 1 - age / FLARE_MS[f.kind];
        const pulse = f.kind === "flagged" || f.kind === "stale" ? 0.6 + 0.4 * Math.cos(age / 220) : 1;
        const rgb = FLARE_RGB[f.kind];
        const x = n.col * cell;
        const y = n.row * cell;
        ctx.fillStyle = `rgba(${rgb},${0.3 * fade * pulse})`;
        roundRect(ctx, x - 4, y - 4, cell + 8, 9);
        ctx.fill();
        ctx.strokeStyle = `rgba(${rgb},${0.95 * fade})`;
        ctx.lineWidth = 2;
        roundRect(ctx, x + 2, y + 2, cell - 4, 6);
        ctx.stroke();
        if (!reduced && age < 1000) {
          const q = age / 1000;
          const grow = q * 22;
          ctx.strokeStyle = `rgba(${rgb},${0.6 * (1 - q)})`;
          ctx.lineWidth = 1.5;
          roundRect(ctx, x - grow, y - grow, cell + grow * 2, 8 + grow / 2);
          ctx.stroke();
        }
      }
      raf = live && !reduced ? requestAnimationFrame(draw) : 0;
    };
    kick.current = () => {
      if (!raf) raf = requestAnimationFrame(draw);
    };
    return () => {
      cancelAnimationFrame(raf);
      kick.current = () => {};
    };
  }, [byPath, size.w, size.h, cell]);

  const hit = (x: number, y: number) => byCell.get(`${Math.floor(x / cell)},${Math.floor(y / cell)}`) ?? null;

  return (
    <div className="ground absolute inset-0" aria-hidden>
      <canvas ref={base} className="absolute inset-0 size-full" />
      <canvas
        ref={overlay}
        className="absolute inset-0 size-full"
        onPointerMove={(e) => {
          const n = hit(e.clientX, e.clientY);
          if (n?.path !== hover?.path) setHover(n);
        }}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          const n = hit(e.clientX, e.clientY);
          if (n) router.push(`/knowledge?path=${encodeURIComponent(n.path)}`);
        }}
        style={{ cursor: hover ? "pointer" : "default" }}
      />
      {hover && (
        <div
          className="panel pointer-events-none absolute z-10 flex items-center gap-2 rounded-lg px-2.5 py-1.5"
          style={{ left: Math.min(hover.col * cell + cell + 8, size.w - 320), top: hover.row * cell + cell + 6 }}
        >
          <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: hover.hue }} />
          <span>
            <span className="block text-sm font-medium">{hover.title}</span>
            <span className="block font-mono text-xs text-text-2">{hover.path}</span>
          </span>
        </div>
      )}
    </div>
  );
}
