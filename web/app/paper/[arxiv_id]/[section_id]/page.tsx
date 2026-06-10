import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { getSectionWithMath, getPaperByArxivId } from "@/lib/supabase/queries";
import { MathBlock } from "@/components/MathBlock";
import { PdfSectionPane } from "@/components/PdfSectionPane";
import { ProseWithMath } from "@/components/ProseWithMath";

export const revalidate = 3600;

interface PageProps {
  params: Promise<{ arxiv_id: string; section_id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { arxiv_id, section_id } = await params;
  const client = await createClient();
  const section = await getSectionWithMath(client, section_id);
  return {
    title: section?.title
      ? `${section.title} — arXiv:${arxiv_id}`
      : `Section — arXiv:${arxiv_id}`,
  };
}

export default async function SectionPage({ params }: PageProps) {
  const { arxiv_id, section_id } = await params;
  const client = await createClient();

  const [section, paper] = await Promise.all([
    getSectionWithMath(client, section_id),
    getPaperByArxivId(client, arxiv_id),
  ]);

  if (!section || !paper) notFound();

  const mathBlocks = section.math_blocks ?? [];

  return (
    <div className="flex h-full min-h-0">
      {/* Left pane — section content */}
      <div className="flex-1 min-w-0 overflow-y-auto px-6 py-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-zinc-400 dark:text-zinc-500 mb-6 flex items-center gap-1.5 flex-wrap">
          <a href="/" className="hover:text-zinc-700 dark:hover:text-zinc-300">
            Home
          </a>
          <span>/</span>
          <a
            href={`/paper/${arxiv_id}`}
            className="hover:text-zinc-700 dark:hover:text-zinc-300 truncate max-w-xs"
          >
            {paper.title}
          </a>
          <span>/</span>
          <span className="text-zinc-700 dark:text-zinc-300 truncate">
            {section.title ?? `Section ${section.order_idx + 1}`}
          </span>
        </nav>

        <h1 className="text-2xl font-bold mb-6">
          {section.title ?? `Section ${section.order_idx + 1}`}
        </h1>

        {/* Section body — interleave text + math */}
        <SectionBody section={section} mathBlocks={mathBlocks} />

        {/* Navigation */}
        <div className="mt-10 pt-6 border-t border-zinc-200 dark:border-zinc-700">
          <a
            href={`/paper/${arxiv_id}`}
            className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            ← Back to {paper.title}
          </a>
        </div>
      </div>

      {/* Right pane — PDF at the section's page */}
      <div className="hidden lg:flex flex-col w-[48%] shrink-0 border-l border-zinc-200 dark:border-zinc-700">
        <PdfSectionPane arxivId={arxiv_id} sectionTitle={section.title ?? ""} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plain-text cleanup (strips LaTeX table/comment artifacts that leaked in)
// ---------------------------------------------------------------------------

function cleanPlainText(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      let t = line;
      // Drop % comment lines
      t = t.replace(/%[^\n]*/g, "").trim();
      return t;
    })
    .filter((line) => {
      const t = line.trim();
      if (!t) return false;
      // Drop lines that look like table rows (3+ & separators)
      if ((t.match(/&/g) ?? []).length >= 3) return false;
      // Drop lines that are only backslash commands / column specs
      if (/^(\\[a-zA-Z]+\s*)+$/.test(t) && !t.includes(" ")) return false;
      if (/^\{[lcr|@{}\s]+\}/.test(t)) return false;
      return true;
    })
    .join("\n")
    .replace(/\s*&\s*/g, " ")   // remaining & → space
    .replace(/\\\\/g, "\n")      // \\ → newline
    .replace(/\n{3,}/g, "\n\n") // collapse blank lines
    .trim();
}

// ---------------------------------------------------------------------------
// Trivial math block filter
// ---------------------------------------------------------------------------

/**
 * Returns true for blocks that are just a single symbol extracted from a table
 * cell (e.g. $\downarrow$, $\uparrow$, $\times$) — not worth showing.
 */
function isTrivialBlock(block: import("@/lib/supabase/types").MathBlock): boolean {
  const stripped = block.latex_expr
    .trim()
    .replace(/^\$\$|\$\$$|^\$|\$$|^\\\[|\\\]$|^\\\(|\\\)$/g, "")
    .trim();
  // Single backslash command with no arguments: \downarrow, \uparrow, \cdot …
  if (/^\\[a-zA-Z]+$/.test(stripped)) return true;
  // Single character or digit
  if (stripped.length <= 2) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Interleaving helpers (server-side — no hooks needed)
// ---------------------------------------------------------------------------

type Segment =
  | { type: "text"; content: string }
  | { type: "math"; block: import("@/lib/supabase/types").MathBlock };

function buildSegments(
  plainText: string,
  mathBlocks: Array<import("@/lib/supabase/types").MathBlock>
): Segment[] {
  const sorted = [...mathBlocks].sort((a, b) => a.order_idx - b.order_idx);
  const segments: Segment[] = [];
  let remaining = plainText;
  const unplaced: typeof sorted = [];

  for (const block of sorted) {
    const before = block.context_before?.trim() ?? "";
    // Try to locate the last 60 chars of context_before inside remaining text
    let probe = before.slice(-60).trim();
    let idx = probe.length >= 8 ? remaining.indexOf(probe) : -1;

    // Fallback: shorter probe
    if (idx === -1 && probe.length > 20) {
      probe = probe.slice(-20);
      idx = remaining.indexOf(probe);
    }

    if (idx !== -1) {
      const splitAt = idx + probe.length;
      const textChunk = remaining.slice(0, splitAt);
      if (textChunk.trim()) segments.push({ type: "text", content: textChunk });
      segments.push({ type: "math", block });
      remaining = remaining.slice(splitAt);
    } else {
      unplaced.push(block);
    }
  }

  if (remaining.trim()) segments.push({ type: "text", content: remaining });
  for (const block of unplaced) segments.push({ type: "math", block });

  return segments;
}

// ---------------------------------------------------------------------------
// SectionBody
// ---------------------------------------------------------------------------

function SectionBody({
  section,
  mathBlocks,
}: {
  section: { plain_text: string | null };
  mathBlocks: Array<import("@/lib/supabase/types").MathBlock>;
}) {
  const plain = cleanPlainText(section.plain_text ?? "");
  const meaningfulBlocks = mathBlocks.filter((b) => !isTrivialBlock(b));

  if (meaningfulBlocks.length === 0 && !plain) {
    return (
      <p className="text-sm text-zinc-400 italic">
        This section contains primarily tables or figures — see the PDF viewer for details.
      </p>
    );
  }

  if (meaningfulBlocks.length === 0) {
    return (
      <div className="prose prose-zinc dark:prose-invert max-w-none">
        {plain.split(/\n{2,}/).map((para, i) => (
          <p key={i}><ProseWithMath text={para.trim()} /></p>
        ))}
      </div>
    );
  }

  const segments = buildSegments(plain, meaningfulBlocks);

  return (
    <div className="space-y-4">
      {segments.map((seg, i) =>
        seg.type === "text" ? (
          <div key={i} className="prose prose-zinc dark:prose-invert max-w-none text-[15px] leading-relaxed">
            {seg.content.split(/\n{2,}/).map((para, j) => (
              <p key={j} className="mb-3 last:mb-0">
                <ProseWithMath text={para.trim()} />
              </p>
            ))}
          </div>
        ) : (
          <MathBlock key={seg.block.id} block={seg.block} />
        )
      )}
    </div>
  );
}
