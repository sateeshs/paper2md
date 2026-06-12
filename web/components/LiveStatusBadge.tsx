"use client";

import { useEffect, useState } from "react";

interface LiveStatusBadgeProps {
  arxivId: string;
  initialStatus: string;
}

const BADGE_CLASS: Record<string, string> = {
  pending:    "bg-amber-50 text-amber-600",
  processing: "bg-blue-50 text-blue-600",
  complete:   "bg-green-50 text-green-700",
  error:      "bg-red-50 text-red-600",
};

export function LiveStatusBadge({ arxivId, initialStatus }: LiveStatusBadgeProps) {
  const [status, setStatus] = useState(initialStatus);
  const [title, setTitle] = useState<string | null>(null);

  useEffect(() => {
    // Only stream for non-terminal statuses
    if (status === "complete" || status === "error") return;

    const es = new EventSource(`/api/status/${arxivId}`);
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as { status: string; title: string | null };
        setStatus(payload.status);
        if (payload.title && payload.title !== arxivId) setTitle(payload.title);
      } catch { /* ignore */ }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [arxivId, status]);

  const isLive = status !== "complete" && status !== "error";

  return (
    <span className={`inline-flex items-center gap-1.5 shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${BADGE_CLASS[status] ?? "bg-zinc-100 text-zinc-500"}`}>
      {isLive && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {status === "complete" && title ? (
        <a href={`/paper/${arxivId}`} className="underline underline-offset-2">
          {title}
        </a>
      ) : status}
    </span>
  );
}
