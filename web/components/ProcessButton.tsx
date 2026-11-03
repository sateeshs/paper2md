"use client";

import { useState } from "react";
import { PaperStatusStream } from "@/components/PaperStatusStream";

interface ProcessButtonProps {
  arxivId: string;
}

export function ProcessButton({ arxivId }: ProcessButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "triggered" | "error" | "not_configured">("idle");

  async function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setState("loading");
    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
      if (res.ok) {
        setState("triggered");
      } else if (res.status === 503) {
        // Trigger not configured — paper is queued but won't be auto-processed
        setState("not_configured");
      } else {
        setState("error");
      }
    } catch {
      setState("error");
    }
  }

  if (state === "triggered") {
    return <PaperStatusStream arxivId={arxivId} />;
  }

  if (state === "not_configured") {
    return (
      <span className="text-xs text-amber-600 font-medium shrink-0" title="No processing backend configured — set PAPER_PROCESSOR_MCP_URL or GITHUB_DISPATCH_TOKEN">
        Queued — no processor configured
      </span>
    );
  }

  const failed = state === "error";

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-md border disabled:opacity-50 transition-colors ${
        failed
          ? "border-red-200 bg-red-50 text-red-600 hover:bg-red-100 hover:text-red-700"
          : "border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900"
      }`}
    >
      {state === "loading" ? "Requesting…" : failed ? "Failed — retry" : "Request processing"}
    </button>
  );
}
