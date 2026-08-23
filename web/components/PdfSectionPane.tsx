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

/** Check if a page's text contains a heading matching any of the title variants. */
function titleInPage(title: string, pageText: string): boolean {
  const lines = pageText.split("\n");
  return titleVariants(title).some((norm) =>
    norm.length >= 3 && lines.some((line) => isHeadingLine(line, norm))
  );
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
 * Scan ALL pages of the PDF for the section title.
 * Skips TOC zone (first ~10% of pages) unless no body match is found.
 * Returns the first body-page match, or falls back to estimation.
 */
async function findPageByFullScan(
  arxivId: string,
  title: string,
  orderIdx: number | undefined,
  totalSections: number | undefined,
): Promise<number> {
  const variants = titleVariants(title);
  if (variants.length === 0) {
    // No usable title — fall back to estimation
    const { getPdfDocument } = await import("@/lib/pdf-doc");
    const doc = await getPdfDocument(arxivId);
    return estimatePage(orderIdx, totalSections, doc.numPages);
  }

  const { extractPageTexts, getPdfDocument } = await import("@/lib/pdf-doc");
  const [pageTexts, doc] = await Promise.all([
    extractPageTexts(arxivId),
    getPdfDocument(arxivId),
  ]);
  const totalPages = doc.numPages;
  // TOC zone: cap at 5 pages — 10% was too aggressive for long papers (157pp → 16pp TOC zone)
  const tocZone = Math.min(5, Math.max(2, Math.ceil(totalPages * 0.03)));
  const scannedPages = pageTexts.length - 1; // texts[0] is placeholder

  // Collect all matching pages
  const matches: number[] = [];
  for (let p = 1; p <= scannedPages; p++) {
    if (titleInPage(title, pageTexts[p])) matches.push(p);
  }

  if (matches.length > 0) {
    // Prefer body pages over TOC-zone pages
    const bodyMatches = matches.filter((p) => p > tocZone);
    if (bodyMatches.length > 0) {
      // Among body matches, pick the one closest to the estimated page
      const estimated = estimatePage(orderIdx, totalSections, totalPages);
      bodyMatches.sort((a, b) => Math.abs(a - estimated) - Math.abs(b - estimated));
      return bodyMatches[0];
    }
    // All matches in TOC zone — return last one (most likely the actual heading, not TOC entry)
    return matches[matches.length - 1];
  }

  // No match found — fall back to estimation
  return estimatePage(orderIdx, totalSections, totalPages);
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

      // 1. Show estimated page immediately while full scan runs
      const estimated = estimatePage(orderIdx, totalSections, numPages);
      if (!cancelled) setTargetPage(estimated);

      // 2. Full-scan all pages for an exact title match
      const exact = await findPageByFullScan(arxivId, sectionTitle, orderIdx, totalSections);
      if (!cancelled && exact !== estimated) {
        setTargetPage(exact);
      }
    }

    resolve();
    return () => { cancelled = true; };
  }, [arxivId, sectionTitle, orderIdx, totalSections]);

  return <PdfPageViewer arxivId={arxivId} targetPage={targetPage} />;
}
