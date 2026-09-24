/**
 * Block-level structure for LLM prose (math explanations, section text).
 *
 * `ProseWithMath` renders inline content only — it emits spans, so newlines in
 * its input collapse. A symbol list written as consecutive "- " lines therefore
 * used to read as one run-on paragraph. This module recovers the line
 * structure; `<ProseBlocks>` renders it.
 *
 * Pure and DOM-free so it can be unit-tested directly.
 */

export type ProseBlock =
  | { type: "heading"; level: 3 | 4; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] };

/** "- item", "* item", "• item" — the space is required so "-5" stays prose. */
const BULLET_RE = /^\s*[-*•]\s+(.*)$/;
/** "1. item" */
const ORDERED_RE = /^\s*\d+[.)]\s+(.*)$/;
/** A wrapped continuation of the list item above it. */
const INDENTED_RE = /^\s+\S/;

function matchItem(line: string): { ordered: boolean; text: string } | null {
  const bullet = BULLET_RE.exec(line);
  if (bullet) return { ordered: false, text: bullet[1].trim() };
  const ordered = ORDERED_RE.exec(line);
  if (ordered) return { ordered: true, text: ordered[1].trim() };
  return null;
}

function headingOf(chunk: string): ProseBlock | null {
  if (chunk.startsWith("### ")) return { type: "heading", level: 3, text: chunk.slice(4).trim() };
  if (chunk.startsWith("#### ")) return { type: "heading", level: 4, text: chunk.slice(5).trim() };
  return null;
}

/**
 * Parse one blank-line-delimited chunk into blocks.
 *
 * Lists and prose may alternate inside a chunk, so runs are grouped rather than
 * classifying the chunk as a whole: a lead-in sentence keeps its own paragraph
 * instead of swallowing the bullets under it.
 */
function parseChunk(chunk: string): ProseBlock[] {
  const heading = headingOf(chunk);
  if (heading) return [heading];

  const blocks: ProseBlock[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ type: "list", ...list });
    list = null;
  };

  for (const line of chunk.split("\n")) {
    if (!line.trim()) continue;

    const item = matchItem(line);
    if (item) {
      flushParagraph();
      if (list && list.ordered !== item.ordered) flushList();
      if (!list) list = { ordered: item.ordered, items: [] };
      list.items.push(item.text);
      continue;
    }

    // An indented line under a list item is that item's continuation.
    if (list && INDENTED_RE.test(line)) {
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  return blocks;
}

/** Split prose into heading / paragraph / list blocks, in document order. */
export function parseProseBlocks(text: string): ProseBlock[] {
  return text
    .split(/\n{2,}/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .flatMap(parseChunk);
}
