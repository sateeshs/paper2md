/**
 * Trigger the GitHub Actions workflow_dispatch for processing a paper.
 *
 * Required env vars:
 *   GITHUB_DISPATCH_TOKEN  — PAT with Actions: read/write
 *   GITHUB_REPO_OWNER      — GitHub username or org (e.g. "ssateesh")
 *   GITHUB_REPO_NAME       — repo name (e.g. "paper2md")
 */

const WORKFLOW_FILE = "process_pending.yml";

export type DispatchResult =
  | { triggered: true }
  | { triggered: false; reason: string };

export async function triggerProcessing(arxivId: string): Promise<DispatchResult> {
  const token = process.env.GITHUB_DISPATCH_TOKEN?.trim();
  const owner = process.env.GITHUB_REPO_OWNER?.trim();
  const repo  = process.env.GITHUB_REPO_NAME?.trim();

  if (!token || !owner || !repo) {
    return { triggered: false, reason: "GITHUB_DISPATCH_TOKEN / GITHUB_REPO_OWNER / GITHUB_REPO_NAME not configured" };
  }

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { arxiv_id: arxivId },
      }),
    });

    // 204 = success (no content)
    if (res.status === 204) return { triggered: true };

    const text = await res.text();
    return { triggered: false, reason: `GitHub API ${res.status}: ${text.slice(0, 200)}` };
  } catch (err) {
    return { triggered: false, reason: String(err) };
  }
}
