import { NextResponse } from 'next/server'

interface ServerStatus {
  url: string | null
  status: 'ok' | 'error' | 'unconfigured'
  latency_ms?: number
  error?: string
}

interface HealthResponse {
  status: 'ok' | 'degraded' | 'error'
  mcp_servers: Record<string, ServerStatus>
  timestamp: string
}

const MCP_SERVERS = {
  paper_processor: process.env.PAPER_PROCESSOR_MCP_URL ?? null,
  paper_reader: process.env.PAPER_READER_MCP_URL ?? null,
  arxiv_search: process.env.ARXIV_SEARCH_MCP_URL ?? null,
  math_to_code: process.env.MATH_TO_CODE_MCP_URL ?? null,
}

async function checkServer(baseUrl: string): Promise<Omit<ServerStatus, 'url'>> {
  const start = Date.now()
  try {
    const res = await fetch(`${baseUrl}/health`, {
      signal: AbortSignal.timeout(5000),
    })
    const latency_ms = Date.now() - start
    if (!res.ok) {
      return { status: 'error', latency_ms, error: `HTTP ${res.status}` }
    }
    return { status: 'ok', latency_ms }
  } catch (err) {
    return {
      status: 'error',
      latency_ms: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
    }
  }
}

export async function GET(): Promise<NextResponse<HealthResponse>> {
  const checks = await Promise.all(
    Object.entries(MCP_SERVERS).map(async ([name, url]) => {
      if (!url) {
        return [name, { url: null, status: 'unconfigured' as const }] as const
      }
      const result = await checkServer(url)
      return [name, { url, ...result }] as const
    })
  )

  const mcp_servers = Object.fromEntries(checks) as Record<string, ServerStatus>

  const configured = Object.values(mcp_servers).filter((s) => s.status !== 'unconfigured')
  const errors = configured.filter((s) => s.status === 'error')

  const overallStatus =
    configured.length === 0 ? 'error'
    : errors.length === 0 ? 'ok'
    : errors.length < configured.length ? 'degraded'
    : 'error'

  return NextResponse.json(
    { status: overallStatus, mcp_servers, timestamp: new Date().toISOString() },
    { status: overallStatus === 'error' ? 503 : 200 }
  )
}
