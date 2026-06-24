/**
 * KaTeX rendering helpers.
 *
 * KaTeX itself is imported only in Client Components (browser-only).
 * This module provides the options config used across all render calls.
 */

import type { KatexOptions } from "katex";

export const KATEX_OPTIONS: KatexOptions = {
  throwOnError: false,
  displayMode: false,       // caller sets per-block
  trust: false,
  strict: "ignore",
  errorColor: "currentColor", // unknown macros render in normal text color, not red
  macros: {
    // Number sets
    "\\R": "\\mathbb{R}",
    "\\N": "\\mathbb{N}",
    "\\Z": "\\mathbb{Z}",
    "\\E": "\\mathbb{E}",
    "\\P": "\\mathbb{P}",
    "\\C": "\\mathbb{C}",
    "\\Q": "\\mathbb{Q}",
    // Bold math (\bm is from the bm package; KaTeX uses \boldsymbol)
    "\\bm": "\\boldsymbol",
    // Common ML / stats operators
    "\\argmin": "\\operatorname*{argmin}",
    "\\argmax": "\\operatorname*{argmax}",
    "\\tr": "\\operatorname{tr}",
    "\\KL": "\\operatorname{KL}",
    "\\diag": "\\operatorname{diag}",
    "\\softmax": "\\operatorname{softmax}",
    "\\sigmoid": "\\operatorname{sigmoid}",
    // Misc
    "\\given": "\\mid",
    // Transformer / attention paper macros (Attention is All You Need)
    "\\dmodel": "d_{\\mathrm{model}}",
    "\\dk": "d_k",
    "\\dv": "d_v",
    "\\dff": "d_{\\mathrm{ff}}",
    "\\heads": "h",
  },
};

/**
 * Env types that should render in display (block) mode.
 *
 * NOTE: Python's latex_parse.py strips the "*" suffix before storing
 * (e.g. "equation*" → "equation"), so starred variants never appear in the DB.
 * The set below matches what is actually stored.
 */
export const DISPLAY_ENV_TYPES = new Set([
  "equation",
  "align",
  "gather",
  "multline",
  "eqnarray",
  "cases",
  "display",      // $$...$$ and \[...\] blocks
  // Previously missing — Python extracts these but frontend was silently dropping them:
  "split",        // \begin{split} (always inside another display env)
  "subequations", // \begin{subequations} wrapper
  "flalign",      // \begin{flalign}
  "alignat",      // \begin{alignat}{n}
]);

export function isDisplayMode(envType: string): boolean {
  return DISPLAY_ENV_TYPES.has(envType);
}

/**
 * Prepare a latex_expr for katex.render().
 * Strips delimiters and fixes environments that KaTeX can't handle as top-level.
 */
export function prepareLatex(expr: string, displayMode: boolean): string {
  let s = stripDelimiters(expr);

  if (displayMode) {
    // \begin{split} must be inside an outer environment — wrap in align
    if (/^\\begin\{split\}/.test(s)) {
      s = `\\begin{aligned}${s.replace(/^\\begin\{split\}/, "").replace(/\\end\{split\}$/, "")}\\end{aligned}`;
    }
    // \begin{subequations} is not supported — strip the wrapper
    s = s
      .replace(/^\\begin\{subequations\}/, "")
      .replace(/\\end\{subequations\}$/, "")
      .trim();
    // eqnarray / eqnarray* are not supported by KaTeX — rewrite to align / align*
    s = s
      .replace(/\\begin\{eqnarray\*\}/g, "\\begin{align*}")
      .replace(/\\end\{eqnarray\*\}/g,   "\\end{align*}")
      .replace(/\\begin\{eqnarray\}/g,   "\\begin{align}")
      .replace(/\\end\{eqnarray\}/g,     "\\end{align}");
  }

  // Strip LaTeX % comments (everything from % to end of line)
  s = s.replace(/%[^\r\n]*/g, "").replace(/\n{3,}/g, "\n\n").trim();

  // Strip \label{...} — KaTeX doesn't know this command
  s = s.replace(/\\label\{[^}]*\}/g, "");
  // Strip \nonumber
  s = s.replace(/\\nonumber/g, "");
  // \mbox → \text
  s = s.replace(/\\mbox\{([^}]*)\}/g, "\\text{$1}");

  // After all cleanup, return empty string if nothing remains
  // (e.g. an equation that was entirely commented out)
  const bodyStripped = s
    .replace(/\\begin\{[^}]+\}/g, "")
    .replace(/\\end\{[^}]+\}/g, "")
    .trim();
  if (!bodyStripped) return "";

  return s;
}

/**
 * Strip LaTeX math delimiters before passing to katex.render().
 * KaTeX render() takes the expression only — no $, $$, \[, \] wrappers.
 */
export function stripDelimiters(expr: string): string {
  const s = expr.trim();
  // $$ ... $$ or \[ ... \]
  if ((s.startsWith("$$") && s.endsWith("$$")) || (s.startsWith("\\[") && s.endsWith("\\]"))) {
    return s.slice(2, -2).trim();
  }
  // $ ... $
  if (s.startsWith("$") && s.endsWith("$") && s.length > 1) {
    return s.slice(1, -1).trim();
  }
  // \( ... \)
  if (s.startsWith("\\(") && s.endsWith("\\)")) {
    return s.slice(2, -2).trim();
  }
  return s;
}
