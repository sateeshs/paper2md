import { describe, expect, it } from "vitest";
import { parseProseBlocks } from "@/lib/prose-blocks";

describe("parseProseBlocks", () => {
  it("returns nothing for blank input", () => {
    expect(parseProseBlocks("")).toEqual([]);
    expect(parseProseBlocks("   \n\n  ")).toEqual([]);
  });

  it("keeps a single line as one paragraph", () => {
    expect(parseProseBlocks("The state $u$ evolves in time.")).toEqual([
      { type: "paragraph", text: "The state $u$ evolves in time." },
    ]);
  });

  it("splits paragraphs on blank lines", () => {
    const blocks = parseProseBlocks("First para.\n\nSecond para.");
    expect(blocks).toEqual([
      { type: "paragraph", text: "First para." },
      { type: "paragraph", text: "Second para." },
    ]);
  });

  it("joins soft-wrapped lines of one paragraph with a space", () => {
    expect(parseProseBlocks("A sentence that was\nhard wrapped.")).toEqual([
      { type: "paragraph", text: "A sentence that was hard wrapped." },
    ]);
  });

  // The reported defect: a symbol list written as consecutive "- " lines used
  // to collapse into a single run-on paragraph.
  it("turns consecutive dash lines into a bullet list", () => {
    const blocks = parseProseBlocks(
      "- $u$: the state function.\n- $u_t$: its time derivative.\n- $T$: the terminal time."
    );
    expect(blocks).toEqual([
      {
        type: "list",
        ordered: false,
        items: [
          "$u$: the state function.",
          "$u_t$: its time derivative.",
          "$T$: the terminal time.",
        ],
      },
    ]);
  });

  it("keeps a lead-in sentence separate from the bullets that follow it", () => {
    const blocks = parseProseBlocks("The symbols are:\n- $a$: first.\n- $b$: second.");
    expect(blocks).toEqual([
      { type: "paragraph", text: "The symbols are:" },
      { type: "list", ordered: false, items: ["$a$: first.", "$b$: second."] },
    ]);
  });

  it("attaches an indented continuation line to the bullet above it", () => {
    const blocks = parseProseBlocks(
      "- $y$: the model output.\n  Here it is the generated response.\n- $q$: the question."
    );
    expect(blocks).toEqual([
      {
        type: "list",
        ordered: false,
        items: [
          "$y$: the model output. Here it is the generated response.",
          "$q$: the question.",
        ],
      },
    ]);
  });

  it("recognises numbered lists", () => {
    const blocks = parseProseBlocks("1. Split the operator.\n2. Solve each part.");
    expect(blocks).toEqual([
      { type: "list", ordered: true, items: ["Split the operator.", "Solve each part."] },
    ]);
  });

  it("recognises markdown headings", () => {
    const blocks = parseProseBlocks("### Setup\n\nLet $x$ be fixed.");
    expect(blocks).toEqual([
      { type: "heading", level: 3, text: "Setup" },
      { type: "paragraph", text: "Let $x$ be fixed." },
    ]);
  });

  it("does not mistake a minus sign for a bullet", () => {
    expect(parseProseBlocks("-5 is negative.")).toEqual([
      { type: "paragraph", text: "-5 is negative." },
    ]);
  });
});
