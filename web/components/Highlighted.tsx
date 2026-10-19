import { splitMatches } from "@/lib/section-search";

interface HighlightedProps {
  text: string;
  terms: string[];
}

/** Render text with every search-term occurrence wrapped in <mark>. */
export function Highlighted({ text, terms }: HighlightedProps) {
  return (
    <>
      {splitMatches(text, terms).map((part, i) =>
        part.match ? (
          <mark
            key={i}
            className="rounded-sm bg-amber-200/80 dark:bg-amber-500/30 text-inherit px-0.5"
          >
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        )
      )}
    </>
  );
}
