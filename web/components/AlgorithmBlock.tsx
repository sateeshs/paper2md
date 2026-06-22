"use client";

import { useState } from "react";
import { ProseWithMath } from "@/components/ProseWithMath";
import type { AlgorithmBlock as AlgorithmBlockRow } from "@/lib/supabase/types";

export type { AlgorithmBlockRow };

interface AlgorithmExplanation {
  purpose?: string;
  inputs_outputs?: string;
  step_by_step?: string;
  complexity?: string;
  key_insight?: string;
  prerequisites?: string;
}

interface AlgorithmBlockProps {
  block: AlgorithmBlockRow;
}

export function AlgorithmBlock({ block }: AlgorithmBlockProps) {
  const [showExplanation, setShowExplanation] = useState(false);

  const explanation: AlgorithmExplanation | null = block.explanation
    ? (() => {
        try {
          return JSON.parse(block.explanation);
        } catch {
          return null;
        }
      })()
    : null;

  const pseudocode = block.pseudocode_text || block.raw_pseudocode;

  return (
    <div className="my-4 rounded-lg border border-zinc-200 dark:border-zinc-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-50 dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700">
        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {block.caption ? `Algorithm: ${block.caption}` : "Algorithm"}
        </span>
        {block.explanation_model && (
          <span className="text-xs text-zinc-400 dark:text-zinc-500 font-mono">
            {block.explanation_model}
          </span>
        )}
      </div>

      {/* Pseudocode body */}
      <div className="px-4 py-3 bg-white dark:bg-zinc-950">
        <pre className="font-mono text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap leading-relaxed overflow-x-auto">
          {pseudocode}
        </pre>
      </div>

      {/* Explanation toggle */}
      {explanation && (
        <div className="border-t border-zinc-200 dark:border-zinc-700">
          <button
            onClick={() => setShowExplanation((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors"
          >
            <span className="font-medium">
              {showExplanation ? "Hide explanation" : "Show explanation"}
            </span>
            <span className="text-zinc-400">{showExplanation ? "↑" : "↓"}</span>
          </button>

          {showExplanation && (
            <div className="px-4 py-4 space-y-4 bg-white dark:bg-zinc-950 border-t border-zinc-100 dark:border-zinc-800">
              <ExplanationField label="Purpose" value={explanation.purpose} />
              <ExplanationField label="Inputs / Outputs" value={explanation.inputs_outputs} />
              <ExplanationField label="Step-by-step" value={explanation.step_by_step} />
              <ExplanationField label="Complexity" value={explanation.complexity} />
              <ExplanationField label="Key Insight" value={explanation.key_insight} />
              <ExplanationField label="Prerequisites" value={explanation.prerequisites} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ExplanationField({
  label,
  value,
}: {
  label: string;
  value: string | undefined;
}) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-1">
        {label}
      </p>
      <div className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
        <ProseWithMath text={value} />
      </div>
    </div>
  );
}
