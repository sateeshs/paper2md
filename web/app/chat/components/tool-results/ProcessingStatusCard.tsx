'use client'

interface ProcessingStatusCardProps {
  data: Record<string, unknown>
  toolName: string
}

const TOOL_LABELS: Record<string, string> = {
  process_paper: 'Processing Paper',
  get_paper_status: 'Paper Status',
  create_sections: 'Creating Sections',
  explain_section_math: 'Explaining Math',
  explain_section_algorithms: 'Explaining Algorithms',
}

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  complete: { bg: 'bg-green-50', text: 'text-green-700', dot: 'bg-green-500' },
  processing: { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' },
  pending: { bg: 'bg-yellow-50', text: 'text-yellow-700', dot: 'bg-yellow-400' },
  error: { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-500' },
  queued: { bg: 'bg-purple-50', text: 'text-purple-700', dot: 'bg-purple-500' },
}

export function ProcessingStatusCard({ data, toolName }: ProcessingStatusCardProps) {
  const label = TOOL_LABELS[toolName] ?? 'Status'
  const arxivId = data.arxiv_id as string | undefined
  const status = (data.status as string | undefined) ?? 'unknown'
  const message = data.message as string | undefined
  const errorMsg = data.error as string | undefined

  // Stats for create_sections / explain_section_math
  const sectionsCreated = data.sections_created as number | undefined
  const mathExplained = data.math_explained as number | undefined
  const algorithmsExplained = data.algorithms_explained as number | undefined
  const blocksExplained = data.blocks_explained as number | undefined
  const totalBlocks = data.total_blocks as number | undefined

  const styleKey = status in STATUS_STYLES ? status : 'pending'
  const style = STATUS_STYLES[styleKey]

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden w-full max-w-md">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
        {arxivId && (
          <p className="text-sm font-medium text-gray-900 mt-0.5 font-mono">{arxivId}</p>
        )}
      </div>

      <div className="px-4 py-3 space-y-2">
        {/* Status badge */}
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${style.bg} ${style.text}`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${style.dot} ${status === 'processing' ? 'animate-pulse' : ''}`}
            />
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </span>
        </div>

        {/* Message */}
        {message && (
          <p className="text-xs text-gray-600">{message}</p>
        )}

        {/* Error */}
        {errorMsg && (
          <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{errorMsg}</p>
        )}

        {/* Stats grid */}
        {(sectionsCreated !== undefined ||
          mathExplained !== undefined ||
          algorithmsExplained !== undefined ||
          blocksExplained !== undefined) && (
          <div className="grid grid-cols-2 gap-2 pt-1">
            {sectionsCreated !== undefined && (
              <Stat label="Sections" value={sectionsCreated} />
            )}
            {mathExplained !== undefined && (
              <Stat label="Math explained" value={mathExplained} />
            )}
            {algorithmsExplained !== undefined && (
              <Stat label="Algorithms" value={algorithmsExplained} />
            )}
            {blocksExplained !== undefined && totalBlocks !== undefined && (
              <Stat label="Blocks" value={`${blocksExplained}/${totalBlocks}`} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-semibold text-gray-700">{value}</p>
    </div>
  )
}
