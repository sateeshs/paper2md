import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import { getCodeArtifact } from '@/lib/supabase/queries'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

type Library = 'numpy' | 'pytorch' | 'jax' | 'scipy'
const VALID_LIBRARIES: Library[] = ['numpy', 'pytorch', 'jax', 'scipy']

// Long-running tool — extend Vercel function timeout
export const maxDuration = 120
export const runtime = 'nodejs'

export async function POST(
  req: Request,
  { params }: { params: Promise<{ block_id: string }> }
): Promise<NextResponse> {
  const { block_id } = await params

  let library: Library = 'numpy'
  try {
    const body = await req.json()
    if (VALID_LIBRARIES.includes(body.library)) {
      library = body.library as Library
    }
  } catch {
    // body parse failure — proceed with numpy default
  }

  // 1. Check Supabase cache — skip MCP call if already generated
  const supabase = await createServiceClient()
  const cached = await getCodeArtifact(supabase, block_id, library)
  if (cached) {
    return NextResponse.json(cached)
  }

  // 2. Gate on MCP availability
  const mcpUrl = process.env.MATH_TO_CODE_MCP_URL
  if (!mcpUrl) {
    return NextResponse.json(
      { error: 'math-to-code-mcp not configured — set MATH_TO_CODE_MCP_URL' },
      { status: 503 }
    )
  }

  // 3. Call MCP tool directly via raw SDK client (tools are not callable in ai@4.3.x outside streamText)
  const client = new Client(
    { name: 'math-code-client', version: '1.0.0' },
    { capabilities: {} }
  )
  const transport = new StreamableHTTPClientTransport(new URL(mcpUrl))

  try {
    await client.connect(transport)
    const result = await client.callTool({
      name: 'generate_formula_code',
      arguments: { block_id, library },
    })

    // MCP tool returns { content: [{ type: 'text', text: '...' }] }
    const text = (result.content as Array<{ text?: string }>)?.[0]?.text ?? '{}'
    const artifact = JSON.parse(text) as Record<string, unknown>

    if (artifact.error) {
      return NextResponse.json({ error: artifact.error }, { status: 422 })
    }

    return NextResponse.json(artifact)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: `MCP call failed: ${message}` }, { status: 502 })
  } finally {
    await client.close().catch(() => undefined)
  }
}
