"use client";

import { useState, useTransition, useRef, useEffect } from "react";
import type { ArxivResult } from "@/app/api/arxiv/route";
import { extractArxivId } from "@/lib/arxiv-id";
import { PaperStatusStream } from "@/components/PaperStatusStream";

type Tab = "id" | "title";
type QueueStatus = "idle" | "ok" | "exists" | "error";
type StreamingIds = Set<string>;

export function QueueForm() {
  const [tab, setTab] = useState<Tab>("title");

  return (
    <div className="bg-white rounded-xl border border-zinc-200 shadow-sm overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-zinc-100">
        <TabButton active={tab === "title"} onClick={() => setTab("title")}>
          Search ArXiv
        </TabButton>
        <TabButton active={tab === "id"} onClick={() => setTab("id")}>
          Paste ID
        </TabButton>
      </div>

      <div className="p-5">
        {tab === "title" ? <TitleSearch /> : <IdForm />}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
        active
          ? "text-blue-600 border-b-2 border-blue-600 -mb-px bg-white"
          : "text-zinc-400 hover:text-zinc-700"
      }`}
    >
      {children}
    </button>
  );
}

// ── Tab: search ArXiv by title ────────────────────────────────────────────────

function TitleSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ArxivResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [queueStatus, setQueueStatus] = useState<Record<string, QueueStatus>>({});
  const [streaming, setStreaming] = useState<StreamingIds>(new Set());
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // If the user pastes a URL/ID, skip ArXiv search
  const resolvedId = extractArxivId(query.trim());
  const isUrl = resolvedId !== null && (query.includes("/") || /^\d{4}\.\d{4,5}/.test(query.trim()));

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (isUrl) { setResults([]); return; }
    if (query.trim().length < 3) { setResults([]); return; }

    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await fetch(`/api/arxiv?q=${encodeURIComponent(query.trim())}`);
        const data: ArxivResult[] = await res.json();
        setResults(data);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 400);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, isUrl]);

  async function queue(arxivId: string, title?: string) {
    setQueueStatus((s) => ({ ...s, [arxivId]: "idle" }));
    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId, title }),
      });
      const json = await res.json();
      const next: QueueStatus = json.existing ? "exists" : res.ok ? "ok" : "error";
      setQueueStatus((s) => ({ ...s, [arxivId]: next }));
      if (next === "ok") {
        setStreaming((s) => new Set(s).add(arxivId));
      }
    } catch {
      setQueueStatus((s) => ({ ...s, [arxivId]: "error" }));
    }
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by title, or paste arxiv.org / alphaxiv.org URL"
          autoComplete="off"
          className="w-full rounded-lg border border-zinc-300 bg-zinc-50 px-4 py-2.5 text-sm placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent focus:bg-white transition-colors pr-10"
        />
        {searching && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-xs animate-pulse">
            …
          </span>
        )}
      </div>

      {/* URL / bare ID detected — show quick-queue row */}
      {isUrl && resolvedId && (
        <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2.5">
          <span className="text-sm text-zinc-700">
            Detected ArXiv ID: <span className="font-mono font-medium">{resolvedId}</span>
          </span>
          <QueueButton
            status={queueStatus[resolvedId]}
            onClick={() => queue(resolvedId)}
          />
        </div>
      )}

      {results.length > 0 && (
        <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200 overflow-hidden">
          {results.map((r) => {
            const status = queueStatus[r.arxiv_id];
            return (
              <li key={r.arxiv_id} className="p-3 flex items-start gap-3 hover:bg-zinc-50 transition-colors">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-zinc-900 line-clamp-2 leading-snug">
                    {r.title}
                  </p>
                  <div className="flex items-center gap-2 mt-1 text-xs text-zinc-400 flex-wrap">
                    <span className="font-mono">arXiv:{r.arxiv_id}</span>
                    {r.authors.length > 0 && (
                      <span>{r.authors.slice(0, 2).join(", ")}{r.authors.length > 2 ? " et al." : ""}</span>
                    )}
                    <span>{r.published}</span>
                  </div>
                </div>
                <QueueButton
                  status={status}
                  onClick={() => queue(r.arxiv_id, r.title)}
                />
              </li>
            );
          })}
        </ul>
      )}

      {!isUrl && query.trim().length >= 3 && !searching && results.length === 0 && (
        <p className="text-sm text-zinc-400 text-center py-3">No results from ArXiv.</p>
      )}

      {streaming.size > 0 && (
        <div className="space-y-1">
          {Array.from(streaming).map((id) => (
            <PaperStatusStream key={id} arxivId={id} />
          ))}
        </div>
      )}
    </div>
  );
}

function QueueButton({ status, onClick }: { status?: QueueStatus; onClick: () => void }) {
  if (status === "ok") {
    return (
      <span className="shrink-0 text-xs font-medium text-green-600 bg-green-50 px-2.5 py-1 rounded-lg">
        Queued ✓
      </span>
    );
  }
  if (status === "exists") {
    return (
      <span className="shrink-0 text-xs font-medium text-zinc-400 bg-zinc-100 px-2.5 py-1 rounded-lg">
        Already in DB
      </span>
    );
  }
  if (status === "error") {
    return (
      <button onClick={onClick} className="shrink-0 text-xs font-medium text-red-600 bg-red-50 px-2.5 py-1 rounded-lg hover:bg-red-100">
        Retry
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className="shrink-0 text-xs font-semibold text-white bg-zinc-900 px-2.5 py-1 rounded-lg hover:bg-zinc-700 transition-colors"
    >
      Queue
    </button>
  );
}

// ── Tab: paste arxiv ID ───────────────────────────────────────────────────────

function IdForm() {
  const [arxivId, setArxivId] = useState("");
  const [status, setStatus] = useState<QueueStatus>("idle");
  const [message, setMessage] = useState("");
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const raw = arxivId.trim();
    if (!raw) return;
    const id = extractArxivId(raw);
    if (!id) {
      setStatus("error");
      setMessage("Could not parse an ArXiv ID from that input.");
      return;
    }
    startTransition(async () => {
      try {
        const res = await fetch("/api/queue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ arxiv_id: id }),
        });
        const json = await res.json();
        if (!res.ok) { setStatus("error"); setMessage(json.error ?? "Unknown error"); }
        else if (json.existing) { setStatus("exists"); setMessage(`${id} is already queued.`); }
        else { setStatus("ok"); setMessage(""); setArxivId(""); setStreamingId(id); }
      } catch {
        setStatus("error");
        setMessage("Network error — try again.");
      }
    });
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-400">
        Paste an ArXiv ID or URL — e.g.{" "}
        <span className="font-mono">2301.07984</span>,{" "}
        <span className="font-mono">arxiv.org/abs/2301.07984</span>, or{" "}
        <span className="font-mono">alphaxiv.org/abs/2301.07984</span>.
      </p>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={arxivId}
          onChange={(e) => setArxivId(e.target.value)}
          placeholder="2301.07984 or arxiv.org/abs/2301.07984"
          className="flex-1 rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm font-mono placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent focus:bg-white transition-colors"
        />
        <button
          type="submit"
          disabled={isPending || !arxivId.trim()}
          className="rounded-lg bg-zinc-900 text-white px-4 py-2 text-sm font-semibold hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "…" : "Queue"}
        </button>
      </form>
      {status === "exists" && (
        <p className="text-xs font-medium px-3 py-2 rounded-lg bg-zinc-100 text-zinc-500">
          {message}
        </p>
      )}
      {status === "error" && (
        <p className="text-xs font-medium px-3 py-2 rounded-lg bg-red-50 text-red-600">
          {message}
        </p>
      )}
      {streamingId && <PaperStatusStream arxivId={streamingId} />}
    </div>
  );
}
