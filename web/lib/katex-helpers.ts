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
    "\\K": "\\mathbb{K}",
    // Bold math (\bm is from the bm package; KaTeX uses \boldsymbol)
    "\\bm": "\\boldsymbol",
    // Bold vectors: \Ba–\Bz, \BA–\BZ (common ML/math convention)
    ...Object.fromEntries(
      "abcdefghijklmnopqrstuvwxyz".split("").flatMap((c) => [
        [`\\B${c}`, `\\boldsymbol{${c}}`],
        [`\\B${c.toUpperCase()}`, `\\boldsymbol{${c.toUpperCase()}}`],
      ])
    ),
    "\\Bnul": "\\boldsymbol{0}",
    "\\Bone": "\\boldsymbol{1}",
    "\\Balpha": "\\boldsymbol{\\alpha}",
    "\\Bbeta": "\\boldsymbol{\\beta}",
    "\\Bgamma": "\\boldsymbol{\\gamma}",
    "\\Bdelta": "\\boldsymbol{\\delta}",
    "\\Bepsilon": "\\boldsymbol{\\epsilon}",
    "\\Bvarepsilon": "\\boldsymbol{\\varepsilon}",
    "\\Blambda": "\\boldsymbol{\\lambda}",
    "\\Bmu": "\\boldsymbol{\\mu}",
    "\\Bnu": "\\boldsymbol{\\nu}",
    "\\Bsigma": "\\boldsymbol{\\sigma}",
    "\\Btheta": "\\boldsymbol{\\theta}",
    "\\Bphi": "\\boldsymbol{\\phi}",
    "\\Bpsi": "\\boldsymbol{\\psi}",
    "\\Bomega": "\\boldsymbol{\\omega}",
    "\\BPhi": "\\boldsymbol{\\Phi}",
    "\\BSigma": "\\boldsymbol{\\Sigma}",
    // Mathbf vectors: \VA–\VZ (common ML textbook convention)
    ...Object.fromEntries(
      "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((c) => [
        `\\V${c}`, `\\mathbf{${c}}`,
      ])
    ),
    // Common ML / stats operators
    "\\argmin": "\\operatorname*{argmin}",
    "\\argmax": "\\operatorname*{argmax}",
    "\\tr": "\\operatorname{tr}",
    "\\KL": "\\operatorname{KL}",
    "\\diag": "\\operatorname{diag}",
    "\\softmax": "\\operatorname{softmax}",
    "\\sigmoid": "\\operatorname{sigmoid}",
    "\\rank": "\\operatorname{rank}",
    "\\sign": "\\operatorname{sign}",
    "\\Var": "\\operatorname{Var}",
    "\\Cov": "\\operatorname{Cov}",
    // Operators (common across ML/math papers)
    "\\co": "\\operatorname{co}",
    "\\aff": "\\operatorname{aff}",
    "\\itr": "\\operatorname{int}",
    "\\depth": "\\operatorname{depth}",
    "\\wdth": "\\operatorname{width}",
    "\\size": "\\operatorname{size}",
    "\\st": "\\operatorname{Star}",
    "\\ber": "\\mathrm{B}",
    "\\cc": "\\mathrm{cc}",
    // Common shorthand
    "\\eps": "\\varepsilon",
    "\\given": "\\mid",
    "\\norm": "\\left\\|#1\\right\\|",
    "\\abs": "\\left|#1\\right|",
    "\\set": "\\{#1\\,|\\,#2\\}",
    "\\setc": "\\left\\{#1\\,\\middle|\\,#2\\right\\}",
    "\\nId": "\\Phi^{\\mathrm{id}}_{#1}",
    "\\nmin": "\\Phi^{\\min}_{#1}",
    "\\nmax": "\\Phi^{\\max}_{#1}",
    "\\ntim": "\\Phi^{\\times}_{#1}",
    "\\bbE": "\\mathbb{E}",
    "\\bbP": "\\mathbb{P}",
    "\\bbR": "\\mathbb{R}",
    "\\CA": "\\mathcal{A}",
    "\\CB": "\\mathcal{B}",
    "\\CC": "\\mathcal{C}",
    "\\CD": "\\mathcal{D}",
    "\\CF": "\\mathcal{F}",
    "\\CG": "\\mathcal{G}",
    "\\CH": "\\mathcal{H}",
    "\\CL": "\\mathcal{L}",
    "\\CM": "\\mathcal{M}",
    "\\CN": "\\mathcal{N}",
    "\\CO": "\\mathcal{O}",
    "\\CP": "\\mathcal{P}",
    "\\CR": "\\mathcal{R}",
    "\\CS": "\\mathcal{S}",
    "\\CT": "\\mathcal{T}",
    "\\CX": "\\mathcal{X}",
    "\\CY": "\\mathcal{Y}",
    // Common paper-specific
    "\\objF": "F",
    "\\risk": "\\mathcal{R}",
    "\\dfn": "\\coloneqq",
    "\\dfnn": "=\\vcentcolon",
    "\\CV": "\\mathcal{V}",
    "\\dd": "\\,\\mathrm{d}",
    "\\ind": "\\mathbb{1}",
    "\\gauss": "\\mathrm{N}",
    "\\unif": "\\mathrm{U}",
    // Transformer / attention paper macros (Attention is All You Need)
    "\\dmodel": "d_{\\mathrm{model}}",
    "\\dk": "d_k",
    "\\dv": "d_v",
    "\\dff": "d_{\\mathrm{ff}}",
    "\\heads": "h",
    // \mR, \mC etc. (alternative number set notation)
    "\\mR": "\\mathbb{R}",
    "\\mC": "\\mathbb{C}",
    "\\mN": "\\mathbb{N}",
    "\\mZ": "\\mathbb{Z}",
    "\\mQ": "\\mathbb{Q}",
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

  // Unsupported packages: \xymatrix (XY-pic commutative diagrams)
  if (/\\xymatrix\b/.test(s)) {
    return "\\text{[diagram — xymatrix not supported by KaTeX]}";
  }

  // Strip LaTeX % comments (everything from % to end of line)
  s = s.replace(/%[^\r\n]*/g, "").replace(/\n{3,}/g, "\n\n").trim();

  // Strip \label{...} — KaTeX doesn't know this command
  s = s.replace(/\\label\{[^}]*\}/g, "");
  // Strip \nonumber
  s = s.replace(/\\nonumber/g, "");
  // \mbox → \text
  s = s.replace(/\\mbox\{([^}]*)\}/g, "\\text{$1}");

  // After all cleanup, return empty string if nothing meaningful remains
  // (e.g. an equation that was entirely commented out, or junk whitespace-only extractions)
  const bodyStripped = s
    .replace(/\\begin\{[^}]+\}/g, "")
    .replace(/\\end\{[^}]+\}/g, "")
    .replace(/\\\\/g, "")       // strip line breaks
    .replace(/[.\s,;]+/g, "")   // strip whitespace and punctuation-only residue
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
