"use client";

import { useEffect, useRef } from "react";
import { prepareLatex, KATEX_OPTIONS } from "@/lib/katex-helpers";

// Matches display math: \[...\] or $$...$$ — must come before inline patterns
const DISPLAY_MATH_RE = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g;

// Matches inline math: $...$ (avoiding $$) or \(...\)
const INLINE_MATH_RE = /(?<!\$)\$(?!\$)((?:[^$\n]|\\.)+?)(?<!\$)\$(?!\$)|\\\(((?:[^\\]|\\.)+?)\\\)/g;

// Combined: display first so $$ isn't swallowed by the $ pattern
const ALL_MATH_RE = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|(?<!\$)\$(?!\$)((?:[^$\n]|\\.)+?)(?<!\$)\$(?!\$)|\\\(((?:[^\\]|\\.)+?)\\\)/g;

// Detects bare LaTeX subscript/superscript notation not wrapped in $...$
// e.g. σ_θ, u_{<i}, F_θ(q, u_{<i}), μ_θ
// Single-char subscripts require the subscript char NOT be followed by a word char
// (prevents matching n_gram → $n_g$ram false positives)
const BARE_LATEX_RE =
  /([a-zA-ZΑ-Ωα-ω]\w*(?:[_^]\{[^}\n]+\}|[_^][a-zA-ZΑ-Ωα-ω\d](?!\w))+(?:\((?:[^()]*|\{[^}]*\})*\))?)/g;

/**
 * Pre-process text to wrap bare LaTeX subscript/superscript notation in $...$.
 * Handles LLM output that writes math like σ_θ(q, u_{<i}) without delimiters.
 * Already-delimited math regions are left untouched.
 */
function autoWrapBareLatex(text: string): string {
  const parts: string[] = [];
  let last = 0;
  for (const m of text.matchAll(ALL_MATH_RE)) {
    // Wrap bare LaTeX in non-delimited regions
    parts.push(
      text.slice(last, m.index!).replace(BARE_LATEX_RE, "$$$1$$")
    );
    parts.push(m[0]); // already-delimited — keep as-is
    last = m.index! + m[0].length;
  }
  parts.push(text.slice(last).replace(BARE_LATEX_RE, "$$$1$$"));
  return parts.join("");
}

function MathChunk({ expr, display }: { expr: string; display: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const prepared = prepareLatex(expr, display);
    if (!prepared) return;
    import("katex").then(({ default: katex }) => {
      try {
        katex.render(prepared, ref.current!, {
          ...KATEX_OPTIONS,
          displayMode: display,
        });
      } catch {
        // leave as raw text on error
      }
    });
  }, [expr, display]);

  // Placeholder text until KaTeX hydrates
  return (
    <span
      ref={ref}
      className={display ? "block overflow-x-auto py-1 text-center" : "inline"}
    >
      {display ? `\\[${expr}\\]` : `$${expr}$`}
    </span>
  );
}

interface ProseWithMathProps {
  text: string;
  className?: string;
}

/**
 * Renders prose text, replacing inline $...$, \(...\) and display \[...\], $$...$$ with KaTeX.
 */
export function ProseWithMath({ text, className }: ProseWithMathProps) {
  type Part =
    | { type: "text"; content: string }
    | { type: "math"; content: string; display: boolean };

  const parts: Part[] = [];
  let last = 0;

  const processed = autoWrapBareLatex(text);

  for (const match of processed.matchAll(ALL_MATH_RE)) {
    if (match.index! > last) {
      parts.push({ type: "text", content: processed.slice(last, match.index) });
    }
    // Groups: 1=\[...\], 2=$$...$$, 3=$...$, 4=\(...\)
    const isDisplay = match[1] !== undefined || match[2] !== undefined;
    const expr = match[1] ?? match[2] ?? match[3] ?? match[4] ?? "";
    parts.push({ type: "math", content: expr, display: isDisplay });
    last = match.index! + match[0].length;
  }
  if (last < processed.length) {
    parts.push({ type: "text", content: processed.slice(last) });
  }

  return (
    <span className={className}>
      {parts.map((p, i) =>
        p.type === "math" ? (
          <MathChunk key={i} expr={p.content} display={p.display} />
        ) : (
          <span key={i}>{p.content}</span>
        )
      )}
    </span>
  );
}
