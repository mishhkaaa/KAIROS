"use client";

import { useQuery } from "@tanstack/react-query";
import { useClient } from "@/app/providers";
import type { Doc } from "@/lib/desktop/kairos";

export function usePendingApprovals() {
  const client = useClient();
  return useQuery({ queryKey: ["approvals", "pending"], queryFn: () => client.approvals("pending"), refetchInterval: 5_000 });
}

export function useResources() {
  const client = useClient();
  return useQuery({ queryKey: ["system-resources"], queryFn: () => client.resources(), refetchInterval: 2_000 });
}

export function useModels() {
  const client = useClient();
  return useQuery({ queryKey: ["models"], queryFn: () => client.models(), refetchInterval: 30_000 });
}

export function useTasks() {
  const client = useClient();
  return useQuery({ queryKey: ["tasks"], queryFn: () => client.listTasks(), refetchInterval: 3_000 });
}

/** Every document under /org (the tree is listed one folder at a time), for the wallpaper and the launcher. */
export function useAllDocs() {
  const client = useClient();
  return useQuery({
    queryKey: ["knowledge-all-docs"],
    staleTime: Infinity,
    queryFn: async () => {
      const docs: Doc[] = [];
      const walk = async (path: string, depth: number): Promise<void> => {
        const listing = await client.tree(path);
        const dirs = listing.entries.filter((e) => e.is_dir);
        for (const e of listing.entries) if (!e.is_dir) docs.push({ path: e.path, title: e.title ?? undefined });
        if (depth < 3) await Promise.all(dirs.map((d) => walk(d.path, depth + 1)));
      };
      await walk("/org", 0);
      return docs;
    },
  });
}
