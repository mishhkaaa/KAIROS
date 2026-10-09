import type { MemoryRecord } from "@kairos/contracts";

/** The id of the memory this one was re-derived to replace (tag `replaces:<id>`), if any. */
export function replacesOf(m: MemoryRecord): string | undefined {
  return m.tags?.find((t) => t.startsWith("replaces:"))?.slice("replaces:".length);
}

/** A memory and the records it was re-derived from, newest first (a chain when the source changed more than once). */
export type MemoryGroup = { memory: MemoryRecord; replaced: MemoryRecord[] };

/** One entry per memory, keeping the list's order, except that a re-derived memory carries the records it replaced
 *  (those in the list) and they are not listed again on their own. */
export function groupMemories(memories: MemoryRecord[]): MemoryGroup[] {
  const byId = new Map(memories.map((m) => [m.memory_id, m]));
  const replaced = new Set<string>();
  for (const m of memories) {
    const old = replacesOf(m);
    if (old && byId.has(old)) replaced.add(old);
  }
  const groups: MemoryGroup[] = [];
  for (const m of memories) {
    if (replaced.has(m.memory_id)) continue;
    const chain: MemoryRecord[] = [];
    for (let old = replacesOf(m); old && byId.has(old) && !chain.some((c) => c.memory_id === old); ) {
      const prev = byId.get(old)!;
      chain.push(prev);
      old = replacesOf(prev);
    }
    groups.push({ memory: m, replaced: chain });
  }
  return groups;
}
