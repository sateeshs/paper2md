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
 * 600-page PDFs crash the browser tab if we extract all pages — cap here.
 */
const MAX_SCAN_PAGES = 150;

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
    const text = content.items
      .map((it) => ("str" in it ? (it as { str: string }).str : ""))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    texts.push(text);
  }
  return texts;
}
