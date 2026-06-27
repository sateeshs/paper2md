#!/usr/bin/env bash
# process_paper.sh — Full pipeline: fetch LaTeX, parse, summarize, explain math, push to DB.
#
# Usage:
#   ./process_paper.sh 2606.24937
#   ./process_paper.sh 2606.24937 --force          # re-process even if complete
#   ./process_paper.sh 2606.24937 --max-math-blocks 300 --max-blocks-per-section 5
#
# Env vars required (or set in .env):
#   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
#   GEMINI_API_KEY (or GROQ_API_KEY / OPENAI_API_KEY)

set -euo pipefail

ARXIV_ID="${1:?Usage: $0 <arxiv_id> [extra summarize_papers.py flags]}"
shift || true

# Defaults for large papers — override with env vars
MAX_BLOCKS="${MAX_BLOCKS:-500}"
MAX_PER_SECTION="${MAX_PER_SECTION:-3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[INFO] Processing arXiv:${ARXIV_ID}"
echo "[INFO] Math cap: ${MAX_BLOCKS} blocks global, ${MAX_PER_SECTION} per section"

python summarize_papers.py \
  --arxiv-id "$ARXIV_ID" \
  --push-supabase \
  --max-math-blocks "$MAX_BLOCKS" \
  --max-blocks-per-section "$MAX_PER_SECTION" \
  "$@"
