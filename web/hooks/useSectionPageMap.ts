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

function titleVariants(title: string): string[] {
  const full = normalizeTitle(title);
  const variants: string[] = [];
  if (full) variants.push(full);
  // "Chapter N: Subtitle" → also try the subtitle alone
  const chapterMatch = /^chapter\s+\d+[:\s]\s*(.+)/i.exec(title);
  if (chapterMatch) {
    const sub = normalizeTitle(chapterMatch[1].trim());
    if (sub && sub.length >= 4 && sub !== full) variants.push(sub);
  }
  return variants;
}

function titleInPage(title: string, pageText: string): boolean {
  const lines = pageText.split("\n");
  return titleVariants(title).some((norm) =>
    norm.length >= 3 && lines.some((line) => isHeadingLine(line, norm))
  );
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

        const doc = await (await import("@/lib/pdf-doc")).getPdfDocument(arxivId);
        const totalPages = doc.numPages; // actual total, may be > scanned pages
        const map = new Map<string, number>();

        // TOC zone: skip the first ~10% of the document (min 3 pages)
        // Section titles appear in the TOC on early pages; PDF.js often puts
        // the page-number on a separate line so they pass the heading check.
        const tocZone = Math.max(3, Math.ceil(totalPages * 0.1));

        // Build a per-page index once so we don't re-scan for every section
        const scannedPages = pageTexts.length - 1; // texts[0] is placeholder

        // For each section, find the best page whose text contains the title
        let unmapped = 0;
        for (const section of sections) {
          const title = section.title ?? "";
          let found = 0;

          // Collect all matching pages within the scanned range
          const matches: number[] = [];
          for (let p = 1; p <= scannedPages; p++) {
            if (titleInPage(title, pageTexts[p])) matches.push(p);
          }

          if (matches.length > 0) {
            // Prefer body pages over TOC-zone pages
            const bodyMatches = matches.filter((p) => p > tocZone);
            found = bodyMatches.length > 0 ? bodyMatches[0] : matches[0];
          }

          if (!found) {
            // Fallback: distribute evenly across total (possibly uncapped) pages
            found = Math.max(
              1,
              Math.round((section.order_idx / sections.length) * totalPages)
            );
            unmapped++;
          }

          map.set(section.id, found);
        }

        if (unmapped > 0) {
          console.debug(`[useSectionPageMap] ${unmapped}/${sections.length} sections used fallback (PDF scan capped at ${scannedPages} pages)`);
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
