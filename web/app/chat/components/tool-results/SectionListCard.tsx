'use client'

import Link from 'next/link'

interface Section {
  id: string
  order_idx: number
  title: string
  has_math: boolean
  math_block_count: number
}

interface SectionListCardProps {
  data: Record<string, unknown>
}

export function SectionListCard({ data }: SectionListCardProps) {
  const arxivId = data.arxiv_id as string
  const title = data.title as string
  const sections = (data.sections as Section[]) ?? []

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sections</p>
        <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">{title || arxivId}</p>
      </div>
      <ul className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
        {sections.map((s) => (
          <li key={s.id}>
            <Link
              href={`/paper/${arxivId}/${s.id}`}
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-blue-50 transition-colors group"
            >
              <span className="text-xs text-gray-400 w-5 shrink-0">{s.order_idx + 1}</span>
              <span className="text-sm text-gray-700 group-hover:text-blue-700 flex-1 truncate">
                {s.title || 'Untitled section'}
              </span>
              {s.math_block_count > 0 && (
                <span className="shrink-0 text-xs bg-blue-100 text-blue-700 rounded-full px-2 py-0.5 font-mono">
                  ∑ {s.math_block_count}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
      <div className="px-4 py-2 bg-gray-50 border-t border-gray-100">
        <Link href={`/paper/${arxivId}`} className="text-xs text-blue-600 hover:underline">
          View full paper →
        </Link>
      </div>
    </div>
  )
}
