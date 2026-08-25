/**
 * MCP client factories for the paper-processor agent.
 *
 * USE_MCP is true when the two core read servers (reader + arxiv-search) are
 * configured. The processor is optional — it runs on a local GPU box, so the
 * deployed app may not have a reachable URL for it. math-to-code gates only
 * the Code toggle feature.
 */

import { experimental_createMCPClient } from 'ai'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

export const USE_MCP = !!(
  process.env.PAPER_READER_MCP_URL &&
  process.env.ARXIV_SEARCH_MCP_URL
)

export const USE_PAPER_PROCESSOR_MCP = !!process.env.PAPER_PROCESSOR_MCP_URL

export const USE_MATH_TO_CODE_MCP = !!process.env.MATH_TO_CODE_MCP_URL

type MCPClient = Awaited<ReturnType<typeof experimental_createMCPClient>>

/** Create core MCP clients (reader + search), plus processor when configured. */
export async function createAllMCPClients(): Promise<MCPClient[]> {
  const transports: URL[] = [
    new URL(process.env.PAPER_READER_MCP_URL!),
    new URL(process.env.ARXIV_SEARCH_MCP_URL!),
  ]
  if (process.env.PAPER_PROCESSOR_MCP_URL) {
    transports.push(new URL(process.env.PAPER_PROCESSOR_MCP_URL))
  }
  return Promise.all(
    transports.map((url) =>
      experimental_createMCPClient({
        transport: new StreamableHTTPClientTransport(url),
      })
    )
  )
}

/** Create just the math-to-code MCP client (used by /api/math/[block_id]/code). */
export async function createMathToCodeClient(): Promise<MCPClient> {
  return experimental_createMCPClient({
    transport: new StreamableHTTPClientTransport(
      new URL(process.env.MATH_TO_CODE_MCP_URL!)
    ),
  })
}
