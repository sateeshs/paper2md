/**
 * MCP client factories for the paper2md agent.
 *
 * USE_MCP is true only when all three core server URLs are configured.
 * The math-to-code client is optional — it gates only the Code toggle feature.
 */

import { experimental_createMCPClient } from 'ai'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

export const USE_MCP = !!(
  process.env.PAPER_PROCESSOR_MCP_URL &&
  process.env.PAPER_READER_MCP_URL &&
  process.env.ARXIV_SEARCH_MCP_URL
)

export const USE_MATH_TO_CODE_MCP = !!process.env.MATH_TO_CODE_MCP_URL

type MCPClient = Awaited<ReturnType<typeof experimental_createMCPClient>>

/** Create all three core MCP clients in parallel. */
export async function createAllMCPClients(): Promise<MCPClient[]> {
  return Promise.all([
    experimental_createMCPClient({
      transport: new StreamableHTTPClientTransport(
        new URL(process.env.PAPER_PROCESSOR_MCP_URL!)
      ),
    }),
    experimental_createMCPClient({
      transport: new StreamableHTTPClientTransport(
        new URL(process.env.PAPER_READER_MCP_URL!)
      ),
    }),
    experimental_createMCPClient({
      transport: new StreamableHTTPClientTransport(
        new URL(process.env.ARXIV_SEARCH_MCP_URL!)
      ),
    }),
  ])
}

/** Create just the math-to-code MCP client (used by /api/math/[block_id]/code). */
export async function createMathToCodeClient(): Promise<MCPClient> {
  return experimental_createMCPClient({
    transport: new StreamableHTTPClientTransport(
      new URL(process.env.MATH_TO_CODE_MCP_URL!)
    ),
  })
}
