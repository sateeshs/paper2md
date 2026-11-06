/**
 * Pick up to `limit` entries of `items` to show beside a search result, the
 * ones that matched `query` first — so a search for "google deepmind" shows
 * the DeepMind affiliation rather than whichever happens to be listed first.
 */
export function pickMatches(
  items: readonly string[] | null | undefined,
  query: string,
  limit: number
): string[] {
  const list = items ?? [];
  const needle = query.trim().toLowerCase();
  const matched = needle ? list.filter((s) => s.toLowerCase().includes(needle)) : [];
  const rest = list.filter((s) => !matched.includes(s));
  return [...matched, ...rest].slice(0, limit);
}
