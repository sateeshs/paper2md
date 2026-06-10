/**
 * Extract an ArXiv ID from a plain ID or any recognised URL format.
 *
 * Supported inputs:
 *   2301.07984
 *   2301.07984v2
 *   https://arxiv.org/abs/2301.07984
 *   https://arxiv.org/pdf/2301.07984
 *   https://www.alphaxiv.org/abs/2301.07984
 *   https://alphaxiv.org/abs/2301.07984
 *
 * Returns the bare ID (without version suffix) or null if unrecognised.
 */

const BARE_ID_RE = /^(\d{4}\.\d{4,5})(v\d+)?$/;

// Matches /abs/<id> or /pdf/<id> in the path of arxiv.org / alphaxiv.org URLs
const URL_PATH_RE = /\/(?:abs|pdf)\/(\d{4}\.\d{4,5}(?:v\d+)?)/;

export function extractArxivId(input: string): string | null {
  const s = input.trim();

  // Plain ID
  const bareMatch = BARE_ID_RE.exec(s);
  if (bareMatch) return bareMatch[1];

  // URL
  try {
    const url = new URL(s);
    const host = url.hostname.replace(/^www\./, "");
    if (host === "arxiv.org" || host === "alphaxiv.org") {
      const pathMatch = URL_PATH_RE.exec(url.pathname);
      if (pathMatch) {
        // Strip version suffix
        return pathMatch[1].replace(/v\d+$/, "");
      }
    }
  } catch {
    // Not a URL — already handled by bare ID check above
  }

  return null;
}
