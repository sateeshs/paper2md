"use client";

import { useState } from "react";

interface PdfViewerProps {
  arxivId: string;
}

export function PdfViewer({ arxivId }: PdfViewerProps) {
  const [open, setOpen] = useState(true);

  const pdfUrl = `https://arxiv.org/pdf/${arxivId}`;
  const proxyUrl = `/api/pdf/${arxivId}`;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 shrink-0">
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 truncate">
          arXiv:{arxivId} — original PDF
        </span>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <a
            href={pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            title="Open in new tab"
          >
            ↗
          </a>
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            title={open ? "Hide PDF" : "Show PDF"}
          >
            {open ? "✕" : "PDF"}
          </button>
        </div>
      </div>

      {/* PDF iframe */}
      {open && (
        <iframe
          src={proxyUrl}
          className="flex-1 w-full border-0 min-h-0"
          title={`arXiv:${arxivId} PDF`}
        />
      )}
    </div>
  );
}
