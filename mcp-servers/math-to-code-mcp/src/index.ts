/**
 * math-to-code-mcp — Cloudflare Worker MCP server.
 *
 * Converts stored math blocks (LaTeX + DSPy explanation) into runnable Python
 * code by calling the Anthropic API directly.  Mirrors the paper-reader-mcp
 * and arxiv-search-mcp pattern: TypeScript + Cloudflare Workers + wrangler.
 *
 * Tools:
 *   list_implementable_formulas  — classify blocks in a section
 *   generate_formula_code        — generate Python for one block
 *   generate_section_code        — generate a full module for a section
 *
 * Secrets (wrangler secret put):
 *   SUPABASE_URL
 *   SUPABASE_SERVICE_ROLE_KEY   (needed to write math_code_artifacts)
 *   OPENROUTER_API_KEY
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { z } from 'zod'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Env {
  SUPABASE_URL: string
  SUPABASE_SERVICE_ROLE_KEY: string
  OPENROUTER_API_KEY: string
}

interface MathBlockRow {
  id: string
  order_idx: number
  env_type: string | null
  latex_expr: string | null
  context_before: string | null
  context_after: string | null
  explanation: string | null
  explanation_model: string | null
  sections?: {
    id: string
    title: string | null
    paper_id: string
    papers?: { title: string | null }
  }
}

interface ExplanationV2 {
  what_it_computes?: string
  symbol_meanings?: string
  derivation?: string
  intuition?: string
  prerequisites?: string
  mathematical_significance?: string
}

interface CodeArtifact {
  function_name: string
  imports: string
  code: string
  parameters: unknown
  example_usage: string
  test_code: string | null
  notes: string
}

// ---------------------------------------------------------------------------
// Implementability classifier
// ---------------------------------------------------------------------------

// Only block code generation when what_it_computes is *about* pure symbol definition.
// Avoid "defines" / "denotes" / "where" — they appear in normal computation descriptions
// ("It defines the output as...", "where W_g denotes the gate matrix").
const NOTATION_KW = [
  'is purely notation',
  'is notation for',
  'introduces notation',
  'shorthand for',
  'symbol for',
  'no computation',
  'cannot be computed',
  'not a computation',
]

function isImplementable(row: MathBlockRow): [boolean, string] {
  if (!row.explanation) return [false, 'no explanation — run explain_section_math first']
  if (row.env_type === 'inline' && (row.latex_expr ?? '').length < 10) {
    return [false, 'trivial inline expression']
  }
  let exp: ExplanationV2
  try {
    exp = JSON.parse(row.explanation)
  } catch {
    return [false, 'explanation is not valid JSON']
  }
  const what = (exp.what_it_computes ?? '').toLowerCase()
  if (NOTATION_KW.some(kw => what.includes(kw))) {
    return [false, 'definitional notation, not a computation']
  }
  if (!exp.what_it_computes) return [false, 'what_it_computes is empty']
  return [true, 'has clear input→output computation']
}

// ---------------------------------------------------------------------------
// LLM — call Anthropic API directly (no SDK needed in CF Workers)
// ---------------------------------------------------------------------------

const CODE_GEN_SYSTEM = `You are an expert mathematical programmer and teacher. Given a mathematical formula and its explanation, generate Python code that (1) NUMERICALLY IMPLEMENTS the formula and (2) is fully self-explanatory — someone unfamiliar with the math should understand every symbol and every step just by reading the code.

You MUST respond with valid JSON matching this exact schema:
{
  "function_name": "library_verb_noun (e.g. numpy_compute_cross_entropy)",
  "imports": "import statements, one per line",
  "code": "the complete function definition with docstring and inline comments",
  "parameters": [{"name": "x", "type": "np.ndarray", "description": "..."}],
  "example_usage": "runnable example with print statements showing intermediate values",
  "test_code": "pytest function testing correctness (or null)",
  "notes": "any caveats about numerical stability or edge cases"
}

═══════════════════════════════════════════════
RULE 1 — EVERY SYMBOL MUST BE DOCUMENTED
═══════════════════════════════════════════════

In the docstring, include a "Symbol Guide" section that explains every math symbol with:
- What it is (variable, operator, function)
- What it means in plain English
- Its type/shape (scalar, vector R^n, matrix R^{m×n})
- A concrete example value

Example docstring format:
    Symbol Guide:
        Σ (Sigma)       : summation operator — adds up terms for each index i
                          Example: Σ_{i=1}^{3} x_i = x_1 + x_2 + x_3
        u, v            : input vectors in R^{d_k}, each component ~ N(0,1)
                          Example: u = [0.3, -1.2, 0.8], shape (d_k,)
        E[X]            : expected value of X — average over many random samples
                          Example: E[coin flip] ≈ 0.5
        d_k             : dimensionality of the vectors (int), e.g. d_k=64 in transformers
        <u, v>          : dot product = Σ_i u_i * v_i = u[0]*v[0] + u[1]*v[1] + ...
        Var(X)          : variance of X = E[(X - E[X])^2] — spread of X around its mean

═══════════════════════════════════════════════
RULE 2 — STEP-BY-STEP INLINE COMMENTS
═══════════════════════════════════════════════

Every significant computation line must have an inline comment that:
- Names which part of the formula this implements (using the LaTeX notation)
- Shows what the result looks like with a concrete example value

Example:
    # Σ_{i=1}^{d_k} u_i * v_i  (dot product, the Sigma loop over d_k dimensions)
    dot_product = np.dot(u, v)        # e.g. [0.3,-1.2,0.8]·[0.5,0.2,-0.9] = -0.69

    # E[<u,v>] via Monte Carlo: average over n_samples realizations
    expected_value = np.mean(dot_products)   # should be ≈ 0.0 for zero-mean vectors

═══════════════════════════════════════════════
RULE 3 — MATHEMATICAL NOTATION → CODE
═══════════════════════════════════════════════

These rules are MANDATORY. Every formula element must become real computation.

1. SUMMATION  Σ_{i=1}^{n} f(i)
   → np.sum(array)  OR  explicit for loop.  NEVER skip the sum and return a constant.
   Example: Σ_{i=1}^{d_k} u_i*v_i  →  dot = np.sum(u * v)  # Σ u_i*v_i

2. EXPECTATION  E[X]
   → Monte Carlo: generate n_samples realizations, return np.mean(samples).
   → Accept n_samples: int = 10000 as a parameter.
   → NEVER return the theoretical result directly (e.g. return 0.0 is FORBIDDEN).
   Example: E[u_i*v_i] where u_i,v_i~N(0,1)
     →  samples = np.random.randn(n_samples) * np.random.randn(n_samples)
        return float(np.mean(samples))   # E[u_i*v_i] = E[u_i]*E[v_i] = 0*0 ≈ 0

3. VARIANCE  Var(X)
   → Monte Carlo: generate samples, return np.var(samples).
   Example: Var(<u,v>)  →  dots = np.einsum('ni,ni->n', u_mat, v_mat); return np.var(dots)

4. VECTORS / MATRICES  u, v, W, X
   → np.ndarray parameters, or np.random.randn(n_samples, d_k) for random-vector formulas.

5. DIMENSION  d_k, n, m
   → int parameter; must appear in the body (controls array shape or loop range).

6. DOT PRODUCT  <u,v>  or  u·v  or  u^T v
   → np.dot(u, v)  or  np.sum(u * v, axis=-1)

7. PRODUCTS  ∏_{i} f(i)
   → np.prod(array)  or  accumulate in a loop.

═══════════════════════════════════════════════
RULE 4 — EDUCATIONAL example_usage
═══════════════════════════════════════════════

The example_usage field must:
- Use concrete, small input values (e.g. d_k=4, not d_k=512)
- Print intermediate results with labels so the reader can follow the math
- Show the expected theoretical result alongside the computed result
- Be fully self-contained and runnable (import numpy if needed)

Example pattern:
    import numpy as np
    np.random.seed(42)

    # Set d_k=4 so we can mentally verify: u and v have 4 components each
    result = numpy_compute_expected_dot_product(d_k=4, n_samples=50000)
    print(f"E[<u,v>] with d_k=4: {result:.4f}")
    print(f"Theory says:          0.0000  (zero-mean × zero-mean = 0)")

    result_var = numpy_compute_dot_product_variance(d_k=4, n_samples=50000)
    print(f"Var(<u,v>) with d_k=4: {result_var:.4f}")
    print(f"Theory says:            4.0000  (= d_k)")

═══════════════════════════════════════════════
STRICT PROHIBITIONS
═══════════════════════════════════════════════

- NEVER return a hardcoded constant. Every return value must be computed.
- NEVER write a function body that is just \`return 0.0\` or \`return d_k\`.
- NEVER omit the Σ summation — it must become np.sum() or a loop.
- NEVER omit the E[] expectation — it must become np.mean() over samples.
- Function name: {library}_compute_{short_description} using snake_case
- example_usage must include print() statements showing actual output values

CRITICAL OUTPUT FORMAT:
- Return ONLY the raw JSON object — absolutely no markdown fences, no \`\`\`json, no \`\`\`
- All newlines inside string values MUST be escaped as \\n (backslash + n)
- All backslashes inside string values MUST be escaped as \\\\
- The response must be directly parseable by JSON.parse() with zero modifications`

// OpenRouter uses the OpenAI-compatible chat completions API.
// Default model: google/gemini-2.0-flash-001 (fast, free tier available)
const OPENROUTER_MODEL = 'google/gemini-2.0-flash-001'

async function callLLM(
  apiKey: string,
  prompt: string,
): Promise<CodeArtifact> {
  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
      'HTTP-Referer': 'https://paper2md.vercel.app',
      'X-Title': 'paper2md math-to-code',
    },
    body: JSON.stringify({
      model: OPENROUTER_MODEL,
      max_tokens: 8192,
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: CODE_GEN_SYSTEM },
        { role: 'user', content: prompt },
      ],
    }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`OpenRouter API ${response.status}: ${body}`)
  }

  const data = await response.json() as {
    choices: Array<{ message: { content: string }; finish_reason?: string }>
  }
  const choice = data.choices[0]
  const text = choice?.message?.content ?? ''

  // Detect truncated response (thinking models can exhaust the token budget)
  if (choice?.finish_reason === 'length' || text.length < 100) {
    throw new Error(
      `LLM response truncated (finish_reason=${choice?.finish_reason ?? 'unknown'}, ` +
      `len=${text.length}). The model may have used most tokens for reasoning. ` +
      `Try again or use a simpler formula.`
    )
  }

  // Extract JSON between first '{' and last '}' to strip any markdown fences
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  const extracted = start !== -1 && end !== -1 ? text.slice(start, end + 1) : text.trim()

  // Attempt 1: parse as-is
  try {
    return JSON.parse(extracted) as CodeArtifact
  } catch { /* fall through to repair */ }

  // Attempt 2: fix unescaped newlines/tabs inside JSON string values.
  // Matches each "..." token (respecting \" escapes) and escapes bare control chars.
  try {
    const repaired = extracted.replace(/"((?:[^"\\]|\\.)*)"/gs, (_m, inner: string) => {
      const fixed = inner
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t')
      return `"${fixed}"`
    })
    return JSON.parse(repaired) as CodeArtifact
  } catch {
    throw new Error(`LLM returned non-JSON (len=${text.length}): ${text.slice(-200)}`)
  }
}

