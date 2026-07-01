'use client'

import type { ToolInvocation } from 'ai'
import { SectionListCard } from './SectionListCard'
import { MathBlockCard } from './MathBlockCard'
import { PrerequisitesCard } from './PrerequisitesCard'
import { ReferencesCard } from './ReferencesCard'
import { PaperSearchCard } from './PaperSearchCard'
import { ProcessingStatusCard } from './ProcessingStatusCard'

interface ToolResultRendererProps {
  invocation: ToolInvocation
}

export function ToolResultRenderer({ invocation }: ToolResultRendererProps) {
  if (invocation.state !== 'result') {
    return (
      <div className="text-xs text-gray-400 flex items-center gap-1.5 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
        <span className="animate-spin">⚙</span>
        <span>Calling <code className="font-mono">{invocation.toolName}</code>…</span>
      </div>
    )
  }

  let result: unknown
  try {
    const text = (invocation.result as { content?: Array<{ text?: string }> })
      ?.content?.[0]?.text ?? '{}'
    result = JSON.parse(text)
  } catch {
    return <RawCard toolName={invocation.toolName} result={invocation.result} />
  }

  const data = result as Record<string, unknown>

  switch (invocation.toolName) {
    case 'get_paper_sections':
      return <SectionListCard data={data} />
    case 'get_section_math':
      return <MathBlockCard data={data} />
    case 'get_prerequisites':
      return <PrerequisitesCard data={data} />
    case 'get_paper_references':
      return <ReferencesCard data={data} />
    case 'search_papers':
    case 'find_prerequisite_papers':
    case 'get_paper_metadata':
      return <PaperSearchCard data={data} toolName={invocation.toolName} />
    case 'process_paper':
    case 'get_paper_status':
    case 'create_sections':
    case 'explain_section_math':
    case 'explain_section_algorithms':
      return <ProcessingStatusCard data={data} toolName={invocation.toolName} />
    default:
      return <RawCard toolName={invocation.toolName} result={data} />
  }
}

function RawCard({ toolName, result }: { toolName: string; result: unknown }) {
  return (
    <div className="text-xs bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 font-mono text-gray-500 max-h-40 overflow-auto">
      <span className="text-gray-400 block mb-1">{toolName}</span>
      {JSON.stringify(result, null, 2)}
    </div>
  )
}
