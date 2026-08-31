"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { prepareLatex, KATEX_OPTIONS } from "@/lib/katex-helpers";

// Math delimiters, display first so $$ is not swallowed by the $ pattern.
//
// NOTE: the inline-$ alternatives must stay disjoint. `[^$\n]` also matches a
// backslash, so `(?:[^$\n]|\\.)` gives the engine two ways to consume every
// escape sequence — on an unbalanced `$` that backtracks exponentially and
// freezes the tab. Excluding `\\` from the first branch keeps it linear.
// A `$` preceded by a backslash is an escaped literal, not an opener.
const MATH_SOURCE =
  String.raw`\\\[([\s\S]+?)\\\]` +
  String.raw`|\$\$([\s\S]+?)\$\$` +
  String.raw`|(?<![\\$])\$(?!\$)((?:[^$\n\\]|\\.)+?)\$(?!\$)` +
  String.raw`|\\\(((?:[^\\]|\\.)+?)\\\)`;

const ALL_MATH_RE = new RegExp(MATH_SOURCE, "g");

// Regions that must never be auto-wrapped: existing math, and `code spans`.
// Without the code-span branch, "`beta_1`" becomes "`$beta_1$`" and renders as
// math with two orphaned backticks around it.
const CODE_SPAN_SOURCE = "`[^`\\n]+`";
const PROTECTED_RE = new RegExp(CODE_SPAN_SOURCE + "|" + MATH_SOURCE, "g");

// Detects bare LaTeX subscript/superscript notation not wrapped in $...$
// e.g. σ_θ, u_{<i}, F_θ(q, u_{<i}), μ_θ
// Single-char subscripts require the subscript char NOT be followed by a word char
// (prevents matching n_gram → $n_g$ram false positives)
const BARE_LATEX_RE =
  /([a-zA-ZΑ-Ωα-ω]\w*(?:[_^]\{[^}\n]+\}|[_^][a-zA-ZΑ-Ωα-ω\d](?!\w))+(?:\((?:[^()]*|\{[^}]*\})*\))?)/g;

const PROSE_WORD_RE = /^[A-Za-z]{2,}$/;

/**
 * Is this `$…$` capture really math, or a pair of unrelated dollar signs?
 *
 * "It costs $5 today and $10 tomorrow" otherwise renders " today and " as a
 * formula. Explicit LaTeX markers always win; otherwise several plain words in
 * a row mean it is prose that happened to sit between two currency amounts.
 */
export function looksLikeMath(expr: string): boolean {
  if (/[\\_^{}]/.test(expr)) return true;
  const plainWords = expr.trim().split(/\s+/).filter((w) => PROSE_WORD_RE.test(w));
  return plainWords.length < 2;
}

/**
 * Pre-process text to wrap bare LaTeX subscript/superscript notation in $...$.
 * Handles LLM output that writes math like σ_θ(q, u_{<i}) without delimiters.
 * Already-delimited math and code spans are left untouched.
 */
export function autoWrapBareLatex(text: string): string {
  const parts: string[] = [];
  let last = 0;
  for (const m of text.matchAll(PROTECTED_RE)) {
    parts.push(text.slice(last, m.index!).replace(BARE_LATEX_RE, "$$$1$$"));
    parts.push(m[0]); // protected — keep as-is
    last = m.index! + m[0].length;
  }
  parts.push(text.slice(last).replace(BARE_LATEX_RE, "$$$1$$"));
  return parts.join("");
}

type Part =
  | { type: "text"; content: string }
  | { type: "math"; content: string; display: boolean };

/** Split prose into text and math parts. Exported for tests. */
export function splitMathParts(text: string): Part[] {
  const parts: Part[] = [];
  const processed = autoWrapBareLatex(text);
  let last = 0;

  const pushText = (content: string) => {
    const prev = parts[parts.length - 1];
    if (prev && prev.type === "text") prev.content += content;
    else parts.push({ type: "text", content });
  };

  for (const match of processed.matchAll(ALL_MATH_RE)) {
    if (match.index! > last) pushText(processed.slice(last, match.index));
    // Groups: 1=\[...\], 2=$$...$$, 3=$...$, 4=\(...\)
    const isDisplay = match[1] !== undefined || match[2] !== undefined;
    const expr = match[1] ?? match[2] ?? match[3] ?? match[4] ?? "";
    if (match[3] !== undefined && !looksLikeMath(expr)) {
      pushText(match[0]); // dollar signs that were never math — keep verbatim
    } else {
      parts.push({ type: "math", content: expr, display: isDisplay });
    }
    last = match.index! + match[0].length;
  }
  if (last < processed.length) pushText(processed.slice(last));
  return parts;
}

function MathChunk({ expr, display }: { expr: string; display: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [renderError, setRenderError] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    const prepared = prepareLatex(expr, display);
    if (!prepared) {
      setRenderError(true);
      return;
    }
    import("katex").then(({ default: katex }) => {
      try {
        katex.render(prepared, ref.current!, {
          ...KATEX_OPTIONS,
          displayMode: display,
        });
        setRenderError(false);
      } catch {
        setRenderError(true);
      }
    });
  }, [expr, display]);

  if (renderError) {
    return (
      <code className="text-sm text-zinc-600 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 rounded font-mono break-all">
        {expr}
      </code>
    );
  }

  // Empty span — no children so React never overwrites KaTeX's innerHTML on re-render
  return (
    <span
      ref={ref}
      className={display ? "block overflow-x-auto py-1 text-center" : "inline"}
    />
  );
}

// ---------------------------------------------------------------------------
// Inline markdown: **bold**, *italic*, `code`
// ---------------------------------------------------------------------------
const INLINE_MD_RE = /(\*\*(?:[^*]|\*(?!\*))+\*\*|\*(?:[^*\n])+\*|`[^`\n]+`)/g;

function parseInlineMarkdown(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE_MD_RE)) {
    if (m.index! > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={m.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(
        <code key={m.index} className="bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 rounded text-[0.85em] font-mono text-zinc-800 dark:text-zinc-200">
          {token.slice(1, -1)}
        </code>
      );
    } else {
      parts.push(<em key={m.index}>{token.slice(1, -1)}</em>);
    }
    last = m.index! + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  if (parts.length === 0) return text;
  if (parts.length === 1 && typeof parts[0] === "string") return parts[0];
  return <>{parts}</>;
}

interface ProseWithMathProps {
  text: string;
  className?: string;
}

/**
 * Renders prose text, replacing inline $...$, \(...\) and display \[...\], $$...$$ with KaTeX.
 */
export function ProseWithMath({ text, className }: ProseWithMathProps) {
  const parts = splitMathParts(text);

  return (
    <span className={className}>
      {parts.map((p, i) =>
        p.type === "math" ? (
          <MathChunk key={i} expr={p.content} display={p.display} />
        ) : (
          <span key={i}>{parseInlineMarkdown(p.content)}</span>
        )
      )}
    </span>
  );
}
