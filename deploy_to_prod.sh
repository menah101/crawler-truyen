#!/usr/bin/env bash
#
# deploy_to_prod.sh — Đẩy nội dung đã review xong lên production (hongtrantruyen.net)
#
# Workflow tách giai đoạn:
#   1. Local:  ./daily_pipeline.sh --skip-sync   (crawl + wrap)
#   2. Local:  python tts_generator.py <slug> --voice female  (cho từng slug)
#   3. Admin:  review nội dung trong dev DB / DOCX
#   4. Prod:   ./deploy_to_prod.sh               ← script này
#
# KHÔNG đụng file .env. Prod URL + secret được prefix inline qua env vars,
# `python-dotenv` mặc định không override env đã set, nên `.env` (local mode)
# vẫn nguyên trạng cho lần dev sau.
#
# Usage:
#   ./deploy_to_prod.sh                              # auto: slug từ JSON hôm nay, push novel+wrap+audio
#   ./deploy_to_prod.sh --json data_crawler/2026-05-02.json
#   ./deploy_to_prod.sh --slugs ten-1 ten-2          # bypass JSON, push slug chỉ định
#   ./deploy_to_prod.sh --replace                    # REPLACE mode (sau split/merge chương)
#   ./deploy_to_prod.sh --skip-audio                 # bỏ bước push MP3
#   ./deploy_to_prod.sh --skip-novel --skip-wrap     # chỉ push audio
#   ./deploy_to_prod.sh --voice male                 # voice khác (default female)
#   ./deploy_to_prod.sh --dry-run --yes              # preview
#   ./deploy_to_prod.sh --yes                        # auto-confirm cho cron
#
# Override prod target qua env (rare):
#   PROD_API_BASE_URL=https://staging.example.com ./deploy_to_prod.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Prod target (override được qua env trước khi gọi script) ────────
PROD_API_BASE_URL="${PROD_API_BASE_URL:-https://hongtrantruyen.net}"
PROD_IMPORT_SECRET="${PROD_IMPORT_SECRET:-@tsp-company}"

# ── Helpers ─────────────────────────────────────────────────────────
log()   { printf "\n\033[1;36m━━━ %s ━━━\033[0m\n" "$*"; }
info()  { printf "\033[0;36m→\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
die()   { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# ── Parse args ──────────────────────────────────────────────────────
JSON_FILE=""
SLUGS_OVERRIDE=()
SKIP_NOVEL=0
SKIP_WRAP=0
SKIP_AUDIO=0
REPLACE=0
ASSUME_YES=0
DRY_RUN=0
VOICE="female"
DATE_TAG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --json)        JSON_FILE="$2"; shift 2 ;;
    --slugs)       shift
                   while [ $# -gt 0 ] && [[ "$1" != --* ]]; do
                     SLUGS_OVERRIDE+=("$1"); shift
                   done ;;
    --skip-novel)  SKIP_NOVEL=1; shift ;;
    --skip-wrap)   SKIP_WRAP=1; shift ;;
    --skip-audio)  SKIP_AUDIO=1; shift ;;
    --replace)     REPLACE=1; shift ;;
    --voice)       VOICE="$2"; shift 2 ;;
    --date)        DATE_TAG="$2"; shift 2 ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             die "Tham số không hợp lệ: $1 (dùng --help)" ;;
  esac
done

# ── Precheck ────────────────────────────────────────────────────────
command -v python3 >/dev/null || die "Thiếu python3"
command -v jq >/dev/null      || die "Thiếu jq (brew install jq)"
command -v sqlite3 >/dev/null || die "Thiếu sqlite3"

# Auto-activate venv
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  source "$SCRIPT_DIR/venv/bin/activate"
fi

DB_PATH="$SCRIPT_DIR/../prisma/dev.db"
[ -f "$DB_PATH" ] || die "Không tìm thấy local DB: $DB_PATH"

# ── Resolve slug list ───────────────────────────────────────────────
SLUGS=()

