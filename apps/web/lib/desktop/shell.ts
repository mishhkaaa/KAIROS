/** The Terminal's pure parts: argument splitting, path resolution and column formatting (unit-tested). */

/** Split a command line like a shell: spaces separate, quotes group. */
export function splitArgs(line: string): string[] {
  const out: string[] = [];
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
  for (let m = re.exec(line); m; m = re.exec(line)) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

/** Resolve a path against the working directory, inside /org. */
export function resolvePath(cwd: string, arg?: string): string {
  if (!arg || arg === "~") return "/org";
  const parts = (arg.startsWith("/") ? arg : `${cwd}/${arg}`).split("/").filter(Boolean);
  const stack: string[] = [];
  for (const p of parts) {
    if (p === ".") continue;
    if (p === "..") stack.pop();
    else stack.push(p);
  }
  const path = `/${stack.join("/")}`;
  return path === "/" || !path.startsWith("/org") ? "/org" : path;
}

/** Left-aligned columns, each as wide as its widest cell. */
export function columns(rows: (string | number)[][]): string[] {
  const widths = rows.reduce<number[]>((w, r) => r.map((c, i) => Math.max(w[i] ?? 0, String(c).length)), []);
  return rows.map((r) => r.map((c, i) => (i === r.length - 1 ? String(c) : String(c).padEnd(widths[i]))).join("  ").trimEnd());
}

/** The longest common prefix of candidates, for tab completion. */
export function commonPrefix(xs: string[]): string {
  if (!xs.length) return "";
  let p = xs[0];
  for (const x of xs) while (!x.startsWith(p)) p = p.slice(0, -1);
  return p;
}
