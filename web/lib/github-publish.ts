/**
 * Generate a Markdown document from a paper's DB content and commit it to
 * the paper2md knowledge-base GitHub repo.
 *
 * Required env vars:
 *   GITHUB_KB_TOKEN   — PAT with Contents read/write on the kb repo
 *   GITHUB_KB_OWNER   — GitHub username or org
 *   GITHUB_KB_REPO    — repo name, e.g. "paper2md-kb"
 */

import type { Paper, SectionWithMath, MathBlock } from "@/lib/supabase/types";

// ---------------------------------------------------------------------------
// Markdown generation
// ---------------------------------------------------------------------------

function parseSummary(summaryMd: string | null): Record<string, string> {
  if (!summaryMd) return {};
  const result: Record<string, string> = {};
  // DSPy structured output is stored as JSON in summary_md
  try {
    return JSON.parse(summaryMd);
  } catch {
    // fallback: treat whole string as tldr
    return { tldr: summaryMd.trim() };
  }
}

function parseMathExplanation(explanation: string | null): Record<string, string> | null {
  if (!explanation) return null;
  try {
    return JSON.parse(explanation);
  } catch {
    return { what_it_computes: explanation };
  }
}

function mathBlockMd(block: MathBlock, index: number): string {
  const lines: string[] = [];
  lines.push(`**Block ${index + 1}** — \`${block.env_type}\``);
  lines.push("```latex");
  lines.push(block.latex_expr.trim());
  lines.push("```");

  const exp = parseMathExplanation(block.explanation);
  if (exp) {
    if (exp.what_it_computes) lines.push(`**What it computes**: ${exp.what_it_computes}`);
    if (exp.symbol_meanings)  lines.push(`**Symbols**: ${exp.symbol_meanings}`);
    if (exp.intuition)        lines.push(`**Intuition**: ${exp.intuition}`);
    if (exp.paper_relevance)  lines.push(`**Why it matters**: ${exp.paper_relevance}`);
  }
  return lines.join("\n");
}

export function generatePaperMarkdown(
  paper: Paper,
  sections: SectionWithMath[]
): string {
  const lines: string[] = [];
  const arxivUrl = paper.arxiv_id
    ? `https://arxiv.org/abs/${paper.arxiv_id}`
    : null;

  // Header
  lines.push(`# ${paper.title}`);
  lines.push("");
  if (arxivUrl) lines.push(`**ArXiv**: ${arxivUrl}`);
  lines.push(`**Published**: ${new Date(paper.created_at).toISOString().slice(0, 10)}`);
  lines.push("");
  lines.push("---");
  lines.push("");

  // Summary
  const summary = parseSummary(paper.summary_md);
  if (Object.keys(summary).length > 0) {
    lines.push("## Summary");
    lines.push("");
    const fields: Array<[string, string]> = [
      ["TL;DR", summary.tldr],
      ["Problem", summary.problem],
      ["Approach", summary.approach],
      ["Results", summary.results],
      ["Practical Takeaways", summary.takeaways],
      ["Limitations / Open Questions", summary.limitations],
    ];
    for (const [label, value] of fields) {
      if (value) {
        lines.push(`### ${label}`);
        lines.push("");
        lines.push(value.trim());
        lines.push("");
      }
    }
    lines.push("---");
    lines.push("");
  }

  // Sections
  lines.push("## Sections");
  lines.push("");
  for (const section of sections) {
    lines.push(`### ${section.title ?? `Section ${section.order_idx + 1}`}`);
    lines.push("");
    if (section.plain_text?.trim()) {
      lines.push(section.plain_text.trim());
      lines.push("");
    }

    const blocks = section.math_blocks ?? [];
    if (blocks.length > 0) {
      lines.push("#### Math Blocks");
      lines.push("");
      blocks.forEach((b, i) => {
        lines.push(mathBlockMd(b, i));
        lines.push("");
      });
    }
  }

  return lines.join("\n").trimEnd() + "\n";
}

// ---------------------------------------------------------------------------
// GitHub Contents API
// ---------------------------------------------------------------------------

export type CommitResult =
  | { ok: true; url: string }
  | { ok: false; error: string };

export async function commitMarkdownToGitHub(
  arxivId: string,
  markdown: string
): Promise<CommitResult> {
  const token = process.env.GITHUB_KB_TOKEN?.trim();
  const owner = process.env.GITHUB_KB_OWNER?.trim();
  const repo  = process.env.GITHUB_KB_REPO?.trim();

  if (!token || !owner || !repo) {
    return { ok: false, error: "GITHUB_KB_TOKEN / GITHUB_KB_OWNER / GITHUB_KB_REPO not configured" };
  }

  const path = `papers/${arxivId}.md`;
  const apiUrl = `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
  };

  // Fetch existing file SHA (needed for updates)
  let sha: string | undefined;
  try {
    const existing = await fetch(apiUrl, { headers });
    if (existing.ok) {
      const data = await existing.json() as { sha?: string };
      sha = data.sha;
    }
  } catch {
    // file doesn't exist yet — that's fine
  }

  const body: Record<string, unknown> = {
    message: sha
      ? `Update ${arxivId}.md`
      : `Add ${arxivId}.md`,
    content: Buffer.from(markdown, "utf-8").toString("base64"),
  };
  if (sha) body.sha = sha;

  const res = await fetch(apiUrl, {
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `GitHub API ${res.status}: ${text.slice(0, 300)}` };
  }

  const fileUrl = `https://github.com/${owner}/${repo}/blob/main/${path}`;
  return { ok: true, url: fileUrl };
}
