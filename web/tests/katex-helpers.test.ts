import { describe, expect, it } from "vitest";
import { isDisplayMode, prepareLatex, stripDelimiters } from "@/lib/katex-helpers";

describe("stripDelimiters", () => {
  it.each([
    ["$x$", "x"],
    ["$$x$$", "x"],
    ["\\[x\\]", "x"],
    ["\\(x\\)", "x"],
    ["x", "x"],
  ])("unwraps %s", (input, expected) => {
    expect(stripDelimiters(input)).toBe(expected);
  });
});

describe("prepareLatex — single-letter commands", () => {
  // These are real LaTeX commands. The rewrite that resolved paper shorthands
  // used to mangle every one of them (\v{s} → {v}{s}, \c{c} → {c}{c}, …).
  it.each([
    ["\\v{s}", "caron accent"],
    ["\\c{c}", "cedilla"],
    ["\\u{a}", "breve"],
    ["\\t{oo}", "tie accent"],
    ["\\r{a}", "ring accent"],
    ["\\H{o}", "double acute"],
    ["\\k{a}", "ogonek"],
    ["\\b{x}", "bar-under"],
    ["\\d{x}", "dot-under"],
    ["\\hat{\\i}", "dotless i"],
    ["\\j", "dotless j"],
    ["\\o", "slashed o"],
    ["\\O", "slashed O"],
    ["\\l", "l with stroke"],
    ["\\L", "L with stroke"],
    ["\\S", "section sign"],
    ["\\P", "pilcrow"],
  ])("preserves %s (%s)", (input) => {
    expect(prepareLatex(input, false)).toBe(input);
  });

  it("still resolves non-reserved shorthands from legacy rows", () => {
    expect(prepareLatex("\\w + \\Y", false)).toBe("{w} + {Y}");
  });

  it("braces the resolved letter so a preceding command cannot merge", () => {
    // \top\w must not become \topw
    expect(prepareLatex("\\top\\w", false)).toBe("\\top{w}");
  });

  it("leaves multi-letter commands untouched", () => {
    expect(prepareLatex("\\alpha + \\Lambda", false)).toBe("\\alpha + \\Lambda");
  });

  it("keeps number-set macros resolvable by KaTeX", () => {
    expect(prepareLatex("\\R^d", false)).toBe("\\R^d");
  });
});

describe("prepareLatex — environment rewriting", () => {
  it("rewrites eqnarray to align", () => {
    const out = prepareLatex("\\begin{eqnarray}a &=& b\\end{eqnarray}", true);
    expect(out).toContain("\\begin{align}");
    expect(out).not.toContain("eqnarray");
  });

  it("rewrites multline to gather", () => {
    const out = prepareLatex("\\begin{multline}a \\\\ b\\end{multline}", true);
    expect(out).toContain("\\begin{gather}");
    expect(out).not.toContain("multline");
  });

  it("rewrites multline* to gather*", () => {
    const out = prepareLatex("\\begin{multline*}a\\end{multline*}", true);
    expect(out).toContain("\\begin{gather*}");
  });

  it("rewrites mathtools multlined to gathered", () => {
    const out = prepareLatex("\\begin{equation}\\begin{multlined}a\\\\b\\end{multlined}\\end{equation}", true);
    expect(out).toContain("\\begin{gathered}");
    expect(out).not.toContain("multlined");
  });

  it("wraps a bare split in aligned", () => {
    const out = prepareLatex("\\begin{split}a &= b\\end{split}", true);
    expect(out).toContain("\\begin{aligned}");
  });

  it("strips the subequations wrapper", () => {
    const out = prepareLatex("\\begin{subequations}x = 1\\end{subequations}", true);
    expect(out).not.toContain("subequations");
  });

  it("replaces xymatrix diagrams with a placeholder", () => {
    expect(prepareLatex("\\xymatrix{A \\ar[r] & B}", true)).toContain("\\text{");
  });
});

describe("prepareLatex — cleanup", () => {
  it("strips labels, \\nonumber and comments", () => {
    const out = prepareLatex("x = 1 \\label{eq:a} \\nonumber % trailing", true);
    expect(out).not.toMatch(/\\label|\\nonumber|%/);
  });

  it("strips package setup commands that typeset nothing", () => {
    const out = prepareLatex("\\mathtoolsset{showonlyrefs}x = 1", true);
    expect(out).toBe("x = 1");
  });

  it("returns empty string when nothing meaningful survives", () => {
    expect(prepareLatex("\\begin{equation}% all commented\\end{equation}", true)).toBe("");
  });

  it("converts \\mbox to \\text", () => {
    expect(prepareLatex("\\mbox{hi}", false)).toBe("\\text{hi}");
  });
});

describe("isDisplayMode", () => {
  it.each(["equation", "align", "gather", "split", "flalign", "alignat", "display"])(
    "treats %s as display",
    (env) => expect(isDisplayMode(env)).toBe(true)
  );

  it("treats inline as inline", () => {
    expect(isDisplayMode("inline")).toBe(false);
  });
});
