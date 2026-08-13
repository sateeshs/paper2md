"use client";

import { useEffect, useState } from "react";
import { PdfPageViewer } from "@/components/PdfPageViewer";

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
  if (/\.\s+\.\s+\./.test(rawLine)) return false;
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

  const chapterMatch = /^chapter\s+\d+[:\s]\s*(.+)/i.exec(title);
  if (chapterMatch) {
    const sub = normalizeTitle(chapterMatch[1].trim());
    if (sub && sub.length >= 4 && sub !== full) variants.push(sub);
  }

  return variants;
}

/** Check if a page's text matches any of the title variants. */
function matchesTitle(pageText: string, variants: string[], tocZone: boolean): boolean {
  for (const normTitle of variants) {
    if (pageText.split("\n").some((line) => isHeadingLine(line, normTitle))) {
      if (!tocZone) return true;
    }
    if (normalizeLine(pageText).includes(normTitle)) {
      if (!tocZone) return true;
    }
  }
  return false;
}

/** Estimate page from section position (instant, no PDF text extraction). */
function estimatePage(
  orderIdx: number | undefined,
  totalSections: number | undefined,
  numPages: number,
): number {
  if (orderIdx !== undefined && totalSections && totalSections > 0) {
    return Math.max(1, Math.round(((orderIdx + 0.5) / totalSections) * numPages));
  }
  return 1;
}

/**
 * Search for the exact page by scanning outward from a starting point.
 * Scans ±radius pages, checking pages closest to center first.
 */
async function findExactPage(
  arxivId: string,
  title: string,
  startPage: number,
  radius: number = 40,
): Promise<number | null> {
  const variants = titleVariants(title);
  if (variants.length === 0) return null;

  const { getPdfDocument, buildPageText } = await import("@/lib/pdf-doc");
  const doc = await getPdfDocument(arxivId);
  const numPages = doc.numPages;
  const tocZone = Math.max(3, Math.ceil(numPages * 0.1));

  // Scan outward from startPage: check center first, then ±1, ±2, etc.
  for (let offset = 0; offset <= radius; offset++) {
    const pagesToCheck = offset === 0
      ? [startPage]
      : [startPage - offset, startPage + offset];

    for (const p of pagesToCheck) {
      if (p < 1 || p > numPages) continue;
      const page = await doc.getPage(p);
      const content = await page.getTextContent();
      const pageText = buildPageText(
        content.items as Array<{ str?: string; transform?: number[] }>
      );
      if (matchesTitle(pageText, variants, p <= tocZone)) {
        return p;
      }
    }
  }

  return null;
}

export function PdfSectionPane({
  arxivId,
  sectionTitle,
  orderIdx,
  totalSections,
}: PdfSectionPaneProps) {
  const [targetPage, setTargetPage] = useState<number>(1);

  useEffect(() => {
    let cancelled = false;

    async function resolve() {
      const { getPdfDocument } = await import("@/lib/pdf-doc");
      const doc = await getPdfDocument(arxivId);
      const numPages = doc.numPages;

      // 1. Show estimated page immediately
      const estimated = estimatePage(orderIdx, totalSections, numPages);
      if (!cancelled) setTargetPage(estimated);

      // 2. Refine with text search (outward from estimate)
      const exact = await findExactPage(arxivId, sectionTitle, estimated);
      if (!cancelled && exact !== null && exact !== estimated) {
        setTargetPage(exact);
      }
    }

    resolve();
    return () => { cancelled = true; };
  }, [arxivId, sectionTitle, orderIdx, totalSections]);

  return <PdfPageViewer arxivId={arxivId} targetPage={targetPage} />;
}
