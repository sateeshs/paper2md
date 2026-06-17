"use client";

import { useEffect, useState } from "react";
import { PdfPageViewer } from "@/components/PdfPageViewer";
import { extractPageTexts } from "@/lib/pdf-doc";

interface PdfSectionPaneProps {
  arxivId: string;
  sectionTitle: string;
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

/** Finds which PDF page contains the section title as a heading. */
async function findPage(arxivId: string, title: string): Promise<number> {
  const normTitle = normalizeTitle(title);
  if (!normTitle || normTitle.length < 3) return 1;

  const texts = await extractPageTexts(arxivId);

  // Pass 1: find a heading line (strips leading section number, rejects TOC entries)
  for (let p = 1; p < texts.length; p++) {
    if (texts[p].split("\n").some((line) => isHeadingLine(line, normTitle))) {
      return p;
    }
  }

  // Pass 2: substring fallback (last resort — less accurate)
  for (let p = 1; p < texts.length; p++) {
    if (normalizeLine(texts[p]).includes(normTitle)) return p;
  }

  return 1;
}

export function PdfSectionPane({ arxivId, sectionTitle }: PdfSectionPaneProps) {
  const [targetPage, setTargetPage] = useState<number>(1);

  useEffect(() => {
    findPage(arxivId, sectionTitle).then(setTargetPage);
  }, [arxivId, sectionTitle]);

  return <PdfPageViewer arxivId={arxivId} targetPage={targetPage} />;
}
