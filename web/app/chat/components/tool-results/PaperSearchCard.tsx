'use client'

import Link from 'next/link'

interface Paper {
  arxiv_id: string
  title: string
  authors?: string[]
  abstract?: string
  status?: string
  is_processed?: boolean
}

interface PaperSearchCardProps {
  data: Record<string, unknown>
  toolName: string
}

const TOOL_LABELS: Record<string, string> = {
  search_papers: 'Search Results',
  find_prerequisite_papers: 'Prerequisite Papers',
  get_paper_metadata: 'Paper',
}

export function PaperSearchCard({ data, toolName }: PaperSearchCardProps) {
  const label = TOOL_LABELS[toolName] ?? 'Papers'
  const query = data.query as string | undefined
  const concept = data.concept as string | undefined

  // Normalize: single paper (get_paper_metadata) or array
  const rawPapers = data.papers ?? (data.arxiv_id ? [data] : [])
  const papers = (rawPapers as Paper[]) ?? []

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
        {(query || concept) && (
          <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">
            {query ?? concept}
          </p>
        )}
        {papers.length > 0 && (
          <p className="text-xs text-gray-400 mt-0.5">{papers.length} paper{papers.length !== 1 ? 's' : ''}</p>
        )}
      </div>

      {papers.length === 0 ? (
        <p className="px-4 py-4 text-sm text-gray-400 text-center">No papers found.</p>
      ) : (
        <ul className="divide-y divide-gray-50 max-h-80 overflow-y-auto">
          {papers.map((paper) => (
            <li key={paper.arxiv_id} className="px-4 py-3">
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/paper/${paper.arxiv_id}`}
                    className="text-sm text-blue-700 hover:underline line-clamp-2 block font-medium"
                  >
                    {paper.title || paper.arxiv_id}
                  </Link>
                  {paper.authors && paper.authors.length > 0 && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      {paper.authors.slice(0, 2).join(', ')}
                      {paper.authors.length > 2 ? ' et al.' : ''}
                    </p>
                  )}
                  {paper.abstract && (
                    <p className="text-xs text-gray-400 mt-1 line-clamp-2">{paper.abstract}</p>
                  )}
                </div>
                <div className="shrink-0 flex flex-col items-end gap-1">
                  {paper.is_processed || paper.status === 'complete' ? (
                    <span className="text-xs bg-green-50 text-green-700 border border-green-100 rounded-full px-2 py-0.5">
                      Ready
                    </span>
                  ) : (
                    <span className="text-xs bg-gray-50 text-gray-500 border border-gray-100 rounded-full px-2 py-0.5">
                      {paper.status ?? 'Not processed'}
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
