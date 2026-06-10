"use client";

import { useEffect, useRef, useState } from "react";
import type { MathBlock as MathBlockType } from "@/lib/supabase/types";
import { KATEX_OPTIONS, isDisplayMode, prepareLatex } from "@/lib/katex-helpers";
import { ProseWithMath } from "@/components/ProseWithMath";

interface MathBlockProps {
  block: MathBlockType;
}

export function MathBlock({ block }: MathBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState(false);
  const [showExplanation, setShowExplanation] = useState(false);

  const displayMode = isDisplayMode(block.env_type);
  const prepared = prepareLatex(block.latex_expr, displayMode);

  useEffect(() => {
    if (!prepared || !containerRef.current) return;

    import("katex").then(({ default: katex }) => {
      try {
        katex.render(prepared, containerRef.current!, {
          ...KATEX_OPTIONS,
          displayMode,
        });
        setRenderError(false);
      } catch {
        setRenderError(true);
      }
    });
  }, [prepared, displayMode]);

  // Expression is entirely commented-out or empty — nothing to render
  if (!prepared) return null;

  return (
    <div className="my-4 rounded-lg border border-zinc-200 dark:border-zinc-700 overflow-hidden">
      {/* Rendered math */}
      <div className="px-4 py-3 bg-zinc-50 dark:bg-zinc-900">
        {renderError ? (
          <code className="text-sm text-zinc-600 dark:text-zinc-400 break-all">
            {block.latex_expr}
          </code>
        ) : (
          <div
            ref={containerRef}
            className={displayMode ? "overflow-x-auto py-1" : "inline"}
          />
        )}
      </div>

      {/* Explanation toggle */}
      {block.explanation && (
        <>
          <div className="border-t border-zinc-200 dark:border-zinc-700">
            <button
              onClick={() => setShowExplanation((v) => !v)}
              className="w-full px-4 py-2 text-left text-sm text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors flex items-center gap-2"
            >
              <span>{showExplanation ? "▾" : "▸"}</span>
              <span>Explanation</span>
              {block.explanation_model && (
                <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">
                  {block.explanation_model}
                </span>
              )}
            </button>
          </div>

          {showExplanation && (
            <ExplanationPanel explanation={block.explanation} />
          )}
        </>
      )}
    </div>
  );
}

function ExplanationPanel({ explanation }: { explanation: string }) {
  // Explanation is a JSON string from DSPy structured output
  let parsed: Record<string, string> | null = null;
  try {
    parsed = JSON.parse(explanation);
  } catch {
    // plain text fallback
  }

  if (parsed) {
    return (
      <dl className="px-4 py-3 space-y-2 text-sm bg-white dark:bg-zinc-950">
        {parsed.what_it_computes && (
          <ExplanationRow label="What it computes" value={parsed.what_it_computes} />
        )}
        {parsed.symbol_meanings && (
          <ExplanationRow label="Symbols" value={parsed.symbol_meanings} />
        )}
        {parsed.derivation && (
          <ExplanationRow label="Derivation" value={parsed.derivation} />
        )}
        {parsed.intuition && (
          <ExplanationRow label="Intuition" value={parsed.intuition} />
        )}
        {parsed.paper_relevance && (
          <ExplanationRow label="Why it matters" value={parsed.paper_relevance} />
        )}
      </dl>
    );
  }

  return (
    <p className="px-4 py-3 text-sm text-zinc-700 dark:text-zinc-300 bg-white dark:bg-zinc-950">
      <ProseWithMath text={explanation} />
    </p>
  );
}

function ExplanationRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-0.5 text-zinc-700 dark:text-zinc-300 leading-relaxed">
        <ProseWithMath text={value} />
      </dd>
    </div>
  );
}
