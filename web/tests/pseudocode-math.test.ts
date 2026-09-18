import { describe, expect, it } from "vitest";
import katex from "katex";
import { splitMathParts } from "@/components/ProseWithMath";
import { prepareLatex, KATEX_OPTIONS } from "@/lib/katex-helpers";

/**
 * Pseudocode as it now leaves `_pseudocode_to_text()` in lib/latex_parse.py.
 * Before that fix every symbol was stripped and these lines arrived as
 * "$ _0  0$" — nothing to render and nothing to read.
 */
const PSEUDOCODE = [
  String.raw`Require: learning rate $\eta > 0$, dataset $\mathcal{D}$`,
  String.raw`Initialize $\hat{\theta}_0 \leftarrow 0$`,
  String.raw`for $t = 1$ to $T$`,
  String.raw`    $g_t \gets \nabla_\theta L(\theta_{t-1})$   // stochastic gradient`,
  String.raw`    $\theta_t \leftarrow \theta_{t-1} + \eta g_t$`,
  "end for",
  String.raw`return $\hat{\theta}_T$`,
].join("\n");

const mathParts = (line: string) =>
  splitMathParts(line).filter((p) => p.type === "math");

describe("pseudocode math rendering", () => {
  it("every math span in the pseudocode renders in KaTeX", () => {
    const failures: string[] = [];
    for (const line of PSEUDOCODE.split("\n")) {
      for (const part of mathParts(line)) {
        const prepared = prepareLatex(part.content, false);
        try {
          katex.renderToString(prepared, { ...KATEX_OPTIONS, displayMode: false, throwOnError: true });
        } catch (e) {
          failures.push(`${part.content} -> ${(e as Error).message}`);
        }
      }
    }
    expect(failures).toEqual([]);
  });

  it("extracts the symbols that the old stripper deleted", () => {
    const all = PSEUDOCODE.split("\n").flatMap(mathParts).map((p) => p.content).join(" ");
    for (const symbol of ["\\theta", "\\eta", "\\gets", "\\nabla", "\\hat"]) {
      expect(all).toContain(symbol);
    }
  });

  it("keeps comments and keywords out of the math parts", () => {
    const line = String.raw`    $g_t \gets \nabla_\theta L(\theta_{t-1})$   // stochastic gradient`;
    const text = splitMathParts(line)
      .filter((p) => p.type === "text")
      .map((p) => p.content)
      .join("");
    expect(text).toContain("// stochastic gradient");
    expect(text).not.toContain("\\gets");
  });

  it("preserves leading indentation as text, not markup", () => {
    const line = String.raw`    $\theta_t \leftarrow \theta_{t-1}$`;
    const parts = splitMathParts(line);
    expect(parts[0].type).toBe("text");
    expect(parts[0].content.startsWith("    ")).toBe(true);
  });
});
