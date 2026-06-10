import type { SectionWithMath } from "@/lib/supabase/types";

interface SectionCardProps {
  section: SectionWithMath;
  arxivId: string;
}

export function SectionCard({ section, arxivId }: SectionCardProps) {
  const mathCount = section.math_blocks?.length ?? 0;

  return (
    <a
      href={`/paper/${arxivId}/${section.id}`}
      className="block rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-3 hover:border-zinc-400 dark:hover:border-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-0.5">
            §{section.order_idx + 1}
          </p>
          <p className="font-medium truncate">
            {section.title ?? "Untitled section"}
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0 text-sm text-zinc-500 dark:text-zinc-400">
          {section.has_math && mathCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 px-2 py-0.5 text-xs font-medium">
              {mathCount} eq
            </span>
          )}
          <span className="text-zinc-300 dark:text-zinc-600">→</span>
        </div>
      </div>

      {section.plain_text && (
        <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400 line-clamp-2">
          {section.plain_text.slice(0, 200)}
        </p>
      )}
    </a>
  );
}
