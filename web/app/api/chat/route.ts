import { streamText, experimental_createMCPClient } from 'ai'
import type { LanguageModel } from 'ai'
import { createOpenAI } from '@ai-sdk/openai'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { USE_MCP, createAllMCPClients } from '@/lib/mcp-clients'
import { PAPER_AGENT_SYSTEM_PROMPT } from '@/lib/paper-agent-prompt'
import type { Message } from 'ai'

// OpenRouter via OpenAI-compatible API — free tier model
const openrouter = createOpenAI({
  baseURL: 'https://openrouter.ai/api/v1',
  apiKey: process.env.OPENROUTER_API_KEY ?? '',
  headers: {
    'HTTP-Referer': 'https://paper2md.vercel.app',
    'X-Title': 'paper2md',
  },
})
const CHAT_MODEL = 'google/gemini-2.0-flash-001'

export const runtime = 'nodejs'
export const maxDuration = 60

// Keep the last N messages to avoid blowing the context window.
// MCP tool results are 5–15 KB JSON blobs each.
const MAX_HISTORY = 14

export async function POST(req: Request): Promise<Response> {
  if (!process.env.OPENROUTER_API_KEY) {
    return Response.json(
      { error: 'OPENROUTER_API_KEY is not configured. Add it to web/.env.local.' },
      { status: 500 }
    )
  }

  const { messages }: { messages: Message[] } = await req.json()

  // Window history: keep first user message + recent tail
  const windowed: Message[] =
    messages.length <= MAX_HISTORY
      ? messages
      : [messages[0], ...messages.slice(-(MAX_HISTORY - 1))]

  // Strip tool-invocation blobs from older assistant turns to reduce tokens
  const trimmed: Message[] = windowed.map((msg, idx) => {
    const isRecent = idx >= windowed.length - 2
    if (isRecent || msg.role !== 'assistant') return msg
    const content = typeof msg.content === 'string'
      ? msg.content
      : '[tool results omitted]'
    return { ...msg, content }
  })

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let tools: Record<string, any> = {}
  let mcpClients: Array<{ close(): Promise<void> }> = []

  if (USE_MCP) {
    const clients = await createAllMCPClients()
    mcpClients = clients
    const toolSets = await Promise.all(clients.map((c) => c.tools()))
    tools = Object.assign({}, ...toolSets)
  }

  const result = streamText({
    model: openrouter(CHAT_MODEL) as unknown as LanguageModel,
    system: PAPER_AGENT_SYSTEM_PROMPT,
    messages: trimmed,
    tools,
    // Budget: discover(1) + process(1) + read sections(1) + explain math(1) + prereqs(1)
    // + search(1) + find prereq papers(1) = ~7 per paper; 20 gives room for multi-paper sessions
    maxSteps: 20,
    onError: ({ error }) => {
      console.error('[chat] streamText error:', error)
    },
    onStepFinish: ({ toolResults }) => {
      for (const tr of toolResults ?? []) {
        const r = tr as { toolName?: string }
        console.log(`[tool] ${r.toolName ?? 'unknown'} called`)
      }
    },
    onFinish: async ({ usage, finishReason }) => {
      console.log(`[chat] finishReason=${finishReason} tokens=${JSON.stringify(usage)}`)
      if (mcpClients.length > 0) {
        await Promise.allSettled(mcpClients.map((c) => c.close()))
      }
    },
  })

  return result.toDataStreamResponse()
}
