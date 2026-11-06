import { describe, expect, it } from "vitest";
import { pickMatches } from "@/lib/search-match";

describe("pickMatches", () => {
  it("puts the entries the query matched first, case-insensitively", () => {
    const affils = ["MIT", "Google DeepMind, London", "Oxford"];
    expect(pickMatches(affils, "google deepmind", 2)).toEqual(["Google DeepMind, London", "MIT"]);
  });

  it("falls back to the first entries when nothing matches", () => {
    expect(pickMatches(["A", "B", "C"], "zzz", 2)).toEqual(["A", "B"]);
  });

  it("treats a missing list as empty", () => {
    expect(pickMatches(null, "x", 2)).toEqual([]);
  });
});
