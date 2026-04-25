#!/usr/bin/env bash
#
# daily_pipeline.sh — Quy trình 1 ngày: crawl 5 truyện từ JSON → wrap → push pi4
#
# Đọc file JSON dạng:
#   { "stories": [{"url": "..."}, {"url": "..."}, ...] }
#
# Quy trình thực hiện cho từng URL:
#   1. Crawl (IMPORT_MODE=local) với --seo — tự lưu DOCX + seo.txt, KHÔNG hỏi
#      BỎ QUA: --images (thumbnail), --shorts (làm sau bằng câu lệnh khác)
#   2. Tạo cover AI (--cover-only) — vì local mode không tự generate cover
#   3. Wrap §1 (chapter wrapper) — summary/highlight/nextPreview
#   4. Wrap §2 (novel wrapper) — editorialReview/characterAnalysis/faq
#
# Sau loop: audit → push novel mới lên pi4 → push wrappers lên pi4.
#
# Usage:
#   ./daily_pipeline.sh                                # JSON theo ngày hôm nay
#   ./daily_pipeline.sh --json data_crawler/2026-03-26.json
#   ./daily_pipeline.sh --skip-crawl                   # bỏ crawl, làm wrap+sync
#   ./daily_pipeline.sh --skip-wrap                    # bỏ wrap, chỉ crawl+sync
#   ./daily_pipeline.sh --skip-sync                    # crawl+wrap, không sync pi4
#   ./daily_pipeline.sh --yes                          # tự confirm tất cả
#   ./daily_pipeline.sh --dry-run                      # preview, không gọi API/LLM
#
# Đề xuất chạy crontab 1h sáng mỗi ngày:
#   0 1 * * * cd /path/to/crawler && ./daily_pipeline.sh --yes >> logs/daily.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Helpers ─────────────────────────────────────────────────────────
log()   { printf "\n\033[1;36m━━━ %s ━━━\033[0m\n" "$*"; }
info()  { printf "\033[0;36m→\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
die()   { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# ── Parse args ──────────────────────────────────────────────────────
JSON_FILE=""
SKIP_CRAWL=0
SKIP_WRAP=0
SKIP_SYNC=0
ASSUME_YES=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --json)        JSON_FILE="$2"; shift 2 ;;
    --skip-crawl)  SKIP_CRAWL=1; shift ;;
    --skip-wrap)   SKIP_WRAP=1; shift ;;
    --skip-sync)   SKIP_SYNC=1; shift ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             die "Tham số không hợp lệ: $1 (dùng --help)" ;;
  esac
done

# ── Default JSON: data_crawler/<today>.json ─────────────────────────
if [ -z "$JSON_FILE" ]; then
  JSON_FILE="data_crawler/$(date +%Y-%m-%d).json"
fi

# ── Precheck ────────────────────────────────────────────────────────
command -v python3 >/dev/null || die "Thiếu python3"
command -v jq >/dev/null      || die "Thiếu jq (brew install jq)"
command -v sqlite3 >/dev/null || die "Thiếu sqlite3"

[ -f "$JSON_FILE" ] || die "Không tìm thấy JSON: $JSON_FILE"

# Auto-activate venv
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  source "$SCRIPT_DIR/venv/bin/activate"
fi

# ── In kế hoạch ─────────────────────────────────────────────────────
URLS=$(jq -r '.stories[].url' "$JSON_FILE")
N_URLS=$(echo "$URLS" | grep -c . || echo 0)

log "KẾ HOẠCH"
printf "  JSON:           %s\n" "$JSON_FILE"
printf "  Số truyện:      %s\n" "$N_URLS"
printf "  Crawl:          %s\n" "$([ $SKIP_CRAWL -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Wrap §1+§2:     %s\n" "$([ $SKIP_WRAP -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Sync pi4:       %s\n" "$([ $SKIP_SYNC -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Auto-confirm:   %s\n" "$([ $ASSUME_YES -eq 1 ] && echo "có" || echo "KHÔNG")"
printf "  Dry-run:        %s\n" "$([ $DRY_RUN -eq 1 ] && echo "CÓ" || echo "không")"

if [ $ASSUME_YES -eq 0 ] && [ -t 0 ]; then
  printf "\nTiếp tục? [Y/n] "
  read -r answer
  case "$answer" in
    n|N|no|NO) die "Dừng theo yêu cầu" ;;
  esac
fi

# ── Tracking ────────────────────────────────────────────────────────
DB_PATH="$SCRIPT_DIR/../prisma/dev.db"
CRAWL_OK=()
CRAWL_FAIL=()
SLUGS=()

slug_from_db_by_url() {
  # Tìm slug trong DB theo sourceUrl (dạng đã trim trailing /)
  local url="${1%/}"
  sqlite3 "$DB_PATH" "SELECT slug FROM Novel WHERE sourceUrl = '$url' LIMIT 1;"
}

