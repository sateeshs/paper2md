#!/usr/bin/env bash
# explain_paper_math.sh — Run section-aware math explanation for a single paper.
#
# Usage:
#   ./explain_paper_math.sh 2606.24937
#   ./explain_paper_math.sh 2606.24937 --max-blocks 300 --max-blocks-per-section 5
#
# Env vars required (or set in .env):
#   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
#   GEMINI_API_KEY (or GROQ_API_KEY / OPENAI_API_KEY)
#
# This script fills in missing math block explanations for a paper that is
# already in the Supabase DB. It does NOT re-fetch or re-parse LaTeX.
# Run summarize_papers.py first if the paper isn't in the DB yet.

set -euo pipefail

ARXIV_ID="${1:?Usage: $0 <arxiv_id> [extra explain_math_only.py flags]}"
shift || true

# Default: explain up to 3 blocks per section, cap at 500 total
MAX_BLOCKS="${MAX_BLOCKS:-500}"
MAX_PER_SECTION="${MAX_PER_SECTION:-3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists, else use system python
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[INFO] Explaining math for arXiv:${ARXIV_ID}"
echo "[INFO] Global cap: ${MAX_BLOCKS} blocks, per-section cap: ${MAX_PER_SECTION}"

python explain_math_only.py \
  --arxiv-id "$ARXIV_ID" \
  --max-blocks "$MAX_BLOCKS" \
  --max-blocks-per-section "$MAX_PER_SECTION" \
  "$@"
