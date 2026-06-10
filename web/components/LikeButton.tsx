"use client";

import { useState } from "react";

interface LikeButtonProps {
  arxivId: string;
  initialLiked: boolean;
  initialUrl: string | null;
}

type State = "idle" | "loading" | "liked" | "error";

export function LikeButton({ arxivId, initialLiked, initialUrl }: LikeButtonProps) {
  const [state, setState] = useState<State>(initialLiked ? "liked" : "idle");
  const [githubUrl, setGithubUrl] = useState<string | null>(initialUrl);

  async function handleLike() {
    if (state === "liked" || state === "loading") return;
    setState("loading");
    try {
      const res = await fetch("/api/like", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
      const data = await res.json() as { liked?: boolean; github_md_url?: string; error?: string };
      if (!res.ok) throw new Error(data.error ?? "Unknown error");
      setGithubUrl(data.github_md_url ?? null);
      setState("liked");
    } catch {
      setState("error");
      // auto-reset error state after 3s
      setTimeout(() => setState("idle"), 3000);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleLike}
        disabled={state === "loading" || state === "liked"}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
          state === "liked"
            ? "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400 cursor-default"
            : state === "error"
            ? "border-red-300 dark:border-red-700 text-red-500 dark:text-red-400"
            : "border-zinc-300 dark:border-zinc-600 hover:border-amber-400 dark:hover:border-amber-600 hover:text-amber-500 dark:hover:text-amber-400"
        }`}
        title={state === "liked" ? "Saved to knowledge base" : "Save to knowledge base"}
      >
        {state === "loading" ? (
          <span className="animate-spin text-base">⟳</span>
        ) : (
          <span className="text-base">{state === "liked" ? "★" : "☆"}</span>
        )}
        <span>{state === "error" ? "Failed — retry" : state === "liked" ? "Saved" : "Save"}</span>
      </button>

      {state === "liked" && githubUrl && (
        <a
          href={githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 underline underline-offset-2"
        >
          View on GitHub →
        </a>
      )}
    </div>
  );
}
