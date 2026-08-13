// Singleton PDF document cache — loads once per arxiv_id per session.
// Shared between PdfPageViewer and section-page finding so we don't download twice.

type PDFDocumentProxy = Awaited<ReturnType<typeof loadPdf>>;

const cache = new Map<string, PDFDocumentProxy>();
// Single promise so concurrent callers all await the same initialization
let configurePromise: Promise<void> | null = null;

function configurePdfJs(): Promise<void> {
  if (!configurePromise) {
    configurePromise = import("pdfjs-dist").then((pdfjsLib) => {
      pdfjsLib.GlobalWorkerOptions.workerSrc =
        `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
    });
  }
  return configurePromise;
}

async function loadPdf(url: string) {
  await configurePdfJs();
  const { getDocument } = await import("pdfjs-dist");
  const doc = await getDocument({ url }).promise;
  return doc;
}

export async function getPdfDocument(arxivId: string) {
  if (cache.has(arxivId)) return cache.get(arxivId)!;
  const doc = await loadPdf(`/api/pdf/${arxivId}`);
  cache.set(arxivId, doc);
  return doc;
}

/**
 * Maximum pages to scan for section-title mapping.
 * Very long PDFs (600+ pages) are slow — scan all but in batches.
 */
const MAX_SCAN_PAGES = 800;

/**
 * Build readable text from PDF.js TextContent items.
 * Items on the same Y line are joined with spaces; line breaks only between
 * different Y positions. This produces proper heading lines for matching.
 */
export function buildPageText(items: Array<{ str?: string; transform?: number[] }>): string {
  const lines: string[] = [];
  let currentLine: string[] = [];
  let lastY: number | null = null;

  for (const item of items) {
    const str = item.str ?? "";
    if (!str) continue;
    // transform[5] is the Y coordinate in PDF space
    const y = item.transform?.[5] ?? 0;
    if (lastY !== null && Math.abs(y - lastY) > 2) {
      // New line — flush previous
      if (currentLine.length > 0) lines.push(currentLine.join(" "));
      currentLine = [];
    }
    currentLine.push(str);
    lastY = y;
  }
  if (currentLine.length > 0) lines.push(currentLine.join(" "));

  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/**
 * Extract plain text page-by-page up to maxPages.
 * Returns array indexed by pageNum (1-based); entries beyond maxPages are "".
 */
export async function extractPageTexts(
  arxivId: string,
  maxPages = MAX_SCAN_PAGES
): Promise<string[]> {
  const doc = await getPdfDocument(arxivId);
  const limit = Math.min(doc.numPages, maxPages);
  const texts: string[] = [""];          // index 0 unused so texts[pageNum] works
  for (let i = 1; i <= limit; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const text = buildPageText(
      content.items as Array<{ str?: string; transform?: number[] }>
    );
    texts.push(text);
  }
  return texts;
}