function buildPrompt(
  row: MathBlockRow,
  exp: ExplanationV2,
  library: string,
  paperTitle: string,
  sectionTitle: string,
): string {
  return [
    `Paper: ${paperTitle}`,
    `Section: ${sectionTitle}`,
    `Target library: ${library}`,
    ``,
    `Formula (LaTeX):`,
    row.latex_expr ?? '',
    ``,
    `What it computes: ${exp.what_it_computes ?? ''}`,
    `Symbol meanings: ${exp.symbol_meanings ?? ''}`,
    exp.derivation ? `Derivation: ${exp.derivation}` : '',
    exp.intuition ? `Intuition: ${exp.intuition}` : '',
    row.context_before ? `Context before: ${row.context_before}` : '',
    row.context_after ? `Context after: ${row.context_after}` : '',
  ].filter(Boolean).join('\n')
}

// ---------------------------------------------------------------------------
// Supabase helpers
// ---------------------------------------------------------------------------

function db(env: Env): SupabaseClient {
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY)
}

async function fetchBlock(env: Env, blockId: string): Promise<MathBlockRow> {
  const { data, error } = await db(env)
    .from('math_blocks')
    .select(
      'id, order_idx, env_type, latex_expr, context_before, context_after, ' +
      'explanation, explanation_model, ' +
      'sections(id, title, paper_id, papers(title))',
    )
    .eq('id', blockId)
    .maybeSingle()

  if (error) throw new Error(`fetchBlock: ${error.message}`)
  if (!data) throw new Error(`math_block ${blockId} not found`)
  return data as unknown as MathBlockRow
}

