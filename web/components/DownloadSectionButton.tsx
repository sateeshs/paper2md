'use client'

import { useState } from 'react'

interface MathBlockData {
  id: string
  order_idx: number
  env_type: string
  latex_expr: string
  explanation: string | null
  explanation_model: string | null
}

interface SectionData {
  id: string
  title: string | null
  order_idx: number
  plain_text: string | null
  math_blocks?: MathBlockData[]
}

interface PaperData {
  title: string
  arxiv_id: string
}

interface DownloadSectionButtonProps {
  section: SectionData
  paper: PaperData
}

function buildMarkdown(section: SectionData, paper: PaperData): string {
  const lines: string[] = [
    `# ${section.title ?? `Section ${section.order_idx + 1}`}`,
    ``,
    `**Paper:** ${paper.title}  `,
    `**ArXiv:** [${paper.arxiv_id}](https://arxiv.org/abs/${paper.arxiv_id})`,
    ``,
  ]

  if (section.plain_text) {
    lines.push(`## Text`, ``, section.plain_text, ``)
  }

  const mathBlocks = section.math_blocks ?? []
  if (mathBlocks.length > 0) {
    lines.push(`## Math Blocks`, ``)

    for (const block of mathBlocks) {
      lines.push(`### Formula ${block.order_idx + 1} (${block.env_type})`, ``)
      lines.push('```latex', block.latex_expr, '```', '')

      let exp: Record<string, string> | null = null
      if (block.explanation) {
        try {
          exp = JSON.parse(block.explanation) as Record<string, string>
        } catch {
          // plain text fallback
        }
      }

      if (exp) {
        if (exp.what_it_computes) lines.push(`**What it computes:** ${exp.what_it_computes}`, '')
        if (exp.symbol_meanings) lines.push(`**Symbols:** ${exp.symbol_meanings}`, '')
        if (exp.derivation) lines.push(`**Derivation:** ${exp.derivation}`, '')
        if (exp.intuition) lines.push(`**Intuition:** ${exp.intuition}`, '')
        if (exp.mathematical_significance ?? exp.paper_relevance) {
          lines.push(`**Why it matters:** ${exp.mathematical_significance ?? exp.paper_relevance}`, '')
        }
        if (block.explanation_model) {
          lines.push(`*Explanation model: ${block.explanation_model}*`, '')
        }
      } else if (block.explanation) {
        lines.push(block.explanation, '')
      }

      // Check localStorage for any generated code for this block
      if (typeof window !== 'undefined') {
        for (const lib of ['numpy', 'pytorch', 'jax', 'scipy']) {
          const key = `code:${block.id}:${lib}`
          const stored = localStorage.getItem(key)
          if (!stored) continue
          try {
            const artifact = JSON.parse(stored) as {
              function_name?: string
              imports?: string
              code?: string
              example_usage?: string
              test_code?: string | null
            }
            lines.push(`#### Generated Code (${lib})`, '')
            if (artifact.imports) lines.push('```python', artifact.imports, '```', '')
            if (artifact.code) lines.push('```python', artifact.code, '```', '')
            if (artifact.example_usage) {
              lines.push(`**Example usage:**`, '', '```python', artifact.example_usage, '```', '')
            }
            if (artifact.test_code) {
              lines.push(`**Tests:**`, '', '```python', artifact.test_code, '```', '')
            }
          } catch {
            // ignore corrupt cache entry
          }
        }
      }

      lines.push('---', '')
    }
  }

  return lines.join('\n')
}

export function DownloadSectionButton({ section, paper }: DownloadSectionButtonProps) {
  const [downloading, setDownloading] = useState(false)

  function handleDownload() {
    setDownloading(true)
    try {
      const md = buildMarkdown(section, paper)
      const blob = new Blob([md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const slug = (section.title ?? `section-${section.order_idx + 1}`)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .slice(0, 50)
      const filename = `${paper.arxiv_id}-${slug}.md`
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <button
      onClick={handleDownload}
      disabled={downloading}
      className="inline-flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
    >
      <span>↓</span>
      <span>{downloading ? 'Preparing…' : 'Download .md'}</span>
    </button>
  )
}
