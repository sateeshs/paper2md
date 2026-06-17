"use client";

import { useState, useEffect } from "react";
import { extractPageTexts } from "@/lib/pdf-doc";

export type SectionPageMap = Map<string, number>; // sectionId → 1-based page number

interface SectionStub {
  id: string;
  title: string | null;
  order_idx: number;
}

function normalizeLine(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/^[\d.]+\s+/, "")
    .replace(/^[ivxlcdmIVXLCDM]+\.\s+/i, "")
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** True if rawLine is a heading for this title (strips section numbers, rejects TOC). */
function isHeadingLine(rawLine: string, normTitle: string): boolean {
  // Reject TOC dot-leader entries: ". . . . ." pattern
  if (/\.\s+\.\s+\./.test(rawLine)) return false;
  // Reject bullet items (·, •, -, *)
  if (/^[\s·•\-\*]/.test(rawLine.trim())) return false;
  const stripped = rawLine.trim()
    .replace(/^\d+(\.\d+)*\.?\s+/, "")
    .replace(/^[ivxlcdmIVXLCDM]+\.\s+/i, "");
  return normalizeLine(stripped) === normTitle;
}

function titleInPage(title: string, pageText: string): boolean {
  const norm = normalizeTitle(title);
  if (!norm || norm.length < 3) return false;
  return pageText.split("\n").some((line) => isHeadingLine(line, norm));
}

/**
 * Scans PDF text once and returns a map of sectionId → page number.
 * Falls back to order-based estimate when a title isn't found.
 */
export function useSectionPageMap(
  arxivId: string,
  sections: SectionStub[]
): { pageMap: SectionPageMap; scanning: boolean } {
  const [pageMap, setPageMap] = useState<SectionPageMap>(new Map());
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    if (!sections.length) return;
    let cancelled = false;

    async function scan() {
      setScanning(true);
      try {
        const pageTexts = await extractPageTexts(arxivId);
        if (cancelled) return;

        const totalPages = pageTexts.length - 1; // texts[0] is placeholder
        const map = new Map<string, number>();

        // For each section, find the first page whose text contains the title
        for (const section of sections) {
          const title = section.title ?? "";
          let found = 0;

          for (let p = 1; p <= totalPages; p++) {
            if (titleInPage(title, pageTexts[p])) {
              found = p;
              break;
            }
          }

          if (!found) {
            // Fallback: distribute evenly across pages
            found = Math.max(
              1,
              Math.round((section.order_idx / sections.length) * totalPages)
            );
          }

          map.set(section.id, found);
        }

        setPageMap(map);
      } finally {
        if (!cancelled) setScanning(false);
      }
    }

    scan();
    return () => { cancelled = true; };
  }, [arxivId, sections]);

  return { pageMap, scanning };
}
