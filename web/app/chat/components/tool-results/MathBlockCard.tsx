'use client'

interface MathBlockCardProps {
  data: Record<string, unknown>
}

interface MathBlock {
  id: string
  order_idx: number
  env_type: string
  latex_expr: string
  explanation: string | null
}

export function MathBlockCard({ data }: MathBlockCardProps) {
  const title = data.title as string
  const mathBlocks = (data.math_blocks as MathBlock[]) ?? []
  const namedBlocks = mathBlocks.filter((b) =>
    ['equation', 'align', 'gather', 'multline'].includes(b.env_type)
  )

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Math Blocks</p>
        <p className="text-sm font-medium text-gray-900 mt-0.5 truncate">{title}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {mathBlocks.length} total · {namedBlocks.length} named equations
        </p>
      </div>
      <ul className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
        {namedBlocks.slice(0, 8).map((b) => (
          <li key={b.id} className="px-4 py-3">
            <div className="flex items-start gap-2">
              <span className="text-xs text-gray-400 font-mono shrink-0 mt-0.5">
                Eq {b.order_idx + 1}
              </span>
              <div className="flex-1 min-w-0">
                <code className="text-xs text-gray-700 font-mono block truncate">
                  {b.latex_expr.slice(0, 80)}{b.latex_expr.length > 80 ? '…' : ''}
                </code>
                {b.explanation && (() => {
                  try {
                    const exp = JSON.parse(b.explanation)
                    return (
                      <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                        {exp.what_it_computes}
                      </p>
                    )
                  } catch { return null }
                })()}
              </div>
            </div>
          </li>
        ))}
        {namedBlocks.length > 8 && (
          <li className="px-4 py-2 text-xs text-gray-400 text-center">
            +{namedBlocks.length - 8} more equations — open section page to view all
          </li>
        )}
      </ul>
    </div>
  )
}
