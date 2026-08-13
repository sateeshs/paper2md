/**
 * Copied verbatim from web/lib/prerequisites.ts
 * Utilities for extracting and aggregating prerequisite concepts
 * from math block explanation JSON fields.
 */

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
]

const FRAGMENT_NOISE = [
  "not part of a proof",
  "is also required",
  "will be helpful",
  "is needed",
  "are needed",
  "are required",
  "as well as",
]

const LEAD_IN_RE =
  /^(the reader (needs|must know|should know|requires|should be familiar with|is expected to know)|a reader (should|must|needs to)|an understanding of|familiarity with|knowledge of|requires?|needs?|assumes?|understanding of|the following (concepts?|background|knowledge)[:\s]*)[:\s]*/i

const SUFFIX_RE =
  /\s*(is (also )?(required|needed|assumed|expected)|will be (helpful|useful|necessary)|are (also )?(required|needed|assumed)|, (which|as) (was|were|is|are) introduced.*)$/i

const MIN_LEN = 3
const MAX_PREREQUISITES = 30

export function parsePrerequisiteString(raw: string): string[] {
  if (!raw || typeof raw !== "string") return []

  const trimmed = raw.trim()
  if (!trimmed) return []

  const lower = trimmed.toLowerCase().replace(/[.!?]+$/, "").trim()

  if (NONE_PHRASES.some((p) => lower === p || lower.startsWith(p + " ") || lower.startsWith(p + ","))) {
    return []
  }

  const sentences = trimmed
    .split(/\.\s+(?=[A-Z])|\.\s*$/)
    .map((s) => s.trim())
    .filter(Boolean)

  const concepts: string[] = []

  for (const sentence of sentences) {
    const stripped = sentence
      .replace(LEAD_IN_RE, "")
      .replace(/\s+as introduced in [Ss]ection[\s\d.]+/g, "")
      .replace(/\s+\(see [^)]+\)/g, "")
      .replace(/\s+introduced (earlier|above|in section[\s\d.]*)/gi, "")
      .trim()

    if (!stripped) continue

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
        if (p.length < MIN_LEN) return false
        const pl = p.toLowerCase()
        if (/^(the|a|an|of|in|on|at|to|for|with|by|from|that|this|which|also|both)$/i.test(p)) return false
        if (FRAGMENT_NOISE.some((f) => pl.includes(f))) return false
        if (NONE_PHRASES.some((n) => pl === n)) return false
        if (/^(the reader|a reader|an understanding|familiarity|knowledge of)/i.test(p)) return false
        return true
      })

    concepts.push(...parts)
  }

  return concepts
}

export function aggregatePrerequisites(
  mathBlocks: Array<{ explanation: string | null }>
): string[] {
  const seen = new Set<string>()
  const result: string[] = []

  for (const block of mathBlocks) {
    if (!block.explanation) continue

    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(block.explanation)
    } catch {
      continue
    }

    const raw = (parsed?.prerequisites as string) ?? ""
    if (!raw) continue

    for (const concept of parsePrerequisiteString(raw)) {
      const key = concept.toLowerCase()
      if (!seen.has(key)) {
        seen.add(key)
        result.push(concept)
      }
      if (result.length >= MAX_PREREQUISITES) break
    }

    if (result.length >= MAX_PREREQUISITES) break
  }

  return result.sort((a, b) => a.localeCompare(b))
}
