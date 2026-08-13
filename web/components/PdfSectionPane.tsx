"use client";

import { useEffect, useState } from "react";
import { PdfPageViewer } from "@/components/PdfPageViewer";
import { extractPageTexts } from "@/lib/pdf-doc";

interface PdfSectionPaneProps {
  arxivId: string;
  sectionTitle: string;
  /** 0-based position of this section among all sections — used for page estimation fallback */
  orderIdx?: number;
  /** Total number of sections in the paper — used for page estimation fallback */
  totalSections?: number;
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
    .replace(/^[\d.]+\s+/, "")              // strip leading "1 " / "2.3 "
    .replace(/^[ivxlcdmIVXLCDM]+\.\s+/, "") // strip roman numerals
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Returns true if rawLine looks like a section heading for this title.
 * Accepts:   "Supervised Fine-Tuning"   or   "3.1 Supervised Fine-Tuning"
 * Rejects:   "Supervised Fine-Tuning . . . . . . 12"   (TOC dot-leader entries)
 */
function isHeadingLine(rawLine: string, normTitle: string): boolean {
  // Reject TOC dot-leader entries: ". . . . ." pattern (PDF.js extracts spaced dots)
  if (/\.\s+\.\s+\./.test(rawLine)) return false;
  // Reject diagram/figure bullet items (·, •, -, *)
  if (/^[\s·•\-\*]/.test(rawLine.trim())) return false;
  const stripped = rawLine.trim()
    .replace(/^\d+(\.\d+)*\.?\s+/, "")       // strip optional leading "3.1 "
    .replace(/^[ivxlcdmIVXLCDM]+\.\s+/i, ""); // strip roman "IV. "
  return normalizeLine(stripped) === normTitle;
}

/**
 * Extract candidate normalized titles to match against.
 * For "Chapter 3: Nash Equilibrium" this returns both the full normalized form
 * AND just the subtitle "nash equilibrium", since typeset PDFs often have
 * "Chapter 3" and "Nash Equilibrium" on separate lines.
 */
function titleVariants(title: string): string[] {
  const full = normalizeTitle(title);
  const variants: string[] = [];
  if (full) variants.push(full);

  // "Chapter N: Subtitle" → also try "subtitle"
  const chapterMatch = /^chapter\s+\d+[:\s]\s*(.+)/i.exec(title);
  if (chapterMatch) {
    const sub = normalizeTitle(chapterMatch[1].trim());
    if (sub && sub.length >= 4 && sub !== full) variants.push(sub);
  }

  return variants;
}

/** Finds which PDF page contains the section title as a heading. */
async function findPage(
  arxivId: string,
  title: string,
  orderIdx?: number,
  totalSections?: number,
): Promise<number> {
  const variants = titleVariants(title);

  const { extractPageTexts, getPdfDocument } = await import("@/lib/pdf-doc");
  const texts = await extractPageTexts(arxivId);
  const scannedPages = texts.length - 1;
  const tocZone = Math.max(3, Math.ceil(scannedPages * 0.1));

  if (variants.length > 0) {
    for (const normTitle of variants) {
      // Pass 1: heading-line exact match within scanned pages
      const matches: number[] = [];
      for (let p = 1; p <= scannedPages; p++) {
        if (texts[p].split("\n").some((line) => isHeadingLine(line, normTitle))) {
          matches.push(p);
        }
      }
      if (matches.length > 0) {
        const bodyMatches = matches.filter((p) => p > tocZone);
        return bodyMatches.length > 0 ? bodyMatches[0] : matches[0];
      }
    }

    // Pass 2: substring fallback within scanned pages
    for (const normTitle of variants) {
      const fallbacks: number[] = [];
      for (let p = 1; p <= scannedPages; p++) {
        if (normalizeLine(texts[p]).includes(normTitle)) fallbacks.push(p);
      }
      if (fallbacks.length > 0) {
        const bodyFallbacks = fallbacks.filter((p) => p > tocZone);
        return bodyFallbacks.length > 0 ? bodyFallbacks[0] : fallbacks[0];
      }
    }

    // Pass 2b: fuzzy — match if 80%+ of title words appear on the page
    const primary = variants[0];
    const titleWords = primary.split(" ").filter((w) => w.length >= 3);
    if (titleWords.length >= 2) {
      const fuzzyMatches: number[] = [];
      for (let p = 1; p <= scannedPages; p++) {
        const pageNorm = normalizeLine(texts[p]);
        const matched = titleWords.filter((w) => pageNorm.includes(w)).length;
        if (matched / titleWords.length >= 0.8) fuzzyMatches.push(p);
      }
      if (fuzzyMatches.length > 0) {
        const bodyFuzzy = fuzzyMatches.filter((p) => p > tocZone);
        return bodyFuzzy.length > 0 ? bodyFuzzy[0] : fuzzyMatches[0];
      }
    }
  }

  // Pass 3: ratio-based estimate, then targeted scan around estimated page.
  if (orderIdx !== undefined && totalSections && totalSections > 0) {
    const doc = await getPdfDocument(arxivId);
    const actualTotal = doc.numPages;
    const estimated = Math.max(1, Math.round(((orderIdx + 0.5) / totalSections) * actualTotal));

    // If estimated page is beyond what we scanned, do a targeted scan
    // ±20 pages around the estimate to find the exact heading.
    if (estimated > scannedPages && variants.length > 0) {
      const scanStart = Math.max(1, estimated - 20);
      const scanEnd = Math.min(actualTotal, estimated + 20);
      for (let p = scanStart; p <= scanEnd; p++) {
        const page = await doc.getPage(p);
        const content = await page.getTextContent();
        const { buildPageText } = await import("@/lib/pdf-doc");
        const pageText = buildPageText(
          content.items as Array<{ str?: string; transform?: number[] }>
        );
        for (const normTitle of variants) {
          if (pageText.split("\n").some((line) => isHeadingLine(line, normTitle))) {
            return p;
          }
          if (normalizeLine(pageText).includes(normTitle)) {
            return p;
          }
        }
      }
    }

    return estimated;
  }

  return 1;
}

export function PdfSectionPane({
  arxivId,
  sectionTitle,
  orderIdx,
  totalSections,
}: PdfSectionPaneProps) {
  const [targetPage, setTargetPage] = useState<number>(1);

  useEffect(() => {
    findPage(arxivId, sectionTitle, orderIdx, totalSections).then(setTargetPage);
  }, [arxivId, sectionTitle, orderIdx, totalSections]);

  return <PdfPageViewer arxivId={arxivId} targetPage={targetPage} />;
}
