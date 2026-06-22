"use client";

import { useEffect, useState } from "react";

interface PaperStatusStreamProps {
  arxivId: string;
}

type StreamStatus = "pending" | "processing" | "complete" | "error";

export function PaperStatusStream({ arxivId }: PaperStatusStreamProps) {
  const [status, setStatus] = useState<StreamStatus>("pending");
  const [title, setTitle] = useState<string | null>(null);

  useEffect(() => {
    const es = new EventSource(`/api/status/${arxivId}`);

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as { status: StreamStatus; title: string | null };
        setStatus(payload.status);
        if (payload.title && payload.title !== arxivId) {
          setTitle(payload.title);
        }
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => es.close();

    return () => es.close();
  }, [arxivId]);

  if (status === "complete") {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-700">
        <span>✓</span>
        <span>
          <span className="font-medium">Complete</span>
          {title && (
            <>
              {" — "}
              <a
                href={`/paper/${arxivId}`}
                className="underline underline-offset-2 hover:text-green-900"
              >
                {title}
              </a>
            </>
          )}
        </span>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600">
        <span>✗</span>
        <span>Processing failed for <span className="font-mono">{arxivId}</span></span>
      </div>
    );
  }

  // pending or processing
  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2.5 text-sm text-blue-600">
      <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-blue-300 border-t-blue-600 rounded-full shrink-0" />
      <span>
        {status === "processing" ? (
          <>Processing <span className="font-mono">{arxivId}</span>…</>
        ) : (
          <>Queued — worker runs every 30 min, check back soon.</>
        )}
      </span>
    </div>
  );
}
