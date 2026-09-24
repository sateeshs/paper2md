import { describe, expect, it } from "vitest";
import katex from "katex";
import { readFileSync } from "node:fs";
import { KATEX_OPTIONS, isDisplayMode, prepareLatex } from "@/lib/katex-helpers";

/**
 * End-to-end guard: 400 real math blocks parsed out of arXiv 2310.20360
 * (Mathematical Introduction to Deep Learning), the paper whose formulas were
 * rendering as raw macro names.
 *
 * Regenerate with:
 *   python3 -c "import sys,json,random; sys.path.insert(0,'.'); \
 *     from lib.arxiv_source import fetch_arxiv_latex_full, split_preamble; \
 *     from lib.latex_parse import parse_latex_sections; \
 *     b,f=fetch_arxiv_latex_full('2310.20360'); \
 *     s=parse_latex_sections(b, split_preamble(f)); \
 *     bl=[{'env_type':m.env_type,'latex_expr':m.latex_expr} for x in s for m in x.math_blocks]; \
 *     random.Random(0).shuffle(bl); \
 *     json.dump({'arxiv_id':'2310.20360','blocks':bl[:400]}, open('web/tests/fixtures/math-blocks-2310.20360.json','w'), indent=1)"
 *
 * Measured rates on this fixture:
 *   52.5%  blocks as stored by the pre-fix pipeline
 *   94.3%  after preamble macro expansion + the frontend fixes
 */
const MIN_RENDER_RATE = 0.92;

type Block = { env_type: string; latex_expr: string };

const { blocks } = JSON.parse(
  readFileSync(new URL("./fixtures/math-blocks-2310.20360.json", import.meta.url), "utf8")
) as { blocks: Block[] };

function render(block: Block): string | null {
  const displayMode = isDisplayMode(block.env_type);
  const prepared = prepareLatex(block.latex_expr, displayMode);
  if (!prepared) return "empty";
  try {
    katex.renderToString(prepared, { ...KATEX_OPTIONS, displayMode, throwOnError: true });
    return null;
  } catch (e) {
    return String((e as Error).message);
  }
}

describe("KaTeX rendering of real parsed math blocks", () => {
  it("has a fixture to check", () => {
    expect(blocks.length).toBeGreaterThan(300);
  });

  it(`renders at least ${MIN_RENDER_RATE * 100}% of blocks`, () => {
    const failures = blocks
      .map((b) => ({ block: b, error: render(b) }))
      .filter((r) => r.error !== null);

    const rate = (blocks.length - failures.length) / blocks.length;
    if (rate < MIN_RENDER_RATE) {
      const sample = failures
        .slice(0, 10)
        .map((f) => `  ${f.error}\n    ${f.block.latex_expr.slice(0, 120)}`)
        .join("\n");
      throw new Error(
        `render rate ${(rate * 100).toFixed(1)}% below ${MIN_RENDER_RATE * 100}% ` +
          `(${failures.length}/${blocks.length} failed)\n${sample}`
      );
    }
    expect(rate).toBeGreaterThanOrEqual(MIN_RENDER_RATE);
  });

  it("never leaves an unexpanded paper macro in a block", () => {
    // These are the paper's own \newcommand shorthands. Any occurrence means
    // preamble macro expansion regressed.
    const LEAKED = /\\(altpoint|targetFunction|Aff|defaultParamDim|providecommandordefault)\b/;
    const leaked = blocks.filter((b) => LEAKED.test(b.latex_expr));
    expect(leaked.map((b) => b.latex_expr.slice(0, 80))).toEqual([]);
  });

  it("produces no block that is only a macro definition", () => {
    const defs = blocks.filter((b) => /^\s*\\(new|renew|provide)command/.test(b.latex_expr));
    expect(defs.map((b) => b.latex_expr.slice(0, 80))).toEqual([]);
  });
});
