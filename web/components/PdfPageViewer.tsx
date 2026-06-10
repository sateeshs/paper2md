"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getPdfDocument } from "@/lib/pdf-doc";

interface PdfPageViewerProps {
  arxivId: string;
  /** 1-based page to display. Changing this prop navigates without reload. */
  targetPage?: number;
}

export function PdfPageViewer({ arxivId, targetPage }: PdfPageViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const [currentPage, setCurrentPage] = useState(targetPage ?? 1);
  const [totalPages, setTotalPages] = useState(0);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");

  const pdfUrl = `https://arxiv.org/pdf/${arxivId}`;

  // Cancel in-flight renders on unmount
  useEffect(() => {
    return () => { renderTaskRef.current?.cancel(); };
  }, []);

  // Load PDF document once
  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");

    getPdfDocument(arxivId)
      .then((doc) => {
        if (!cancelled) {
          setTotalPages(doc.numPages);
          setLoadState("ready");
        }
      })
      .catch(() => {
        if (!cancelled) setLoadState("error");
      });

    return () => { cancelled = true; };
  }, [arxivId]);

  // Render the current page whenever page or load state changes
  const renderPage = useCallback(async (pageNum: number) => {
    if (loadState !== "ready") return;
    if (!canvasRef.current || !containerRef.current) return;

    // Cancel any in-flight render
    renderTaskRef.current?.cancel();

    const doc = await getPdfDocument(arxivId);
    const page = await doc.getPage(pageNum);
    const containerWidth = containerRef.current.clientWidth || 600;
    const scale = containerWidth / page.getViewport({ scale: 1 }).width;
    const viewport = page.getViewport({ scale });

    const canvas = canvasRef.current;
    canvas.width = viewport.width;
    canvas.height = viewport.height;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const task = page.render({ canvasContext: ctx, viewport, canvas });
    renderTaskRef.current = task;

    try {
      await task.promise;
    } catch {
      // cancelled — ignore
    }
  }, [arxivId, loadState]);

  useEffect(() => {
    renderPage(currentPage);
  }, [currentPage, renderPage]);

  // Sync prop changes to state
  useEffect(() => {
    if (targetPage && targetPage >= 1) {
      setCurrentPage(targetPage);
    }
  }, [targetPage]);

  const goTo = (page: number) => {
    const clamped = Math.max(1, Math.min(totalPages, page));
    setCurrentPage(clamped);
  };

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-zinc-100 dark:bg-zinc-900">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-zinc-50 dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700 shrink-0 text-xs">
        <span className="text-zinc-500 dark:text-zinc-400 truncate flex-1">
          arXiv:{arxivId}
        </span>
        {loadState === "ready" && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => goTo(currentPage - 1)}
              disabled={currentPage <= 1}
              className="px-1.5 py-0.5 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-30 transition-colors"
            >
              ‹
            </button>
            <span className="text-zinc-500 tabular-nums">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => goTo(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="px-1.5 py-0.5 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-30 transition-colors"
            >
              ›
            </button>
          </div>
        )}
        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 shrink-0 ml-1"
          title="Open original PDF"
        >
          ↗
        </a>
      </div>

      {/* Canvas area */}
      <div ref={containerRef} className="flex-1 overflow-y-auto overflow-x-auto bg-zinc-200 dark:bg-zinc-800 p-2">
        {loadState === "loading" && (
          <div className="flex items-center justify-center h-full text-sm text-zinc-400">
            Loading PDF…
          </div>
        )}
        {loadState === "error" && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-sm text-zinc-400">
            <span>Could not load PDF.</span>
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:underline"
            >
              Open on arXiv ↗
            </a>
          </div>
        )}
        {loadState === "ready" && (
          <canvas
            ref={canvasRef}
            className="mx-auto shadow-md bg-white block"
            style={{ maxWidth: "100%" }}
          />
        )}
      </div>
    </div>
  );
}
