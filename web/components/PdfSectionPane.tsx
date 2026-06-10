"use client";

import { useEffect, useState } from "react";
import { PdfPageViewer } from "@/components/PdfPageViewer";
import { extractPageTexts } from "@/lib/pdf-doc";

interface PdfSectionPaneProps {
  arxivId: string;
  sectionTitle: string;
}

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/^[\d.]+\s+/, "")
    .replace(/^[ivxlcdmIVXLCDM]+\.\s+/, "")
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Finds which PDF page contains the section title as a heading (isolated line). */
async function findPage(arxivId: string, title: string): Promise<number> {
  const normTitle = normalize(title);
  if (!normTitle || normTitle.length < 3) return 1;

  const texts = await extractPageTexts(arxivId);

  // Pass 1: title on its own line with a section-number somewhere in the preceding
  // non-blank lines (skip blank items — pdfjs inserts spacing items between heading parts).
  // e.g. raw items ["3.4", " ", "Inference"] → strongest heading signal.
  const SECTION_NUM_RE = /^\d+(\.\d+)*\.?$/;
  for (let p = 1; p < texts.length; p++) {
    const rawLines = texts[p].split("\n");
    for (let i = 1; i < rawLines.length; i++) {
      if (normalize(rawLines[i]) !== normTitle) continue;
      // Look back up to 3 lines, skipping blanks, for a section number
      for (let back = 1; back <= 3 && i - back >= 0; back++) {
        const prev = rawLines[i - back].trim();
        if (!prev) continue;           // skip blank spacing items
        if (SECTION_NUM_RE.test(prev)) return p;
        break;                         // non-blank, non-number → stop looking back
      }
    }
  }

  // Pass 2: title on its own line, not also embedded in longer lines on the same page
  // (figure labels have it surrounded by other short items — body headings are isolated)
  for (let p = 1; p < texts.length; p++) {
    const lines = texts[p].split("\n").map((l) => normalize(l));
    const exactMatches = lines.filter((l) => l === normTitle).length;
    const longerMatches = lines.filter((l) => l !== normTitle && l.includes(normTitle)).length;
    if (exactMatches > 0 && longerMatches === 0) return p;
  }

  // Pass 3: any exact standalone line
  for (let p = 1; p < texts.length; p++) {
    const lines = texts[p].split("\n").map((l) => normalize(l));
    if (lines.some((l) => l === normTitle)) return p;
  }

  // Pass 4: substring fallback
  for (let p = 1; p < texts.length; p++) {
    if (normalize(texts[p]).includes(normTitle)) return p;
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
