/**
 * A paper is viewable once its sections are stored. "explaining" papers are
 * readable while the math-explanation backfill is still filling in blocks;
 * the runner flips them to "complete" when it has worked through every block.
 */
export const VIEWABLE_STATUSES = ["complete", "explaining"] as const;

export function isViewableStatus(status: string | null | undefined): boolean {
  return (VIEWABLE_STATUSES as readonly string[]).includes(status ?? "");
}
