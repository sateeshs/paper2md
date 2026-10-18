"use client";

import { splitMathParts, MathChunk } from "@/components/ProseWithMath";

interface PseudocodeBlockProps {
  code: string;
}

/**
 * Renders algorithm pseudocode in monospace with indentation preserved, and
 * inline `$...$` spans typeset by KaTeX rather than shown as raw LaTeX.
 *
 * Math inside pseudocode is always set inline — a centered display block would
 * break the line-by-line reading that makes pseudocode legible.
 */
export function PseudocodeBlock({ code }: PseudocodeBlockProps) {
  const lines = code.split("\n");

  return (
    <div className="font-mono text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed overflow-x-auto">
      {lines.map((line, i) => (
        <PseudocodeLine key={i} line={line} />
      ))}
    </div>
  );
}

function PseudocodeLine({ line }: { line: string }) {
  // A blank line is vertical rhythm in pseudocode — keep it, but an empty
  // element collapses, so give it an explicit height.
  if (!line.trim()) return <div className="h-4" />;

  const parts = splitMathParts(line);

  return (
    <div className="whitespace-pre-wrap">
      {parts.map((part, i) =>
        part.type === "math" ? (
          <MathChunk key={i} expr={part.content} display={false} />
        ) : (
          <span key={i}>{part.content}</span>
        )
      )}
    </div>
  );
}
