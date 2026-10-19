import { describe, expect, it } from "vitest";
import { isViewableStatus } from "@/lib/paper-status";

describe("isViewableStatus", () => {
  it("treats complete and explaining papers as readable", () => {
    expect(isViewableStatus("complete")).toBe(true);
    expect(isViewableStatus("explaining")).toBe(true);
  });

  it("hides papers that are not stored yet or failed", () => {
    for (const status of ["pending", "processing", "error", "", null, undefined]) {
      expect(isViewableStatus(status)).toBe(false);
    }
  });
});
