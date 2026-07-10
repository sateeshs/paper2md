'use client'

import { useState } from 'react'

// ---------------------------------------------------------------------------
// Python syntax highlighter — display only; does NOT affect copy or download
// ---------------------------------------------------------------------------

const PYTHON_KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
  'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
  'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
  'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
  'while', 'with', 'yield',
])

const PYTHON_BUILTINS = new Set([
  'abs', 'all', 'any', 'bool', 'bytes', 'callable', 'chr', 'dict',
  'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter', 'float',
  'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'hex',
  'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list',
  'locals', 'map', 'max', 'min', 'next', 'object', 'oct', 'open', 'ord',
  'pow', 'print', 'property', 'range', 'repr', 'reversed', 'round', 'set',
  'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super',
  'tuple', 'type', 'vars', 'zip',
])

type TokenType = 'keyword' | 'builtin' | 'string' | 'comment' | 'number' | 'decorator' | 'plain'

interface Token {
  text: string
  type: TokenType
}

const TOKEN_PATTERNS: Array<[RegExp, TokenType | 'word']> = [
  [/^(#[^\n]*)/, 'comment'],
  [/^("""[\s\S]*?"""|'''[\s\S]*?''')/, 'string'],
  [/^("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/, 'string'],
  [/^(@[\w.]+)/, 'decorator'],
  [/^(\b0[xX][0-9a-fA-F]+|\b\d+\.?\d*(?:[eE][+-]?\d+)?)/, 'number'],
  [/^([A-Za-z_]\w*)/, 'word'],
]

function tokenizePython(code: string): Token[] {
  const tokens: Token[] = []
  let pos = 0
  while (pos < code.length) {
    let matched = false
    for (const [pattern, rawType] of TOKEN_PATTERNS) {
      const m = code.slice(pos).match(pattern)
      if (m) {
        let type: TokenType
        if (rawType === 'word') {
          if (PYTHON_KEYWORDS.has(m[1])) type = 'keyword'
          else if (PYTHON_BUILTINS.has(m[1])) type = 'builtin'
          else type = 'plain'
        } else {
          type = rawType
        }
        tokens.push({ text: m[1], type })
        pos += m[1].length
        matched = true
        break
      }
    }
    if (!matched) {
      tokens.push({ text: code[pos], type: 'plain' })
      pos++
    }
  }
  return tokens
}

const TOKEN_CLASS: Record<TokenType, string> = {
  keyword:   'text-blue-500 dark:text-blue-400',
  builtin:   'text-teal-500 dark:text-teal-400',
  string:    'text-green-600 dark:text-green-400',
  comment:   'text-zinc-400 dark:text-zinc-500 italic',
  number:    'text-orange-500 dark:text-orange-400',
  decorator: 'text-yellow-600 dark:text-yellow-400',
  plain:     '',
}

const CODE_LABELS = new Set(['IMPORTS', 'FUNCTION', 'EXAMPLE USAGE', 'TESTS'])

function HighlightedCode({ code }: { code: string }) {
  const tokens = tokenizePython(code)
  return (
    <>
      {tokens.map((token, i) =>
        token.type === 'plain'
          ? <span key={i}>{token.text}</span>
          : <span key={i} className={TOKEN_CLASS[token.type]}>{token.text}</span>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

export type CodeSection = {
  label: string
  content: string
  defaultOpen: boolean
}

export interface CodeArtifactForSave {
  block_id: string
  library: string
  function_name?: string
  imports?: string
  code?: string
  example_usage?: string
  test_code?: string | null
  parameters?: unknown
  notes?: string
  generated_model?: string
}

interface CodePanelProps {
  sections: CodeSection[]
  functionName: string
  generatedModel: string | null
  /** When provided, shows a "Save to DB" button */
  artifact?: CodeArtifactForSave
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export function CodePanel({ sections, functionName, generatedModel, artifact }: CodePanelProps) {
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave() {
    if (!artifact) return
    setSaveState('saving')
    setSaveError(null)
    try {
      const res = await fetch(`/api/math/${artifact.block_id}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(artifact),
      })
      const data = await res.json()
      if (!res.ok) {
        setSaveError((data as { error?: string }).error ?? 'Save failed')
        setSaveState('error')
      } else {
        setSaveState('saved')
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Network error')
      setSaveState('error')
    }
  }

  return (
    <div className="divide-y divide-zinc-200 dark:divide-zinc-700 bg-white dark:bg-zinc-950">
      {/* Header bar: function name + save button */}
      <div className="flex items-center gap-3 px-4 py-2">
        {(generatedModel || functionName) && (
          <p className="text-xs text-zinc-400 dark:text-zinc-500 flex-1 truncate">
            {functionName}
            {generatedModel ? ` · ${generatedModel}` : ''}
          </p>
        )}
        {artifact && (
          <button
            onClick={handleSave}
            disabled={saveState === 'saving' || saveState === 'saved'}
            className="shrink-0 text-xs border border-zinc-200 dark:border-zinc-700 rounded px-2.5 py-1 text-zinc-500 dark:text-zinc-400 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors disabled:opacity-50"
          >
            {saveState === 'saving' ? 'Saving…'
              : saveState === 'saved' ? '✓ Saved'
              : 'Save to DB'}
          </button>
        )}
      </div>

      {saveState === 'error' && saveError && (
        <p className="px-4 py-2 text-xs text-red-600 bg-red-50 dark:bg-red-950">{saveError}</p>
      )}

      {sections.map((section) => (
        <CollapsibleSection key={section.label} section={section} />
      ))}
    </div>
  )
}

function CollapsibleSection({ section }: { section: CodeSection }) {
  const [open, setOpen] = useState(section.defaultOpen)
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(section.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-2 bg-zinc-50 dark:bg-zinc-900">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-mono font-semibold text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors flex-1 text-left"
        >
          <span>{open ? '▾' : '▸'}</span>
          <span>{section.label}</span>
        </button>
        <button
          onClick={handleCopy}
          className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors shrink-0"
          aria-label={`Copy ${section.label}`}
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      {open && (
        <pre className="px-4 py-3 text-xs font-mono text-zinc-700 dark:text-zinc-300 overflow-x-auto whitespace-pre-wrap break-words leading-relaxed">
          {CODE_LABELS.has(section.label)
            ? <HighlightedCode code={section.content} />
            : section.content}
        </pre>
      )}
    </div>
  )
}