async function fetchSectionBlocks(
  env: Env,
  sectionId: string,
): Promise<{ section: { id: string; title: string | null; papers?: { title: string | null } }; blocks: MathBlockRow[] }> {
  const { data: section, error: secErr } = await db(env)
    .from('sections')
    .select('id, title, paper_id, papers(title)')
    .eq('id', sectionId)
    .maybeSingle()

  if (secErr) throw new Error(`fetchSectionBlocks section: ${secErr.message}`)
  if (!section) throw new Error(`section ${sectionId} not found`)

  const { data: blocks, error: blkErr } = await db(env)
    .from('math_blocks')
    .select('id, order_idx, env_type, latex_expr, context_before, context_after, explanation, explanation_model')
    .eq('section_id', sectionId)
    .order('order_idx', { ascending: true })

  if (blkErr) throw new Error(`fetchSectionBlocks blocks: ${blkErr.message}`)
  return { section: section as unknown as { id: string; title: string | null; papers?: { title: string | null } }, blocks: (blocks ?? []) as unknown as MathBlockRow[] }
}

async function persistArtifact(
  env: Env,
  blockId: string,
  sectionId: string,
  library: string,
  artifact: CodeArtifact,
): Promise<string> {
  try {
    // Idempotent: delete existing then insert fresh
    await db(env)
      .from('math_code_artifacts')
      .delete()
      .eq('block_id', blockId)
      .eq('library', library)

    const { data } = await db(env)
      .from('math_code_artifacts')
      .insert({
        block_id: blockId,
        section_id: sectionId,
        library,
        function_name: artifact.function_name,
        imports: artifact.imports,
        code: artifact.code,
        example_usage: artifact.example_usage,
        test_code: artifact.test_code ?? null,
        parameters: artifact.parameters ?? null,
        notes: artifact.notes ?? null,
        generated_model: OPENROUTER_MODEL,
      })
      .select('id')
      .maybeSingle()

    return (data as unknown as { id: string } | null)?.id ?? ''
  } catch {
    // Table may not exist yet (migration pending) — non-fatal, code still returned
    return ''
  }
}

