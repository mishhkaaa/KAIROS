"use client";

import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useClient } from "@/app/providers";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./status";

export const isImage = (ref: string) => /\.(png|jpe?g)$/i.test(ref);
export const artifactName = (ref: string) => ref.replace(/^artifact:\/\/[^/]+\//, "");

// Bare /org paths in agent-written Markdown become explorer links (paths already inside a link are left alone).
const BARE_ORG_PATH = /(?<![([/\w`])(\/org(?:\/[A-Za-z0-9._-]+)+)/g;
const linkify = (md: string) => md.replace(BARE_ORG_PATH, "[$1]($1)");

/** Agent-written Markdown (the recovery plan). /org links open in the knowledge explorer. */
export function ArtifactMarkdown({ artifact }: { artifact: string }) {
  const client = useClient();
  const text = useQuery({ queryKey: ["artifact", artifact], queryFn: () => client.artifactText(artifact) });
  if (text.isPending) return <p className="text-sm text-muted-foreground">Loading {artifactName(artifact)}…</p>;
  if (text.isError) return <p className="text-sm text-st-failed">Couldn&apos;t load {artifactName(artifact)}: {String(text.error)}</p>;
  return (
    <div className="space-y-3 text-[15px] leading-relaxed [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mt-6 [&_h2]:border-b [&_h2]:border-line [&_h2]:pb-1.5 [&_h2]:text-[17px] [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:pl-1 [&_li]:py-0.5 [&_ol]:list-decimal [&_ul]:list-disc [&_strong]:font-semibold">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith("/org") ? (
              <EvidenceChip path={href} className="mx-0.5 align-baseline" />
            ) : (
              <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:underline">{children}</a>
            ),
        }}
      >
        {linkify(text.data)}
      </ReactMarkdown>
    </div>
  );
}

/** A screenshot artifact, served by GET /tasks/{id}/artifacts/{name}; click opens it full size. */
export function ArtifactImage({ artifact, className }: { artifact: string; className?: string }) {
  const client = useClient();
  const url = client.artifactUrl(artifact);
  if (!url) return <span className="font-mono text-xs text-ev-tool">{artifact}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" title={artifactName(artifact)} className={cn("block overflow-hidden rounded-lg border border-line bg-white", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- bytes come from the gateway, not a Next image source */}
      <img src={url} alt={`screenshot ${artifactName(artifact)}`} className="w-full" />
    </a>
  );
}
