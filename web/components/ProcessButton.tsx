"use client";

import { useState } from "react";
import { PaperStatusStream } from "@/components/PaperStatusStream";

interface ProcessButtonProps {
  arxivId: string;
}

export function ProcessButton({ arxivId }: ProcessButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "triggered" | "error">("idle");

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

  if (state === "error") {
    return (
      <span className="text-xs text-red-500 font-medium shrink-0">Failed — retry?</span>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-md border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900 disabled:opacity-50 transition-colors"
    >
      {state === "loading" ? "Requesting…" : "Request processing"}
    </button>
  );
}
