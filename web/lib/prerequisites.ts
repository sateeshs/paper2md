/**
 * Utilities for extracting and aggregating prerequisite concepts
 * from math block explanation JSON fields.
 *
 * The `prerequisites` field may be:
 *   - A comma-separated list (new format): "measure theory, ELBO, normalizing flows"
 *   - Prose sentences (old format): "The reader should know X and Y. Familiarity with Z is needed."
 *
 * Both formats are handled: prose is split on sentence boundaries first,
 * then lead-in phrases are stripped, then comma/conjunction-split into concepts.
 */

// Whole-string noise: if the entire value is just "none" or similar, skip it
const NONE_PHRASES = [
  "none",
  "no specific",
  "no special",
  "no prior",
  "none required",
  "none needed",
  "not required",
  "no prerequisites",
  "no particular",
];

// Per-concept noise: filter individual extracted fragments that are meaningless
const FRAGMENT_NOISE = [
  "not part of a proof",
  "is also required",
  "will be helpful",
  "is needed",
  "are needed",
  "are required",
  "as well as",
];

// Lead-in phrases to strip from the start of each sentence before concept extraction
const LEAD_IN_RE =
  /^(the reader (needs|must know|should know|requires|should be familiar with|is expected to know)|a reader (should|must|needs to)|an understanding of|familiarity with|knowledge of|requires?|needs?|assumes?|understanding of|the following (concepts?|background|knowledge)[:\s]*)[:\s]*/i;

// Suffix phrases to strip from the end of a fragment
const SUFFIX_RE =
  /\s*(is (also )?(required|needed|assumed|expected)|will be (helpful|useful|necessary)|are (also )?(required|needed|assumed)|, (which|as) (was|were|is|are) introduced.*)$/i;

// Minimum character length for a concept to be shown
const MIN_LEN = 3;

// Maximum prerequisites to show per section
const MAX_PREREQUISITES = 30;

/**
 * Parse a single prerequisites string (list or prose) into individual concept tokens.
 */
export function parsePrerequisiteString(raw: string): string[] {
  if (!raw || typeof raw !== "string") return [];

  const trimmed = raw.trim();
  if (!trimmed) return [];

  const lower = trimmed.toLowerCase().replace(/[.!?]+$/, "").trim();

  // If the whole string signals "no prerequisites", bail out immediately
  if (NONE_PHRASES.some((p) => lower === p || lower.startsWith(p + " ") || lower.startsWith(p + ","))) {
    return [];
  }

  // Step 1: Split into sentences (handles old prose format and new list format)
  // A sentence ends with ". " followed by a capital letter, or just "."
  const sentences = trimmed
    .split(/\.\s+(?=[A-Z])|\.\s*$/)
    .map((s) => s.trim())
    .filter(Boolean);

  const concepts: string[] = [];

  for (const sentence of sentences) {
    // Strip lead-in from sentence start
    const stripped = sentence
      .replace(LEAD_IN_RE, "")
      .replace(/\s+as introduced in [Ss]ection[\s\d.]+/g, "")
      .replace(/\s+\(see [^)]+\)/g, "")
      .replace(/\s+introduced (earlier|above|in section[\s\d.]*)/gi, "")
      .trim();

    if (!stripped) continue;

    // Split on comma, semicolon, " and ", " or "
    const parts = stripped
      .split(/,\s*|\s*;\s*|\s+and\s+|\s+or\s+/)
      .map((p) =>
        p
          .trim()
          .replace(SUFFIX_RE, "")
          .replace(/[.!?]+$/, "")
          .trim()
      )
      .filter((p) => {
        if (p.length < MIN_LEN) return false;
        const pl = p.toLowerCase();
        // Drop if it's just articles/prepositions
        if (/^(the|a|an|of|in|on|at|to|for|with|by|from|that|this|which|also|both)$/i.test(p)) return false;
        // Drop noisy fragments
        if (FRAGMENT_NOISE.some((f) => pl.includes(f))) return false;
        // Drop whole-string noise phrases appearing as fragments
        if (NONE_PHRASES.some((n) => pl === n)) return false;
        // Drop sentence lead-ins that weren't fully stripped (e.g. "the reader should")
        if (/^(the reader|a reader|an understanding|familiarity|knowledge of)/i.test(p)) return false;
        return true;
      });

    concepts.push(...parts);
  }

  return concepts;
}

/**
 * Aggregate and deduplicate prerequisites across all math blocks in a section.
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
