import type { Section } from "@/lib/supabase/types";

/**
 * Left indent for a section's outline level.
 *
 * Tailwind needs literal class names, so this is a lookup rather than a
 * computed `pl-${n}`. Level 1 (chapter) sits flush; each level nests further.
 */
const INDENT_BY_LEVEL: Record<number, string> = {
  1: "",
  2: "pl-3",
  3: "pl-6",
  4: "pl-9",
};

export function indentClass(level: number | null | undefined): string {
  return INDENT_BY_LEVEL[level ?? 1] ?? "";
}

/** Chapters and top-level sections carry more visual weight than leaves. */
export function titleWeightClass(level: number | null | undefined): string {
  if (level === 1) return "font-semibold text-[0.95rem]";
  if (level === 2) return "font-medium";
  return "font-normal";
}

interface SectionNumberProps {
  section: Pick<Section, "number" | "order_idx">;
}

/**
 * The real section number ("2.5.3") when the outline is known, otherwise the
 * legacy positional label for papers processed before migration 008.
 */
export function SectionNumber({ section }: SectionNumberProps) {
  return (
    <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500 tabular-nums">
      {section.number ?? `§${section.order_idx + 1}`}
    </span>
  );
}

interface PageBadgeProps {
  section: Pick<Section, "page_start" | "page_end" | "page_source">;
}

/**
 * PDF page range. Renders nothing when the paper predates page mapping, so the
 * old flat layout degrades cleanly rather than showing "p. null".
 */
export function PageBadge({ section }: PageBadgeProps) {
  const { page_start: start, page_end: end, page_source: source } = section;
  if (start == null) return null;

  const label = end != null && end > start ? `p. ${start}–${end}` : `p. ${start}`;

  return (
    <span
      title={source === "inferred" ? "Approximate — interpolated from neighbouring sections" : undefined}
      className={[
        "shrink-0 rounded px-1.5 py-0.5 text-[0.7rem] font-mono tabular-nums",
        source === "inferred"
          ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 italic"
          : "bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400",
      ].join(" ")}
    >
      {label}
    </span>
  );
}