if [ ${#SLUGS_OVERRIDE[@]} -gt 0 ]; then
  SLUGS=("${SLUGS_OVERRIDE[@]}")
  info "Slug từ --slugs: ${#SLUGS[@]}"
else
  if [ -z "$JSON_FILE" ]; then
    JSON_FILE="data_crawler/$(date +%Y-%m-%d).json"
  fi
  [ -f "$JSON_FILE" ] || die "Không tìm thấy JSON: $JSON_FILE (dùng --slugs nếu không có JSON)"

  # Tự suy ra DATE từ tên file (nếu chưa truyền --date)
  if [ -z "$DATE_TAG" ]; then
    base=$(basename "$JSON_FILE" .json)
    if [[ "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
      DATE_TAG="$base"
    fi
  fi

  URLS=$(jq -r '.stories[].url' "$JSON_FILE")
  for URL in $URLS; do
    url_trim="${URL%/}"
    SLUG=$(sqlite3 "$DB_PATH" "SELECT slug FROM Novel WHERE sourceUrl = '$url_trim' LIMIT 1;" || true)
    if [ -n "$SLUG" ]; then
      SLUGS+=("$SLUG")
    else
      warn "Không tìm thấy slug trong local DB cho URL: $URL"
    fi
  done
fi

[ -z "$DATE_TAG" ] && DATE_TAG="$(date +%Y-%m-%d)"

[ ${#SLUGS[@]} -gt 0 ] || die "Không có slug nào để push"

# ── Plan ────────────────────────────────────────────────────────────
log "KẾ HOẠCH PUSH PROD"
printf "  Target:         %s\n" "$PROD_API_BASE_URL"
printf "  JSON / nguồn:   %s\n" "${JSON_FILE:-(--slugs)}"
printf "  Date tag audio: %s\n" "$DATE_TAG"
printf "  Voice:          %s\n" "$VOICE"
printf "  Số slug:        %s\n" "${#SLUGS[@]}"
for S in "${SLUGS[@]}"; do printf "    • %s\n" "$S"; done
printf "  Push novel:     %s\n" "$([ $SKIP_NOVEL -eq 0 ] && echo "có$([ $REPLACE -eq 1 ] && echo " (REPLACE mode)" || echo "")" || echo "BỎ")"
printf "  Push wrappers:  %s\n" "$([ $SKIP_WRAP  -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Push audio:     %s\n" "$([ $SKIP_AUDIO -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Dry-run:        %s\n" "$([ $DRY_RUN -eq 1 ] && echo "CÓ" || echo "không")"

if [ $ASSUME_YES -eq 0 ] && [ -t 0 ]; then
  printf "\nĐẨY ${#SLUGS[@]} truyện lên %s? [y/N] " "$PROD_API_BASE_URL"
  read -r answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) die "Dừng theo yêu cầu" ;;
  esac
fi

# ── Env override prefix dùng cho mọi lệnh python bên dưới ───────────
# load_dotenv() default KHÔNG override env vars đã set → 3 biến này thắng .env
export IMPORT_MODE=api
export API_BASE_URL="$PROD_API_BASE_URL"
export IMPORT_SECRET="$PROD_IMPORT_SECRET"

# ── 1. Push novel ───────────────────────────────────────────────────
if [ $SKIP_NOVEL -eq 0 ]; then
  log "PUSH NOVEL → $PROD_API_BASE_URL"
  cmd=(python3 push_to_pi4.py --slugs "${SLUGS[@]}")
  [ $REPLACE -eq 1 ] && cmd+=(--replace)
  [ $DRY_RUN -eq 1 ] && cmd+=(--dry-run)
  info "${cmd[*]}"
  "${cmd[@]}" </dev/null || warn "Push novel có lỗi"
fi

# ── 2. Push wrappers ────────────────────────────────────────────────
if [ $SKIP_WRAP -eq 0 ]; then
  log "PUSH WRAPPERS → $PROD_API_BASE_URL"
  cmd=(python3 run.py --sync-wrappers)
  [ $DRY_RUN -eq 1 ] && cmd+=(--sync-wrappers-dry-run)
  info "${cmd[*]}"
  "${cmd[@]}" </dev/null || warn "Sync wrappers có lỗi"
fi

# ── 3. Push audio ───────────────────────────────────────────────────
if [ $SKIP_AUDIO -eq 0 ]; then
  log "PUSH AUDIO ($VOICE) → $PROD_API_BASE_URL"
  cmd=(python3 push_audio_to_pi4.py --slugs "${SLUGS[@]}" --voice "$VOICE")
  [ $DRY_RUN -eq 1 ] && cmd+=(--dry-run)
  info "${cmd[*]}"
  "${cmd[@]}" </dev/null || warn "Push audio có lỗi"
fi

log "HOÀN TẤT"
ok "Đã đẩy ${#SLUGS[@]} truyện lên $PROD_API_BASE_URL"
