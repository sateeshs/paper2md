// Feature flags — single source of truth for all MCP and UI toggles.
// Server-side flags read from process.env.
// Client-side flags must use NEXT_PUBLIC_* prefix.

export const flags = {
  // MCP server connectivity — true only when the URL env var is set
  USE_PAPER_PROCESSOR_MCP: !!process.env.PAPER_PROCESSOR_MCP_URL,
  USE_PAPER_READER_MCP: !!process.env.PAPER_READER_MCP_URL,
  USE_ARXIV_SEARCH_MCP: !!process.env.ARXIV_SEARCH_MCP_URL,
  USE_MATH_TO_CODE_MCP: !!process.env.MATH_TO_CODE_MCP_URL,

  // UI feature visibility (client-readable via NEXT_PUBLIC_*)
  SHOW_CHAT_INTERFACE: process.env.NEXT_PUBLIC_SHOW_CHAT === 'true',
  SHOW_CODE_TOGGLE: process.env.NEXT_PUBLIC_SHOW_CODE_TOGGLE !== 'false',    // default ON
  SHOW_MATH_LIBRARY_PICKER: process.env.NEXT_PUBLIC_SHOW_LIBRARY_PICKER !== 'false', // default ON
  // Controls Save-to-DB button and artifact review panel in CodePanel.
  // Set NEXT_PUBLIC_SHOW_REVIEW_UI=false to hide it (e.g. read-only / demo mode).
  SHOW_REVIEW_UI: process.env.NEXT_PUBLIC_SHOW_REVIEW_UI !== 'false',        // default ON
  SHOW_VISUALIZE: process.env.NEXT_PUBLIC_SHOW_VISUALIZE === 'true',          // default OFF (opt-in)
} as const

export type FeatureFlags = typeof flags
