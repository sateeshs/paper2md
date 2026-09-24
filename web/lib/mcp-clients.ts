/**
 * MCP client factories for the paper-processor agent.
 *
 * All MCP servers require a shared bearer token (MCP_AUTH_TOKEN): they can
 * read the database and spend LLM quota, and their URLs are not secrets.
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

/**
 * Auth header sent to every MCP server.
 *
 * Throws rather than falling back to an unauthenticated request — a missing
 * token is a deployment error, and silently dropping the header would make
 * every call fail with a confusing 401 from the server instead.
 */
function authHeaders(): Record<string, string> {
  const token = process.env.MCP_AUTH_TOKEN?.trim()
  if (!token) {
    throw new Error(
      'MCP_AUTH_TOKEN is not set — required to call any MCP server. ' +
        'Set it in the environment and match it with the value configured on each server.'
    )
  }
  return { Authorization: `Bearer ${token}` }
}

function transportFor(url: URL): StreamableHTTPClientTransport {
  return new StreamableHTTPClientTransport(url, {
    requestInit: { headers: authHeaders() },
  })
}

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
      experimental_createMCPClient({ transport: transportFor(url) })
    )
  )
}

/** Create just the math-to-code MCP client (used by /api/math/[block_id]/code). */
export async function createMathToCodeClient(): Promise<MCPClient> {
  return experimental_createMCPClient({
    transport: transportFor(new URL(process.env.MATH_TO_CODE_MCP_URL!)),
  })
}
