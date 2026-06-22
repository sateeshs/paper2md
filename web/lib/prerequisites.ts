/**
 * Utilities for extracting and aggregating prerequisite concepts
 * from math block explanation JSON fields.
 *
 * The `prerequisites` field is LLM-generated prose, not structured data,
 * so parsing is heuristic. Precision > recall — better to show fewer,
 * correct concepts than many noisy fragments.
 */

// Phrases that indicate no prerequisites — filter these out
const NOISE_PHRASES = [
  "no special",
  "no prior",
  "none required",
  "none needed",
  "not required",
  "no prerequisites",
  "standard undergraduate",
  "basic calculus",
  "high school",
  "not part of a proof",
  "no specific",
  "no particular",
  "elementary",
];

// Minimum token length to keep (filters out "a", "of", "the", etc.)
const MIN_TOKEN_LEN = 4;

// Maximum prerequisites to show per section
const MAX_PREREQUISITES = 30;

/**
 * Parse a single prerequisites prose string into individual concept tokens.
 *
 * Handles comma/semicolon/conjunction-separated lists as well as
 * phrases introduced by "requires", "needs", "familiarity with", etc.
 */
export function parsePrerequisiteString(raw: string): string[] {
  if (!raw || typeof raw !== "string") return [];

  const trimmed = raw.trim();
  if (!trimmed) return [];

  // Check for noise phrases — return empty if the whole string is noise
  const lower = trimmed.toLowerCase();
  if (NOISE_PHRASES.some((phrase) => lower.includes(phrase))) return [];

  // Strip common lead-in phrases to get to the list
  const stripped = trimmed
    .replace(/^(the reader (needs|must know|should know|requires)|requires?|needs?|assumes?|knowledge of|familiarity with|understanding of)[:\s]*/i, "")
    .replace(/\s+as introduced in [Ss]ection[\s\d.]+/g, "")
    .replace(/\s+\(see [^)]*\)/g, "")
    .replace(/\s+introduced (earlier|above|in section[\s\d.]*)/gi, "");

  // Split on comma, semicolon, and " and " / " or "
  const parts = stripped
    .split(/,\s*|\s*;\s*|\s+and\s+|\s+or\s+/)
    .map((p) => p.trim().replace(/[.!?]+$/, "").trim())
    .filter((p) => {
      if (p.length < MIN_TOKEN_LEN) return false;
      const pl = p.toLowerCase();
      if (NOISE_PHRASES.some((phrase) => pl.includes(phrase))) return false;
      // Filter fragments that are just articles or prepositions
      if (/^(the|a|an|of|in|on|at|to|for|with|by|from|that|this|which)$/i.test(p)) return false;
      return true;
    });

  return parts;
}

/**
 * Aggregate and deduplicate prerequisites across all math blocks in a section.
 *
 * Returns a sorted, deduplicated array capped at MAX_PREREQUISITES entries.
 */
export function aggregatePrerequisites(
  mathBlocks: Array<{ explanation: string | null }>
): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const block of mathBlocks) {
    if (!block.explanation) continue;

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(block.explanation);
    } catch {
      continue;
    }

    const raw = (parsed?.prerequisites as string) ?? "";
    if (!raw) continue;

    for (const concept of parsePrerequisiteString(raw)) {
      const key = concept.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        result.push(concept);
      }
      if (result.length >= MAX_PREREQUISITES) break;
    }

    if (result.length >= MAX_PREREQUISITES) break;
  }

  return result.sort((a, b) => a.localeCompare(b));
}
