/**
 * arxiv-search-mcp — Cloudflare Worker MCP server for ArXiv paper discovery.
 *
 * Ports web/app/api/arxiv/route.ts logic into MCP tools.
 * Also checks Supabase to flag already-processed papers.
 *
 * Tools:
 *   search_papers            Full-text search ArXiv by query string
 *   get_paper_metadata       Fetch metadata for a single ArXiv ID
 *   find_prerequisite_papers Search ArXiv for papers covering prerequisite concepts
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { z } from 'zod'

interface Env {
  SUPABASE_URL: string
  SUPABASE_ANON_KEY: string
}

// ---------------------------------------------------------------------------
// ArXiv Atom XML parser (ported from web/app/api/arxiv/route.ts)
// ---------------------------------------------------------------------------

interface ArxivResult {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  published: string
  already_processed: boolean
}

function decode(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

function parseAtomFeed(xml: string): Omit<ArxivResult, 'already_processed'>[] {
  const entries = xml.match(/<entry>([\s\S]*?)<\/entry>/g) ?? []

  return entries.map((entry) => {
    const id = (entry.match(/<id>.*\/abs\/([^<\s]+)<\/id>/) ?? [])[1] ?? ''
    const arxiv_id = id.replace(/v\d+$/, '')

    const title = decode(
      (entry.match(/<title>([\s\S]*?)<\/title>/) ?? [])[1]?.trim() ?? ''
    )

    const authorMatches = [...entry.matchAll(/<name>([\s\S]*?)<\/name>/g)]
    const authors = authorMatches.map((m) => decode(m[1].trim()))

    const abstract = decode(
      (entry.match(/<summary>([\s\S]*?)<\/summary>/) ?? [])[1]?.trim() ?? ''
    ).replace(/\s+/g, ' ')

    const published =
      (entry.match(/<published>([\s\S]*?)<\/published>/) ?? [])[1]?.slice(0, 10) ?? ''

    return { arxiv_id, title, authors, abstract, published }
  })
}

async function searchArxiv(
  query: string,
  maxResults = 8,
  searchType: 'ti' | 'all' = 'ti'
): Promise<Omit<ArxivResult, 'already_processed'>[]> {
  const q = encodeURIComponent(`${searchType}:${query}`)
  const url = `https://export.arxiv.org/api/query?search_query=${q}&max_results=${maxResults}&sortBy=relevance`

  const res = await fetch(url, { headers: { 'User-Agent': 'paper2md-mcp/1.0' } })
  if (!res.ok) throw new Error(`ArXiv API error: ${res.status}`)

  return parseAtomFeed(await res.text())
}

async function flagProcessed(
  db: SupabaseClient,
  results: Omit<ArxivResult, 'already_processed'>[]
): Promise<ArxivResult[]> {
  if (results.length === 0) return []

  const ids = results.map((r) => r.arxiv_id).filter(Boolean)
  const { data } = await db
    .from('papers')
    .select('arxiv_id, status')
    .in('arxiv_id', ids)

  const processed = new Set(
    (data ?? [])
      .filter((p: { status: string }) => p.status === 'complete')
      .map((p: { arxiv_id: string }) => p.arxiv_id)
  )

  return results.map((r) => ({ ...r, already_processed: processed.has(r.arxiv_id) }))
}

// ---------------------------------------------------------------------------
// Server factory
// ---------------------------------------------------------------------------

function createServer(env: Env): McpServer {
  const server = new McpServer({ name: 'arxiv-search-mcp', version: '1.0.0' })
  const db = createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY)

  // ── Tool: search_papers ──────────────────────────────────────────────────

  server.tool(
    'search_papers',
    'Search ArXiv for papers matching a query. Returns title, abstract, authors, ' +
      'published date, and whether each paper is already processed in the system. ' +
      'already_processed=true means you can call get_paper_sections immediately.',
    {
      query: z.string().min(2).describe('Search terms, e.g. "attention transformers"'),
      max_results: z.number().int().min(1).max(20).default(8),
      search_type: z
        .enum(['ti', 'all'])
        .default('ti')
        .describe('"ti" searches titles only (precise); "all" searches full text (broader)'),
    },
    async ({ query, max_results, search_type }) => {
      let raw: Omit<ArxivResult, 'already_processed'>[]
      try {
        raw = await searchArxiv(query, max_results, search_type)
      } catch (e) {
        return err(`ArXiv search failed: ${e}`)
      }

      const results = await flagProcessed(db, raw)
      return ok({
        query,
        count: results.length,
        results,
      })
    }
  )

  // ── Tool: get_paper_metadata ─────────────────────────────────────────────

  server.tool(
    'get_paper_metadata',
    'Fetch metadata for a single ArXiv paper by ID. Checks whether it is already ' +
      'processed in Supabase. Use this to inspect a paper before deciding to process it.',
    {
      arxiv_id: z.string().describe('ArXiv ID, e.g. "2301.07984" or "2301.07984v2"'),
    },
    async ({ arxiv_id }) => {
      // Strip version suffix
      const id = arxiv_id.replace(/v\d+$/, '')

      // Check Supabase first (instant if already known)
      const { data: existing } = await db
        .from('papers')
        .select('title, abstract, authors, status, created_at, summary_md')
        .eq('arxiv_id', id)
        .maybeSingle()

      // Always fetch fresh metadata from ArXiv
      let arxivMeta: Omit<ArxivResult, 'already_processed'> | null = null
      try {
        const q = encodeURIComponent(id)
        const url = `https://export.arxiv.org/api/query?id_list=${q}`
        const res = await fetch(url, { headers: { 'User-Agent': 'paper2md-mcp/1.0' } })
        if (res.ok) {
          const parsed = parseAtomFeed(await res.text())
          arxivMeta = parsed[0] ?? null
        }
      } catch {
        // Non-fatal — fall back to Supabase data
      }

      if (!arxivMeta && !existing) {
        return err(`Paper ${id} not found on ArXiv or in Supabase`)
      }

      return ok({
        arxiv_id: id,
        title: arxivMeta?.title ?? existing?.title ?? id,
        authors: arxivMeta?.authors ?? existing?.authors ?? [],
        abstract: arxivMeta?.abstract ?? existing?.abstract ?? '',
        published: arxivMeta?.published ?? '',
        already_processed: !!existing && existing.status === 'complete',
        status: existing?.status ?? null,
      })
    }
  )

  // ── Tool: find_prerequisite_papers ───────────────────────────────────────

  server.tool(
    'find_prerequisite_papers',
    'Search ArXiv for introductory papers covering a list of prerequisite concepts ' +
      '(typically from get_prerequisites). Returns deduplicated results ranked by relevance ' +
      'across all concepts. already_processed papers can be read immediately.',
    {
      concepts: z
        .array(z.string())
        .min(1)
        .max(10)
        .describe('Prerequisite concept strings from get_prerequisites, e.g. ["measure theory", "ELBO"]'),
      max_per_concept: z.number().int().min(1).max(5).default(3),
    },
    async ({ concepts, max_per_concept }) => {
      // Search each concept in parallel, cap at 5 concepts to respect ArXiv rate limit
      const limited = concepts.slice(0, 5)

      const searches = await Promise.allSettled(
        limited.map((concept) => searchArxiv(concept, max_per_concept, 'ti'))
      )

      // Merge, deduplicate by arxiv_id
      const seen = new Set<string>()
      const merged: Omit<ArxivResult, 'already_processed'>[] = []

      for (const result of searches) {
        if (result.status === 'fulfilled') {
          for (const paper of result.value) {
            if (paper.arxiv_id && !seen.has(paper.arxiv_id)) {
              seen.add(paper.arxiv_id)
              merged.push(paper)
            }
          }
        }
      }

      const results = await flagProcessed(db, merged)

      return ok({
        concepts_searched: limited,
        concepts_skipped: concepts.slice(5),
        count: results.length,
        results,
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
        JSON.stringify({ status: 'ok', server: 'arxiv-search-mcp' }),
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
