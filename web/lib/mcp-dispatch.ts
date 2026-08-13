/**
 * Fire-and-forget trigger for paper processing via the paper-processor MCP server.
 *
 * The queue route calls this without awaiting — the paper is already in Supabase
 * with status=pending, so the Modal cron will pick it up even if this call is dropped.
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

export interface MCPDispatchResult {
  triggered: boolean
  method: 'mcp' | 'github'
  error?: string
}

/**
 * Call process_paper on the paper-processor MCP server.
 * Errors are swallowed — the caller should fire-and-forget with `void`.
 */
export async function triggerMCPProcessing(arxivId: string): Promise<void> {
  const baseUrl = process.env.PAPER_PROCESSOR_MCP_URL
  if (!baseUrl) return

  const client = new Client(
    { name: 'queue-trigger', version: '1.0.0' },
    { capabilities: {} }
  )
  const transport = new StreamableHTTPClientTransport(new URL(baseUrl))

  try {
    await client.connect(transport)
    await client.callTool({
      name: 'process_paper',
      arguments: { arxiv_id: arxivId },
    })
  } catch (err) {
    // Non-fatal: the paper is pending in Supabase; Modal cron will retry
    console.error('[mcp-dispatch] process_paper trigger failed:', err)
  } finally {
    await client.close().catch(() => undefined)
  }
}
