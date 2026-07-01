'use client'

interface Reference {
  ref_id: string
  title: string | null
  authors: string[] | null
  year: string | null
  arxiv_id: string | null
  doi: string | null
}

interface ReferencesCardProps {
  data: Record<string, unknown>
}

export function ReferencesCard({ data }: ReferencesCardProps) {
  const title = data.title as string
  const references = (data.references as Reference[]) ?? []
  const count = data.count as number

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">References</p>
        <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">{title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{count} citations</p>
      </div>
      <ul className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
        {references.slice(0, 12).map((ref) => (
          <li key={ref.ref_id} className="px-4 py-2.5">
            <div className="flex items-start gap-2">
              <span className="text-xs text-gray-400 font-mono shrink-0 mt-0.5 w-8">
                [{ref.ref_id}]
              </span>
              <div className="flex-1 min-w-0">
                {ref.title ? (
                  ref.arxiv_id ? (
                    <a
                      href={`/paper/${ref.arxiv_id}`}
                      className="text-xs text-blue-700 hover:underline line-clamp-2 block"
                    >
                      {ref.title}
                    </a>
                  ) : (
                    <p className="text-xs text-gray-700 line-clamp-2">{ref.title}</p>
                  )
                ) : (
                  <p className="text-xs text-gray-400 italic">Untitled reference</p>
                )}
                <p className="text-xs text-gray-400 mt-0.5">
                  {ref.authors?.slice(0, 2).join(', ')}
                  {ref.authors && ref.authors.length > 2 ? ' et al.' : ''}
                  {ref.year ? ` · ${ref.year}` : ''}
                </p>
              </div>
            </div>
          </li>
        ))}
        {references.length > 12 && (
          <li className="px-4 py-2 text-xs text-gray-400 text-center">
            +{references.length - 12} more — open paper page to view all
          </li>
        )}
      </ul>
    </div>
  )
}
