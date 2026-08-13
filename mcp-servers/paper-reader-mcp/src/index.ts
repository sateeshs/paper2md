/**
 * paper-reader-mcp — Cloudflare Worker MCP server for reading paper data.
 *
 * All tools are read-only and use the Supabase anon key (RLS restricts to SELECT).
 * Pattern mirrors road-trip-planner hotels-mcp exactly.
 *
 * Tools:
 *   get_paper_sections        Return paper metadata + ordered section list with math counts
 *   get_section_math          Return full math + algorithm blocks for one section
 *   get_prerequisites         Aggregate prerequisite concepts from a section's math explanations
 *   get_paper_references      Return bibliography citations for a paper
 *   get_section_plain_text    Return the plain text body of one section
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { z } from 'zod'
import { aggregatePrerequisites } from './prerequisites'

interface Env {
  SUPABASE_URL: string
  SUPABASE_ANON_KEY: string
}

// ---------------------------------------------------------------------------
// Supabase helper
// ---------------------------------------------------------------------------

function supabase(env: Env): SupabaseClient {
  return createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY)
}

// ---------------------------------------------------------------------------
// Server factory
// ---------------------------------------------------------------------------

function createServer(env: Env): McpServer {
  const server = new McpServer({ name: 'paper-reader-mcp', version: '1.0.0' })
  const db = supabase(env)

  // ── Tool: get_paper_sections ─────────────────────────────────────────────

  server.tool(
    'get_paper_sections',
    'Return paper metadata and ordered section list with math block counts. ' +
      'Use this first to discover what sections and math content a paper has.',
    {
      arxiv_id: z.string().describe('ArXiv paper ID, e.g. "2301.07984"'),
    },
    async ({ arxiv_id }) => {
      const { data: paper, error: paperErr } = await db
        .from('papers')
        .select('id, title, abstract, authors, status, summary_md, arxiv_id, created_at')
        .eq('arxiv_id', arxiv_id)
        .maybeSingle()

      if (paperErr) return err(`get_paper_sections: ${paperErr.message}`)
      if (!paper) return err(`Paper ${arxiv_id} not found`)

      const { data: sections, error: secErr } = await db
        .from('sections')
        .select('id, order_idx, title, has_math, math_blocks(id)')
        .eq('paper_id', paper.id)
        .order('order_idx', { ascending: true })

      if (secErr) return err(`get_paper_sections sections: ${secErr.message}`)

      const result = {
        arxiv_id,
        title: paper.title,
        abstract: paper.abstract,
        authors: paper.authors,
        status: paper.status,
        section_count: sections?.length ?? 0,
        sections: (sections ?? []).map((s: Record<string, unknown>) => ({
          id: s.id,
          order_idx: s.order_idx,
          title: s.title,
          has_math: s.has_math,
          math_block_count: Array.isArray(s.math_blocks) ? s.math_blocks.length : 0,
        })),
      }

      return ok(result)
    }
  )

  // ── Tool: get_section_math ───────────────────────────────────────────────

  server.tool(
    'get_section_math',
    'Return all math blocks and algorithm blocks for a section, including LaTeX expressions ' +
      'and any existing explanations. Use section IDs from get_paper_sections.',
    {
      section_id: z.string().describe('Section UUID from get_paper_sections'),
    },
    async ({ section_id }) => {
      const { data, error } = await db
        .from('sections')
        .select('*, math_blocks(*), algorithm_blocks(*)')
        .eq('id', section_id)
        .order('order_idx', { referencedTable: 'math_blocks' })
        .order('order_idx', { referencedTable: 'algorithm_blocks' })
        .maybeSingle()

      if (error) return err(`get_section_math: ${error.message}`)
      if (!data) return err(`Section ${section_id} not found`)

      return ok({
        id: data.id,
        title: data.title,
        order_idx: data.order_idx,
        has_math: data.has_math,
        math_blocks: data.math_blocks ?? [],
        algorithm_blocks: data.algorithm_blocks ?? [],
        math_block_count: (data.math_blocks ?? []).length,
        algorithm_block_count: (data.algorithm_blocks ?? []).length,
      })
    }
  )

  // ── Tool: get_prerequisites ──────────────────────────────────────────────

  server.tool(
    'get_prerequisites',
    'Aggregate prerequisite concepts from all math block explanations in a section. ' +
      'Returns a deduplicated, sorted list of concepts the reader needs to understand this section.',
    {
      section_id: z.string().describe('Section UUID from get_paper_sections'),
    },
    async ({ section_id }) => {
      const { data: section, error: secErr } = await db
        .from('sections')
        .select('title')
        .eq('id', section_id)
        .maybeSingle()

      if (secErr) return err(`get_prerequisites: ${secErr.message}`)
      if (!section) return err(`Section ${section_id} not found`)

      const { data: blocks, error: blockErr } = await db
        .from('math_blocks')
        .select('explanation')
        .eq('section_id', section_id)

      if (blockErr) return err(`get_prerequisites blocks: ${blockErr.message}`)

      const prerequisites = aggregatePrerequisites(
        (blocks ?? []).map((b: { explanation: string | null }) => ({ explanation: b.explanation }))
      )

      return ok({
        section_id,
        section_title: section.title,
        prerequisites,
        count: prerequisites.length,
        blocks_with_explanation: (blocks ?? []).filter((b: { explanation: string | null }) => b.explanation).length,
        total_blocks: (blocks ?? []).length,
      })
    }
  )

  // ── Tool: get_paper_references ───────────────────────────────────────────

  server.tool(
    'get_paper_references',
    'Return the bibliography citations for a paper. Citations with arxiv_id set can be ' +
      'passed to process_paper to fetch and analyse the referenced work.',
    {
      arxiv_id: z.string().describe('ArXiv paper ID'),
    },
    async ({ arxiv_id }) => {
      const { data: paper, error: paperErr } = await db
        .from('papers')
        .select('id')
        .eq('arxiv_id', arxiv_id)
        .maybeSingle()

      if (paperErr) return err(`get_paper_references: ${paperErr.message}`)
      if (!paper) return err(`Paper ${arxiv_id} not found`)

      const { data: citations, error: citErr } = await db
        .from('paper_citations')
        .select('*')
        .eq('paper_id', paper.id)
        .order('order_idx', { ascending: true })

      if (citErr) return err(`get_paper_references citations: ${citErr.message}`)

      const cits = citations ?? []
      return ok({
        arxiv_id,
        citation_count: cits.length,
        processable_count: cits.filter((c: Record<string, unknown>) => c.arxiv_id).length,
        citations: cits,
      })
    }
  )

  // ── Tool: get_section_plain_text ─────────────────────────────────────────

  server.tool(
    'get_section_plain_text',
    'Return the plain text body of a single section. Useful for summarising or quoting ' +
      'section content without loading all math blocks.',
    {
      section_id: z.string().describe('Section UUID from get_paper_sections'),
    },
    async ({ section_id }) => {
      const { data, error } = await db
        .from('sections')
        .select('id, title, order_idx, plain_text')
        .eq('id', section_id)
        .maybeSingle()

      if (error) return err(`get_section_plain_text: ${error.message}`)
      if (!data) return err(`Section ${section_id} not found`)

      return ok({
        id: data.id,
        title: data.title,
        order_idx: data.order_idx,
        plain_text: data.plain_text ?? '',
        char_count: (data.plain_text ?? '').length,
      })
    }
  )

  return server
}

// ---------------------------------------------------------------------------
// Response helpers
// ---------------------------------------------------------------------------

function ok(data: unknown): { content: Array<{ type: 'text'; text: string }> } {
  return { content: [{ type: 'text' as const, text: JSON.stringify(data) }] }
}

function err(message: string): { content: Array<{ type: 'text'; text: string }> } {
  return { content: [{ type: 'text' as const, text: JSON.stringify({ error: message }) }] }
}

// ---------------------------------------------------------------------------
// Cloudflare Worker export
// ---------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)

    if (request.method === 'GET' && url.pathname === '/health') {
      return new Response(
        JSON.stringify({ status: 'ok', server: 'paper-reader-mcp' }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 })
    }

    const server = createServer(env)
    const transport = new WebStandardStreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    })
    await server.connect(transport)
    return transport.handleRequest(request)
  },
}
