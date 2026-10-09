/** The wallpaper's layout: one tessera per /org document, each folder a patch of tesserae around its own seed on an
 *  ellipse (the centre stays clear for the composer). Pure and deterministic, so it is unit-tested. */

export interface Doc {
  path: string;
  title?: string;
}

export interface Tile {
  path: string;
  title?: string;
  folder: string;
  col: number;
  row: number;
}

export interface KairosLayout {
  cell: number;
  cols: number;
  rows: number;
  tiles: Tile[];
  /** Where each folder's name is drawn: just above its patch, in px. */
  labels: { folder: string; x: number; y: number }[];
}

/** `/org/slack/apollo-eng/x` belongs to `slack`. */
export function folderOf(path: string): string {
  return path.split("/")[2] ?? "org";
}

/** A stable 0..1 value per cell, for the tesserae's jitter and the filler's shading. */
export function hash2(a: number, b: number): number {
  let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** A box as fractions of the screen: [x0, y0, x1, y1]. */
export type Box = [x0: number, y0: number, x1: number, y1: number];

/** `cx`/`rx` (fractions of the width) and `cy`/`ry` (of the height) place the ellipse the folder patches sit on (the
 *  default centres it); `avoid` keeps boxes clear, for what the desktop draws over the wallpaper. */
export function layoutKairos(
  docs: Doc[],
  width: number,
  height: number,
  cell = 26,
  shape: { cx?: number; rx?: number; cy?: number; ry?: number; avoid?: Box | Box[]; frame?: Box } = {},
): KairosLayout {
  const cols = Math.max(1, Math.floor(width / cell));
  const rows = Math.max(1, Math.floor(height / cell));
  const groups = new Map<string, Doc[]>();
  for (const d of [...docs].sort((a, b) => a.path.localeCompare(b.path))) {
    const f = folderOf(d.path);
    groups.set(f, [...(groups.get(f) ?? []), d]);
  }
  const folders = [...groups.keys()].sort();
  const taken = new Set<string>();
  const tiles: Tile[] = [];
  const labels: KairosLayout["labels"] = [];
  const cx = cols * (shape.cx ?? 0.5);
  const cy = rows * (shape.cy ?? 0.47);
  const rx = cols * (shape.rx ?? 0.37);
  const ry = rows * (shape.ry ?? 0.33);
  // Rows kept clear: the top bar (first row) and the dock (last three rows).
  const boxes: Box[] = !shape.avoid ? [] : typeof shape.avoid[0] === "number" ? [shape.avoid as Box] : (shape.avoid as Box[]);
  const avoided = (c: number, r: number) =>
    boxes.some(([x0, y0, x1, y1]) => c >= x0 * cols && c <= x1 * cols && r >= y0 * rows && r <= y1 * rows);
  const free = (c: number, r: number) => c >= 0 && c < cols && r >= 1 && r < rows - 3 && !avoided(c, r) && !taken.has(`${c},${r}`);

  const room = (c: number, r: number) => {
    let n = 0;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) n += free(c + dc, r + dr) ? 1 : 0;
    return n;
  };
  // A seed that lands in a kept-clear box (or on another patch) moves to the nearest cell with room around it first;
  // growing from inside a box would string the patch out along the box's edge.
  const reseat = (c0: number, r0: number): [number, number] => {
    if (free(c0, r0) && room(c0, r0) >= 7) return [c0, r0];
    for (let ring = 1; ring < Math.max(cols, rows); ring++) {
      let best: [number, number] | null = null;
      for (let dr = -ring; dr <= ring; dr++) {
        for (let dc = -ring; dc <= ring; dc++) {
          if (Math.max(Math.abs(dr), Math.abs(dc)) !== ring) continue;
          if (free(c0 + dc, r0 + dr) && room(c0 + dc, r0 + dr) >= 7 && (!best || dr * dr + dc * dc < (best[0] - c0) ** 2 + (best[1] - r0) ** 2)) best = [c0 + dc, r0 + dr];
        }
      }
      if (best) return best;
    }
    return [c0, r0];
  };

  // `frame`: seeds evenly spaced round a rectangle (a tiled border), clockwise from its top-left corner. Otherwise an
  // ellipse, starting at the top.
  const seed = (i: number): [number, number] => {
    if (shape.frame) {
      const [x0, y0, x1, y1] = shape.frame;
      const w = (x1 - x0) * cols;
      const h = (y1 - y0) * rows;
      let d = ((i + 0.5) / folders.length) * 2 * (w + h);
      const at = (x: number, y: number): [number, number] => [Math.round(x0 * cols + x), Math.round(y0 * rows + y)];
      if (d < w) return at(d, 0);
      if ((d -= w) < h) return at(w, d);
      if ((d -= h) < w) return at(w - d, h);
      return at(0, h - (d - w));
    }
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / folders.length;
    return [Math.round(cx + rx * Math.cos(angle)), Math.round(cy + ry * Math.sin(angle))];
  };

  folders.forEach((folder, i) => {
    const [sc, sr] = reseat(...seed(i));
    let minRow = Infinity;
    let sumCol = 0;
    const placed: Tile[] = [];
    for (const d of groups.get(folder)!) {
      // Walk rings outward from the seed and take the first free cell: patches stay compact and never overlap.
      search: for (let ring = 0; ring < Math.max(cols, rows); ring++) {
        for (let dr = -ring; dr <= ring; dr++) {
          for (let dc = -ring; dc <= ring; dc++) {
            if (Math.max(Math.abs(dr), Math.abs(dc)) !== ring) continue;
            const c = sc + dc;
            const r = sr + dr;
            if (free(c, r)) {
              taken.add(`${c},${r}`);
              placed.push({ path: d.path, title: d.title, folder, col: c, row: r });
              break search;
            }
          }
        }
      }
    }
    for (const t of placed) {
      minRow = Math.min(minRow, t.row);
      sumCol += t.col;
    }
    tiles.push(...placed);
    // The name goes above the patch, or below it when the patch touches the top bar.
    const maxRow = Math.max(...placed.map((t) => t.row));
    if (placed.length) labels.push({ folder, x: (sumCol / placed.length + 0.5) * cell, y: minRow <= 1 ? (maxRow + 1) * cell + 12 : minRow * cell - 6 });
  });
  return { cell, cols, rows, tiles, labels };
}

/** The document tile under a point, if any. */
export function tileAt(layout: KairosLayout, x: number, y: number): Tile | undefined {
  const c = Math.floor(x / layout.cell);
  const r = Math.floor(y / layout.cell);
  return layout.tiles.find((t) => t.col === c && t.row === r);
}
