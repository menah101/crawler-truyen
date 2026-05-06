#!/usr/bin/env bash
#
# sync_wrappers_prod.sh — Push toàn bộ editorial wrappers (local → prod)
#
# Wrap `python run.py --sync-wrappers` với env prefix prod, KHÔNG đụng .env.
#
# Usage:
#   ./sync_wrappers_prod.sh                    # push all
#   ./sync_wrappers_prod.sh --dry-run          # preview, không gọi API
#   ./sync_wrappers_prod.sh --slug KEYWORD     # filter theo keyword slug
#
# Override prod target qua env:
#   PROD_API_BASE_URL=https://staging.example.com ./sync_wrappers_prod.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROD_API_BASE_URL="${PROD_API_BASE_URL:-https://hongtrantruyen.net}"
PROD_IMPORT_SECRET="${PROD_IMPORT_SECRET:-@tsp-company}"

DRY_RUN=0
SLUG_FILTER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --slug)    SLUG_FILTER="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         printf "✗ Tham số không hợp lệ: %s\n" "$1" >&2; exit 1 ;;
  esac
done

# Auto-activate venv
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  source "$SCRIPT_DIR/venv/bin/activate"
fi

# load_dotenv() default KHÔNG override env vars đã set → 3 biến này thắng .env
export IMPORT_MODE=api
export API_BASE_URL="$PROD_API_BASE_URL"
export IMPORT_SECRET="$PROD_IMPORT_SECRET"

cmd=(python3 run.py)
if [ -n "$SLUG_FILTER" ]; then
  cmd+=(--sync-wrappers-slug "$SLUG_FILTER")
else
  cmd+=(--sync-wrappers)
fi
[ $DRY_RUN -eq 1 ] && cmd+=(--sync-wrappers-dry-run)

printf "\033[1;36m━━━ SYNC WRAPPERS → %s ━━━\033[0m\n" "$PROD_API_BASE_URL"
printf "\033[0;36m→\033[0m %s\n" "${cmd[*]}"
"${cmd[@]}"
