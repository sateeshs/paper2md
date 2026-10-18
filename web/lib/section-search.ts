/** Pure helpers for searching a paper's sections by title and body text. */

export const MIN_TERM_LENGTH = 2;
export const MAX_QUERY_LENGTH = 100;
export const MAX_TERMS = 5;
export const SEARCH_RESULT_LIMIT = 50;
export const SNIPPET_RADIUS = 60;

// `,` `(` `)` delimit PostgREST or() conditions, `"` quotes them, and
// `%` `_` `*` `\` are ilike wildcards/escapes — none may reach the filter.
const UNSAFE_CHARS = /[,()"%_*\\]/g;

export interface MatchPart {
  text: string;
  match: boolean;
}

/** Turn raw input into search terms (each must match), or null if nothing searchable. */
export function parseSectionQuery(raw: string | null | undefined): string[] | null {
  const terms = (raw ?? "")
    .slice(0, MAX_QUERY_LENGTH)
    .replace(UNSAFE_CHARS, " ")
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length >= MIN_TERM_LENGTH)
    .slice(0, MAX_TERMS);
  return terms.length > 0 ? terms : null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Split text into runs, marking every case-insensitive occurrence of any term. */
export function splitMatches(text: string, terms: string[]): MatchPart[] {
  if (terms.length === 0 || text.length === 0) return [{ text, match: false }];
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  return text
    .split(pattern)
    .filter((part) => part.length > 0)
    .map((part) => ({ text: part, match: terms.some((t) => t === part.toLowerCase()) }));
}

/** A window of `text` around the first term match, or its opening when no term occurs. */
export function snippetAround(text: string, terms: string[], radius = SNIPPET_RADIUS): string {
  const lower = text.toLowerCase();
  const hits = terms
    .map((term) => ({ at: lower.indexOf(term), len: term.length }))
    .filter((hit) => hit.at >= 0)
    .sort((a, b) => a.at - b.at);
  if (hits.length === 0) {
    const head = text.slice(0, radius * 2);
    return head.length < text.length ? `${head}…` : head;
  }
  const { at, len } = hits[0];
  const start = Math.max(0, at - radius);
  const end = Math.min(text.length, at + len + radius);
  return `${start > 0 ? "…" : ""}${text.slice(start, end)}${end < text.length ? "…" : ""}`;
}
