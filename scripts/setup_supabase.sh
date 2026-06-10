#!/usr/bin/env bash
# setup_supabase.sh
# One-time setup script: links Supabase project, runs migrations, generates TS types.
#
# Prerequisites:
#   - Supabase account: https://supabase.com
#   - Node.js 18+  (for npx supabase)
#   - SUPABASE_PROJECT_ID set, or pass it as first argument
#
# Usage:
#   ./scripts/setup_supabase.sh
#   ./scripts/setup_supabase.sh your-project-ref

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Project ref ───────────────────────────────────────────────────────────────
PROJECT_ID="${1:-${SUPABASE_PROJECT_ID:-}}"

if [[ -z "$PROJECT_ID" ]]; then
  warn "SUPABASE_PROJECT_ID not set."
  warn "Find your project ref at:"
  warn "  https://supabase.com/dashboard/project/<ref>/settings/general"
  read -rp "Enter your Supabase project ref: " PROJECT_ID
fi

info "Using project: $PROJECT_ID"

# ── Step 1: Install Supabase CLI (if not already installed) ───────────────────
info "Step 1/5: Checking Supabase CLI..."
if ! command -v supabase &>/dev/null; then
  info "Installing Supabase CLI via npm..."
  npm install -g supabase
else
  info "Supabase CLI already installed: $(supabase --version)"
fi

# ── Step 2: Login ─────────────────────────────────────────────────────────────
info "Step 2/5: Logging in to Supabase..."
info "If a browser window opens, complete the login there."
supabase login

# ── Step 3: Link project ──────────────────────────────────────────────────────
info "Step 3/5: Linking project $PROJECT_ID..."
# Run from repo root
cd "$(dirname "$0")/.."
supabase link --project-ref "$PROJECT_ID"

# ── Step 4: Push migrations ───────────────────────────────────────────────────
info "Step 4/5: Pushing migrations..."
echo ""
warn "This will apply the following migrations to your REMOTE Supabase DB:"
ls supabase/migrations/
echo ""
read -rp "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || error "Aborted."

supabase db push

info "Migrations applied successfully."

# ── Step 5: Generate TypeScript types ─────────────────────────────────────────
info "Step 5/5: Generating TypeScript types..."
supabase gen types typescript \
  --project-id "$PROJECT_ID" \
  > web/lib/supabase/types.ts

info "Types written to web/lib/supabase/types.ts"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Supabase setup complete!                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy your project keys from:"
echo "     https://supabase.com/dashboard/project/$PROJECT_ID/settings/api"
echo ""
echo "  2. Add to Python .env:"
echo "     SUPABASE_URL=https://$PROJECT_ID.supabase.co"
echo "     SUPABASE_SERVICE_ROLE_KEY=<service_role key>"
echo ""
echo "  3. Add to web/.env.local:"
echo "     NEXT_PUBLIC_SUPABASE_URL=https://$PROJECT_ID.supabase.co"
echo "     NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>"
echo ""
echo "  4. Add secrets to GitHub Actions:"
echo "     https://github.com/<owner>/<repo>/settings/secrets/actions"
echo "     Required: GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY,"
echo "               SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY"
echo ""
echo "  5. Test the pipeline locally:"
echo "     python summarize_papers.py --arxiv-id 2301.07984 --push-supabase"
echo ""
