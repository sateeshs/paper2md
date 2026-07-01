import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'
import type { SupabaseClient } from '@supabase/supabase-js'

// math_code_artifacts is not yet in the generated types — cast to bypass
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rawFrom = (sb: SupabaseClient, table: string) => (sb as SupabaseClient<any>).from(table)

export const runtime = 'nodejs'

export async function POST(
  req: Request,
  { params }: { params: Promise<{ block_id: string }> }
): Promise<NextResponse> {
  const { block_id } = await params

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const library = typeof body.library === 'string' ? body.library : 'numpy'
  const function_name = typeof body.function_name === 'string' ? body.function_name : ''
  const imports = typeof body.imports === 'string' ? body.imports : ''
  const code = typeof body.code === 'string' ? body.code : ''

  if (!function_name || !code) {
    return NextResponse.json({ error: 'function_name and code are required' }, { status: 400 })
  }

  const supabase = await createServiceClient()

  // Resolve section_id from block_id
  const { data: blockRow } = await supabase
    .from('math_blocks')
    .select('id, section_id')
    .eq('id', block_id)
    .single()

  if (!blockRow) {
    return NextResponse.json({ error: `math_block ${block_id} not found` }, { status: 404 })
  }

  // DELETE+INSERT pattern (idempotent for same block+library)
  await rawFrom(supabase, 'math_code_artifacts')
    .delete()
    .eq('block_id', block_id)
    .eq('library', library)

  let parameters = null
  if (body.parameters !== undefined) {
    parameters = typeof body.parameters === 'string'
      ? (() => { try { return JSON.parse(body.parameters as string) } catch { return body.parameters } })()
      : body.parameters
  }

  const { data, error } = await rawFrom(supabase, 'math_code_artifacts')
    .insert({
      block_id,
      section_id: blockRow.section_id,
      library,
      function_name,
      imports,
      code,
      example_usage: typeof body.example_usage === 'string' ? body.example_usage : null,
      test_code: typeof body.test_code === 'string' ? body.test_code : null,
      parameters,
      notes: typeof body.notes === 'string' ? body.notes : null,
      generated_model: typeof body.generated_model === 'string' ? body.generated_model : null,
    })
    .select('id')
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return NextResponse.json({ saved: true, artifact_id: (data as any)?.id })
}
