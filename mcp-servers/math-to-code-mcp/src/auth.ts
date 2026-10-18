/**
 * Bearer-token auth for this MCP server.
 *
 * These endpoints hold Supabase credentials and can spend LLM quota, so they
 * must not be callable by anyone who learns the URL. Worker URLs are not
 * secrets — they leak through logs, browser history, and request records.
 *
 * Fails closed: if MCP_AUTH_TOKEN is not configured the server refuses every
 * request rather than silently serving unauthenticated traffic. A deploy that
 * forgets the secret breaks loudly instead of quietly being open.
 *
 * Duplicated per worker on purpose — each is an independently deployable
 * project with its own tsconfig `include`, so a shared import would not build.
 */

/** Constant-time string comparison; avoids leaking the token via timing. */
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return diff === 0
}

function deny(status: number, error: string): Response {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: {
      'Content-Type': 'application/json',
      // Signals the scheme without hinting at the token's value.
      'WWW-Authenticate': 'Bearer',
    },
  })
}

/**
 * Returns a Response to send back when the request must be rejected, or null
 * when the caller is authorised and the request should proceed.
 */
export function requireAuth(
  request: Request,
  env: { MCP_AUTH_TOKEN?: string }
): Response | null {
  const expected = env.MCP_AUTH_TOKEN?.trim()

  if (!expected) {
    console.error('MCP_AUTH_TOKEN is not configured — refusing all requests')
    return deny(503, 'Server is not configured for authentication')
  }

  const header = request.headers.get('Authorization') ?? ''
  const match = /^Bearer\s+(.+)$/i.exec(header.trim())

  if (!match) {
    return deny(401, 'Missing or malformed Authorization header')
  }
  if (!safeEqual(match[1].trim(), expected)) {
    return deny(401, 'Invalid token')
  }

  return null
}
