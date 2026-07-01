'use client'

import Link from 'next/link'

interface PrerequisitesCardProps {
  data: Record<string, unknown>
}

export function PrerequisitesCard({ data }: PrerequisitesCardProps) {
  const sectionTitle = data.section_title as string
  const prerequisites = (data.prerequisites as string[]) ?? []
  const count = data.count as number

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Prerequisites</p>
        <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">{sectionTitle}</p>
        <p className="text-xs text-gray-400 mt-0.5">{count} concepts found</p>
      </div>
      {prerequisites.length === 0 ? (
        <p className="px-4 py-4 text-sm text-gray-400 text-center">
          No prerequisites extracted yet — try explaining section math first.
        </p>
      ) : (
        <div className="px-4 py-3 flex flex-wrap gap-1.5">
          {prerequisites.map((concept) => (
            <Link
              key={concept}
              href={`/chat?q=${encodeURIComponent(`Find papers about ${concept}`)}`}
              className="inline-block text-xs bg-blue-50 text-blue-700 border border-blue-100 rounded-full px-3 py-1 hover:bg-blue-100 transition-colors"
            >
              {concept}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
