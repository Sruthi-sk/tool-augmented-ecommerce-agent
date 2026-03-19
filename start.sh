#!/usr/bin/env bash
# start.sh — set up and run the PartSelect Chat Agent
#
# Usage:
#   ./start.sh            — full setup + start both servers
#   ./start.sh --skip-ingestion  — skip crawl (use existing DB)
#   ./start.sh --ingestion-only  — run ingestion and exit
#
# Prerequisites:
#   - Python 3.11+
#   - Node.js 18+
#   - OPENAI_API_KEY set in backend/.env

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/case-study-main"
SKIP_INGESTION=false
INGESTION_ONLY=false

# ── parse flags ───────────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --skip-ingestion)  SKIP_INGESTION=true ;;
    --ingestion-only)  INGESTION_ONLY=true ;;
  esac
done

# ── helpers ───────────────────────────────────────────────────────────────────
info()  { echo ""; echo "▶  $*"; }
ok()    { echo "   ✓ $*"; }
warn()  { echo "   ⚠  $*"; }
die()   { echo ""; echo "✗  ERROR: $*" >&2; exit 1; }

# ── 1. check prerequisites ────────────────────────────────────────────────────
info "Checking prerequisites"

python3 --version &>/dev/null || die "Python 3 not found. Install Python 3.11+."
node --version    &>/dev/null || die "Node.js not found. Install Node.js 18+."
ok "Python $(python3 --version 2>&1 | awk '{print $2}')"
ok "Node $(node --version)"

# ── 2. backend: virtual environment ──────────────────────────────────────────
info "Setting up Python virtual environment"

if [ ! -d "$BACKEND/.venv" ]; then
  python3 -m venv "$BACKEND/.venv"
  ok "Created .venv"
else
  ok ".venv already exists"
fi

source "$BACKEND/.venv/bin/activate"

# ── 3. backend: dependencies ──────────────────────────────────────────────────
info "Installing Python dependencies"
uv pip install -q -r "$BACKEND/requirements.txt"
ok "pip install done"

# ── 4. playwright: chromium browser ──────────────────────────────────────────
info "Checking Playwright / Chromium"

if python3 -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().chromium" &>/dev/null 2>&1; then
  ok "Chromium already installed"
else
  playwright install chromium
  ok "Chromium installed"
fi

# ── 5. backend: .env ─────────────────────────────────────────────────────────
info "Checking backend .env"

if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  warn ".env created from .env.example — add your OPENAI_API_KEY to $BACKEND/.env and re-run"
  exit 1
fi

if grep -q "your-openai-api-key-here" "$BACKEND/.env"; then
  die "OPENAI_API_KEY is not set in $BACKEND/.env. Edit it and re-run."
fi

ok ".env looks good"

# ── 6. ingestion: build the structured index ──────────────────────────────────
if [ "$SKIP_INGESTION" = false ]; then
  PART_COUNT=0
  if [ -f "$BACKEND/partselect_index.db" ]; then
    PART_COUNT=$(sqlite3 "$BACKEND/partselect_index.db" "SELECT COUNT(*) FROM parts;" 2>/dev/null || echo 0)
  fi

  if [ "$PART_COUNT" -gt 0 ] && [ "$INGESTION_ONLY" = false ]; then
    info "Structured index already has $PART_COUNT parts — skipping ingestion"
    warn "Run with --skip-ingestion=false or delete partselect_index.db to re-crawl"
  else
    info "Building structured index (crawling PartSelect — ~10 min)"
    echo "   Fetching up to 50 parts per category (dishwasher + refrigerator)..."
    cd "$BACKEND"
    python3 -m ingestion.crawl_partselect --limit 50 --concurrency 3
    NEW_COUNT=$(sqlite3 "$BACKEND/partselect_index.db" "SELECT COUNT(*) FROM parts;" 2>/dev/null || echo 0)
    ok "Indexed $NEW_COUNT parts into partselect_index.db"
  fi
fi

if [ "$INGESTION_ONLY" = true ]; then
  info "Ingestion complete. Exiting (--ingestion-only)."
  exit 0
fi

# ── 7. frontend: install dependencies ────────────────────────────────────────
info "Installing frontend dependencies"
cd "$FRONTEND"
npm install --silent
ok "npm install done"

# ── 8. start both servers ─────────────────────────────────────────────────────
info "Starting servers"
echo ""
echo "   Backend  →  http://localhost:8000"
echo "   Frontend →  http://localhost:3000"
echo ""
echo "   Press Ctrl+C to stop both."
echo ""

# trap Ctrl+C and kill both background processes
cleanup() {
  echo ""
  info "Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  ok "Done"
}
trap cleanup INT TERM

# start backend
cd "$BACKEND"
uvicorn main:app --port 8000 --reload &
BACKEND_PID=$!

# brief pause so backend logs don't interleave with frontend startup
sleep 1

# start frontend
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# wait for either process to exit
wait "$BACKEND_PID" "$FRONTEND_PID"