# ── Bước 1: Crawl ───────────────────────────────────────────────────
if [ $SKIP_CRAWL -eq 0 ]; then
  log "BƯỚC 1 — CRAWL ${N_URLS} TRUYỆN"
  i=0
  for URL in $URLS; do
    i=$((i+1))
    info "[${i}/${N_URLS}] $URL"

    if [ $DRY_RUN -eq 1 ]; then
      info "   (dry-run, skip crawl)"
      continue
    fi

    # Chạy với </dev/null để không bị block bởi prompt input
    # --seo: sinh seo.txt (tiêu đề YouTube, mô tả, hashtag, tags)
    if python3 run.py --url "$URL" --seo </dev/null; then
      SLUG=$(slug_from_db_by_url "$URL" || true)
      if [ -n "$SLUG" ]; then
        ok "  Slug: $SLUG"
        CRAWL_OK+=("$SLUG")
        SLUGS+=("$SLUG")
      else
        warn "  Không tìm được slug trong DB cho URL này"
        CRAWL_FAIL+=("$URL")
      fi
    else
      warn "  Crawl FAIL"
      CRAWL_FAIL+=("$URL")
    fi
  done

  ok "Crawl xong: ${#CRAWL_OK[@]} OK / ${#CRAWL_FAIL[@]} fail"

  # ── Bước 1b: Tạo cover AI (local mode KHÔNG tự generate cover) ──
  if [ ${#SLUGS[@]} -gt 0 ]; then
    log "BƯỚC 1b — TẠO COVER AI (${#SLUGS[@]} truyện)"
    j=0
    for SLUG in "${SLUGS[@]}"; do
      j=$((j+1))
      info "[${j}/${#SLUGS[@]}] cover: $SLUG"
      python3 run.py --cover-only "$SLUG" </dev/null \
        || warn "  Cover fail cho $SLUG (sẽ dùng default cover)"
    done
  fi
else
  log "BƯỚC 1 — CRAWL (BỎ)"
  # Lấy slug từ JSON URLs (best-effort) để wrap/sync
  for URL in $URLS; do
    SLUG=$(slug_from_db_by_url "$URL" || true)
    [ -n "$SLUG" ] && SLUGS+=("$SLUG")
  done
  info "Tìm được ${#SLUGS[@]} slug có sẵn trong DB"
fi

if [ ${#SLUGS[@]} -eq 0 ]; then
  warn "Không có slug nào để xử lý — dừng"
  exit 0
fi

# ── Bước 2: Wrap §1 + §2 ────────────────────────────────────────────
if [ $SKIP_WRAP -eq 0 ]; then
  log "BƯỚC 2 — WRAP §1 + §2 (${#SLUGS[@]} truyện)"
  i=0
  for SLUG in "${SLUGS[@]}"; do
    i=$((i+1))
    info "[${i}/${#SLUGS[@]}] $SLUG"

    if [ $DRY_RUN -eq 1 ]; then
      info "   (dry-run, skip wrap)"
      continue
    fi

    python3 run.py --wrap-slug "$SLUG"   </dev/null || warn "  Wrap §1 fail"
    python3 run.py --review-slug "$SLUG" </dev/null || warn "  Wrap §2 fail"
  done
  ok "Wrap xong"
else
  log "BƯỚC 2 — WRAP (BỎ)"
fi

# ── Bước 3: Audit ───────────────────────────────────────────────────
log "BƯỚC 3 — AUDIT"
if [ $DRY_RUN -eq 1 ]; then
  info "(dry-run)"
else
  python3 audit_indexable.py | head -60 || true
fi

# ── Bước 4: Sync pi4 ────────────────────────────────────────────────
if [ $SKIP_SYNC -eq 1 ]; then
  log "BƯỚC 4 — SYNC PI4 (BỎ)"
  exit 0
fi

log "BƯỚC 4a — PUSH NOVEL MỚI LÊN PI4"
SLUG_ARGS=("${SLUGS[@]}")
if [ $DRY_RUN -eq 1 ]; then
  info "(dry-run) python3 push_to_pi4.py --slugs ${SLUG_ARGS[*]} --dry-run"
  python3 push_to_pi4.py --slugs "${SLUG_ARGS[@]}" --dry-run </dev/null || warn "Push novel fail"
else
  if [ $ASSUME_YES -eq 0 ] && [ -t 0 ]; then
    printf "\nPush ${#SLUGS[@]} truyện lên pi4? [Y/n] "
    read -r answer
    case "$answer" in
      n|N|no|NO) info "Bỏ qua push novel"; exit 0 ;;
    esac
  fi
  python3 push_to_pi4.py --slugs "${SLUG_ARGS[@]}" </dev/null || warn "Push novel có lỗi"
fi

log "BƯỚC 4b — PUSH WRAPPERS LÊN PI4"
if [ $DRY_RUN -eq 1 ]; then
  info "(dry-run) python3 run.py --sync-wrappers --sync-wrappers-dry-run"
  python3 run.py --sync-wrappers --sync-wrappers-dry-run </dev/null | head -30 || true
else
  python3 run.py --sync-wrappers </dev/null || warn "Sync wrapper có lỗi"
fi

log "HOÀN TẤT"
ok "Đã xử lý ${#SLUGS[@]} truyện trong $JSON_FILE"
[ ${#CRAWL_FAIL[@]} -gt 0 ] && warn "Crawl fail: ${CRAWL_FAIL[*]}"
