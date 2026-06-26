"use client";

import { useState, useEffect } from "react";
import type { PaperCitation } from "@/lib/supabase/types";

interface CitationsPanelProps {
  citations: PaperCitation[];
}

const INITIAL_VISIBLE = 20;

export function CitationsPanel({ citations }: CitationsPanelProps) {
  const [showAll, setShowAll] = useState(false);
  const [queueState, setQueueState] = useState<
    Record<string, "idle" | "loading" | "queued" | "exists" | "error">
  >({});

  // On mount: check which cited papers are already in the DB
  useEffect(() => {
    const arxivIds = citations
      .map((c) => c.arxiv_id)
      .filter((id): id is string => !!id);
    if (arxivIds.length === 0) return;

    fetch(`/api/status/batch?ids=${arxivIds.join(",")}`)
      .then((r) => r.json())
      .then((statusMap: Record<string, string>) => {
        const initial: Record<string, "idle" | "loading" | "queued" | "exists" | "error"> = {};
        for (const [id, status] of Object.entries(statusMap)) {
          if (status === "complete") initial[id] = "exists";
          else if (status === "pending" || status === "processing") initial[id] = "queued";
          // "error" stays "idle" — allow re-queue
        }
        setQueueState((prev) => ({ ...initial, ...prev }));
      })
      .catch(() => { /* silently ignore — buttons still work */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (citations.length === 0) return null;

  const visible = showAll ? citations : citations.slice(0, INITIAL_VISIBLE);
  const hiddenCount = citations.length - INITIAL_VISIBLE;

  async function handleQueue(arxivId: string) {
    setQueueState((s) => ({ ...s, [arxivId]: "loading" }));
    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Queue failed");
      setQueueState((s) => ({
        ...s,
        [arxivId]: json.existing ? "exists" : "queued",
      }));
    } catch {
      setQueueState((s) => ({ ...s, [arxivId]: "error" }));
    }
  }

  return (
    <div className="mt-10 border-t border-zinc-200 dark:border-zinc-700 pt-8">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-100">
          References
        </h2>
        <span className="inline-flex items-center rounded-full bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          {citations.length}
        </span>
      </div>

      <ul className="space-y-2">
        {visible.map((c) => (
          <CitationRow
            key={c.id}
            citation={c}
            state={c.arxiv_id ? (queueState[c.arxiv_id] ?? "idle") : "idle"}
            onQueue={handleQueue}
          />
        ))}
      </ul>

      {!showAll && hiddenCount > 0 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-4 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 underline-offset-2 hover:underline"
        >
          Show all {citations.length} references
        </button>
      )}
    </div>
  );
}

function CitationRow({
  citation,
  state,
  onQueue,
}: {
  citation: PaperCitation;
  state: "idle" | "loading" | "queued" | "exists" | "error";
  onQueue: (arxivId: string) => void;
}) {
  const label =
    citation.title ??
    citation.cite_key;

  return (
    <li className="flex items-start gap-3 rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-3 text-sm">
      <span className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500 shrink-0 font-mono w-5 text-right">
        {citation.order_idx + 1}.
      </span>

      <div className="flex-1 min-w-0">
        <p className="text-zinc-800 dark:text-zinc-200 leading-snug line-clamp-2">
          {label}
        </p>

        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {citation.arxiv_id && (
            <a
              href={`https://arxiv.org/abs/${citation.arxiv_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 px-2 py-0.5 text-xs text-orange-700 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-900 transition-colors"
            >
              arXiv:{citation.arxiv_id}
              <span className="text-orange-400">↗</span>
            </a>
          )}

          {!citation.arxiv_id && citation.url && (
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 underline-offset-2 hover:underline truncate max-w-[200px]"
            >
              {citation.url}
            </a>
          )}
        </div>
      </div>

      {/* Queue / View action — ArXiv citations only */}
      {citation.arxiv_id && (
        <div className="shrink-0 mt-0.5">
          {state === "idle" && (
            <button
              onClick={() => onQueue(citation.arxiv_id!)}
              className="text-xs rounded border border-zinc-300 dark:border-zinc-600 px-2.5 py-1 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              Queue
            </button>
          )}
          {state === "loading" && (
            <span className="text-xs text-zinc-400 animate-pulse">Queuing…</span>
          )}
          {state === "queued" && (
            <span className="text-xs text-green-600 dark:text-green-400">✓ Queued</span>
          )}
          {state === "exists" && (
            <a
              href={`/paper/${citation.arxiv_id}`}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              View →
            </a>
          )}
          {state === "error" && (
            <span className="text-xs text-red-500">Failed</span>
          )}
        </div>
      )}
    </li>
  );
}
