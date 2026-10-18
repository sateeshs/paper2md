"use client";

import { ProseWithMath } from "@/components/ProseWithMath";
import { parseProseBlocks } from "@/lib/prose-blocks";

interface ProseBlocksProps {
  text: string;
  className?: string;
}

/**
 * Renders prose with its block structure intact — paragraphs, bullet and
 * numbered lists, headings — with inline math in each.
 *
 * `ProseWithMath` alone emits inline spans, so a symbol list written one entry
 * per line collapses into a run-on paragraph. Use this wherever the text may
 * carry more than a single paragraph.
 */
export function ProseBlocks({ text, className }: ProseBlocksProps) {
  const blocks = parseProseBlocks(text);
  if (blocks.length === 0) return null;

  return (
    <div className={className}>
      {blocks.map((block, i) => {
        if (block.type === "heading") {
          const Heading = block.level === 3 ? "h3" : "h4";
          return (
            <Heading
              key={i}
              className="font-semibold mt-3 first:mt-0 mb-1 text-zinc-800 dark:text-zinc-100"
            >
              <ProseWithMath text={block.text} />
            </Heading>
          );
        }

        if (block.type === "list") {
          const List = block.ordered ? "ol" : "ul";
          return (
            <List
              key={i}
              className={`${
                block.ordered ? "list-decimal" : "list-disc"
              } list-outside ml-5 space-y-1 my-1.5 first:mt-0 last:mb-0`}
            >
              {block.items.map((item, j) => (
                <li key={j} className="pl-0.5 leading-relaxed">
                  <ProseWithMath text={item} />
                </li>
              ))}
            </List>
          );
        }

        return (
          <p key={i} className="mb-2 last:mb-0 leading-relaxed">
            <ProseWithMath text={block.text} />
          </p>
        );
      })}
    </div>
  );
}
