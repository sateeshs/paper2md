import { describe, expect, it } from "vitest";
import { autoWrapBareLatex, looksLikeMath, splitMathParts } from "@/components/ProseWithMath";

const math = (text: string) =>
  splitMathParts(text).filter((p) => p.type === "math").map((p) => p.content);
const plain = (text: string) =>
  splitMathParts(text).filter((p) => p.type === "text").map((p) => p.content).join("");

describe("code spans", () => {
  it("does not auto-wrap identifiers inside backticks", () => {
    expect(autoWrapBareLatex("The variable `beta_1` is the slope.")).toBe(
      "The variable `beta_1` is the slope."
    );
  });

  it("leaves a code span intact when splitting", () => {
    expect(math("Use `x_i` in numpy and $y_i$ in math.")).toEqual(["y_i"]);
    expect(plain("Use `x_i` in numpy and $y_i$ in math.")).toContain("`x_i`");
  });

  it("still wraps bare notation outside code spans", () => {
    expect(autoWrapBareLatex("compare `a_1` with b_2")).toBe("compare `a_1` with $b_2$");
  });
});

describe("dollar signs that are not math", () => {
  it("does not turn currency amounts into a formula", () => {
    expect(math("It costs $5 today and $10 tomorrow.")).toEqual([]);
    expect(plain("It costs $5 today and $10 tomorrow.")).toBe(
      "It costs $5 today and $10 tomorrow."
    );
  });

  it("ignores an escaped dollar as an opener", () => {
    expect(math("A price of \\$5 and a value $x_1$.")).toEqual(["x_1"]);
  });

  it("keeps genuine short math", () => {
    expect(math("Let $x = 1$ hold.")).toEqual(["x = 1"]);
  });
});

describe("looksLikeMath", () => {
  it.each(["x_1", "\\alpha", "a^{2}", "x = 1", "\\frac{a}{b}"])("accepts %s", (s) =>
    expect(looksLikeMath(s)).toBe(true)
  );

  it.each([" today and ", "the loss function", "per unit for "])("rejects %s", (s) =>
    expect(looksLikeMath(s)).toBe(false)
  );
});

describe("delimiter handling", () => {
  it("splits display and inline math", () => {
    expect(math("before \\[a = b\\] middle $c$ after")).toEqual(["a = b", "c"]);
  });

  it("marks display math as display", () => {
    const parts = splitMathParts("x $$a = b$$ y");
    expect(parts.find((p) => p.type === "math")).toMatchObject({ display: true });
  });

  it("marks inline math as inline", () => {
    const parts = splitMathParts("x $a = b$ y");
    expect(parts.find((p) => p.type === "math")).toMatchObject({ display: false });
  });

  it("handles \\(...\\)", () => {
    expect(math("value \\(z_1\\) here")).toEqual(["z_1"]);
  });

  it("does not let $$ be swallowed by the single-$ pattern", () => {
    expect(math("$$\\alpha$$")).toEqual(["\\alpha"]);
  });
});

describe("bare LaTeX auto-wrapping", () => {
  it("wraps subscripted symbols written without delimiters", () => {
    expect(math("the value σ_θ matters")).toEqual(["σ_θ"]);
  });

  it("does not split snake_case identifiers", () => {
    expect(math("set max_length now")).toEqual([]);
  });

  it("leaves already-delimited math alone", () => {
    expect(autoWrapBareLatex("$x_1$")).toBe("$x_1$");
  });
});

describe("performance", () => {
  // `[^$\n]` also matches a backslash, so `(?:[^$\n]|\\.)` gave the engine two
  // ways to consume every escape — an unbalanced `$` then froze the tab.
  it("does not backtrack exponentially on an unbalanced dollar", () => {
    const pathological = "cost $" + "\\mathbb{N} \\gamma \\in ".repeat(40);
    const start = performance.now();
    splitMathParts(pathological);
    expect(performance.now() - start).toBeLessThan(500);
  });
});
