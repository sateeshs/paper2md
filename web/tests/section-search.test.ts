import { describe, expect, it } from "vitest";
import { parseSectionQuery, snippetAround, splitMatches } from "@/lib/section-search";

describe("parseSectionQuery", () => {
  it("splits a query into lower-cased terms", () => {
    expect(parseSectionQuery("  Reward   Model ")).toEqual(["reward", "model"]);
  });

  it("returns null for queries shorter than two characters", () => {
    expect(parseSectionQuery("a")).toBeNull();
    expect(parseSectionQuery("   ")).toBeNull();
    expect(parseSectionQuery(null)).toBeNull();
  });

  it("strips characters that would break a PostgREST or() filter", () => {
    // `,` `(` `)` delimit or() conditions; `%` `_` `*` are ilike wildcards.
    expect(parseSectionQuery('a,b) or(title.eq.x "%_*\\')).toEqual(["or", "title.eq.x"]);
  });

  it("drops one-character terms and caps the number of terms", () => {
    expect(parseSectionQuery("a policy b gradient c")).toEqual(["policy", "gradient"]);
    expect(parseSectionQuery("one two three four five six seven")).toHaveLength(5);
  });
});

describe("splitMatches", () => {
  it("marks every case-insensitive occurrence of every term", () => {
    expect(splitMatches("Policy gradient and policy", ["policy", "gradient"])).toEqual([
      { text: "Policy", match: true },
      { text: " ", match: false },
      { text: "gradient", match: true },
      { text: " and ", match: false },
      { text: "policy", match: true },
    ]);
  });

  it("treats regex metacharacters in terms literally", () => {
    expect(splitMatches("cost (a+b) here", ["(a+b)"])).toEqual([
      { text: "cost ", match: false },
      { text: "(a+b)", match: true },
      { text: " here", match: false },
    ]);
  });

  it("returns the text unmarked when there are no terms", () => {
    expect(splitMatches("plain", [])).toEqual([{ text: "plain", match: false }]);
  });
});

describe("snippetAround", () => {
  const text = `${"x".repeat(200)} the reward signal ${"y".repeat(200)}`;

  it("centres the snippet on the first match with ellipses", () => {
    const snippet = snippetAround(text, ["reward"], 20);
    expect(snippet.startsWith("…")).toBe(true);
    expect(snippet.endsWith("…")).toBe(true);
    expect(snippet).toContain("reward");
    expect(snippet.length).toBeLessThanOrEqual(2 + 20 * 2 + "reward".length);
  });

  it("falls back to the start of the text when only the title matched", () => {
    expect(snippetAround("Opening words of the body", ["absent"], 10)).toBe("Opening words of the…");
  });
});