// ---------------------------------------------------------------------------
// MCP server factory
// ---------------------------------------------------------------------------

const PRIORITY_ENVS = new Set(['equation', 'align', 'gather', 'multline'])

function createServer(env: Env): McpServer {
  const server = new McpServer({ name: 'math-to-code-mcp', version: '1.0.0' })

  // ── list_implementable_formulas ──────────────────────────────────────────

  server.tool(
    'list_implementable_formulas',
    'Survey math blocks in a section and classify which are suitable for code generation. ' +
      'Run this before generate_formula_code to identify implementable blocks.',
    { section_id: z.string().describe('UUID of the section from the sections table') },
    async ({ section_id }) => {
      try {
        const { section, blocks } = await fetchSectionBlocks(env, section_id)
        const sectionTitle = section.title ?? ''

        let implementableCount = 0
        const results = blocks.map(raw => {
          const [ok, reason] = isImplementable(raw)
          if (ok) implementableCount++
          let exp: ExplanationV2 = {}
          try { exp = JSON.parse(raw.explanation ?? '{}') } catch { /* ignore */ }
          return {
            block_id: raw.id,
            order_idx: raw.order_idx,
            env_type: raw.env_type ?? '',
            latex_expr: raw.latex_expr ?? '',
            what_it_computes: exp.what_it_computes ?? '',
            implementability: ok ? 'yes' : 'no',
            reason,
          }
        })

        return ok({ section_id, section_title: sectionTitle, blocks: results, implementable_count: implementableCount })
      } catch (e) {
        return err(String(e))
      }
    },
  )

  // ── generate_formula_code ────────────────────────────────────────────────

  server.tool(
    'generate_formula_code',
    'Generate a clean Python function implementing the math formula stored in block_id. ' +
      'Uses Anthropic claude-haiku. Result is cached in math_code_artifacts table.',
    {
      block_id: z.string().describe('UUID from math_blocks table'),
      library: z.enum(['numpy', 'pytorch', 'jax', 'scipy']).default('numpy').describe('Target Python library'),
      include_tests: z.boolean().default(true).describe('Whether to generate a pytest function'),
    },
    async ({ block_id, library, include_tests }) => {
      try {
        const raw = await fetchBlock(env, block_id)
        const [implementable, reason] = isImplementable(raw)
        if (!implementable) return err(`block is not implementable: ${reason}`)

        const section = raw.sections as MathBlockRow['sections'] ?? { id: '', title: null, paper_id: '', papers: { title: null } }
        const paper = section.papers ?? { title: null }
        const sectionId = section.id
        const sectionTitle = section.title ?? ''
        const paperTitle = paper.title ?? ''

        let exp: ExplanationV2 = {}
        try { exp = JSON.parse(raw.explanation ?? '{}') } catch { /* ignore */ }

        const prompt = buildPrompt(raw, exp, library, paperTitle, sectionTitle)
        const artifact = await callLLM(env.OPENROUTER_API_KEY, prompt)
        if (!include_tests) artifact.test_code = null

        const artifactId = await persistArtifact(env, block_id, sectionId, library, artifact)

        return ok({
          block_id,
          latex_expr: raw.latex_expr ?? '',
          library,
          function_name: artifact.function_name,
          imports: artifact.imports,
          code: artifact.code,
          parameters: artifact.parameters,
          example_usage: artifact.example_usage,
          test_code: artifact.test_code,
          notes: artifact.notes,
          prompt_context: {
            formula: raw.latex_expr ?? '',
            what_it_computes: exp.what_it_computes ?? '',
            symbol_meanings: exp.symbol_meanings ?? '',
            context_before: raw.context_before ?? '',
            context_after: raw.context_after ?? '',
            library,
          },
          generated_model: OPENROUTER_MODEL,
          artifact_id: artifactId,
        })
      } catch (e) {
        return err(String(e))
      }
    },
  )

  // ── generate_section_code ────────────────────────────────────────────────

  server.tool(
    'generate_section_code',
    'Generate a complete Python module implementing all implementable formulas in a section. ' +
      'Prioritises display-mode blocks (equation/align/gather). Each formula becomes one function.',
    {
      section_id: z.string().describe('UUID from sections table'),
      library: z.enum(['numpy', 'pytorch', 'jax', 'scipy']).default('numpy'),
      include_tests: z.boolean().default(true),
      max_formulas: z.number().int().min(1).max(20).default(10).describe('Cap on LLM calls'),
    },
    async ({ section_id, library, include_tests, max_formulas }) => {
      try {
        const { section, blocks } = await fetchSectionBlocks(env, section_id)
        const sectionTitle = section.title ?? 'Untitled'
        const paperTitle = (section.papers as { title: string | null } | undefined)?.title ?? ''

        // Priority: display envs first, then others
        const implementable = blocks.filter(b => isImplementable(b)[0])
        const prioritised = [
          ...implementable.filter(b => PRIORITY_ENVS.has(b.env_type ?? '')),
          ...implementable.filter(b => !PRIORITY_ENVS.has(b.env_type ?? '')),
        ].slice(0, max_formulas)

        if (prioritised.length === 0) {
          return ok({ error: 'No implementable formulas found in this section.', section_id, section_title: sectionTitle })
        }

        const allImports = new Set<string>()
        const allFunctions: Array<{ function_name: string; latex_expr: string; code: string }> = []
        const allTests: string[] = []
        const skipReasons: string[] = []

        for (const raw of prioritised) {
          let exp: ExplanationV2 = {}
          try { exp = JSON.parse(raw.explanation ?? '{}') } catch { /* ignore */ }

          const prompt = buildPrompt(raw, exp, library, paperTitle, sectionTitle)
          let artifact: CodeArtifact
          try {
            artifact = await callLLM(env.OPENROUTER_API_KEY, prompt)
            if (!include_tests) artifact.test_code = null
          } catch (e) {
            skipReasons.push(`block ${raw.id}: ${String(e)}`)
            continue
          }

          await persistArtifact(env, raw.id, section_id, library, artifact)

          for (const line of artifact.imports.split('\n')) {
            const t = line.trim()
            if (t) allImports.add(t)
          }
          allFunctions.push({ function_name: artifact.function_name, latex_expr: raw.latex_expr ?? '', code: artifact.code })
          if (include_tests && artifact.test_code) allTests.push(artifact.test_code)
        }

        // Assemble module
        const slug = sectionTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').split('_').slice(0, 4).join('_') || 'formulas'
        const moduleFilename = `${slug}.py`
        const moduleLines = [
          `"""Auto-generated Python module for: ${sectionTitle}`,
          `Paper: ${paperTitle}`,
          `Library: ${library}`,
          '"""',
          '',
          ...[...allImports].sort(),
          '',
          `__all__ = ${JSON.stringify(allFunctions.map(f => f.function_name))}`,
          '',
          ...allFunctions.flatMap(f => [f.code, '']),
        ]

        const testModuleCode = (include_tests && allTests.length > 0)
          ? [`"""Tests for ${moduleFilename}."""`, 'import pytest', `from ${slug} import *`, '', ...allTests].join('\n\n')
          : null

        return ok({
          section_id,
          section_title: sectionTitle,
          module_code: moduleLines.join('\n'),
          module_filename: moduleFilename,
          functions: allFunctions.map(f => ({ function_name: f.function_name, latex_expr: f.latex_expr })),
          test_module_code: testModuleCode,
          generated_model: OPENROUTER_MODEL,
          skipped_count: blocks.length - allFunctions.length,
          skip_reasons: skipReasons,
        })
      } catch (e) {
        return err(String(e))
      }
    },
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
        JSON.stringify({ status: 'ok', server: 'math-to-code-mcp' }),
        { headers: { 'Content-Type': 'application/json' } },
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
