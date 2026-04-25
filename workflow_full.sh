#!/usr/bin/env bash
#
# workflow_full.sh — Quy trình A-Z cho 1 truyện.
# Crawl (optional) → Rewrite → Wrap §1 → Wrap §2 → Audit → Dry-run → Sync.
#
# Xem quy trình chi tiết: crawler/docs/quy_trinh_a_z.md
#
# Dùng:
#   ./crawler/workflow_full.sh --slug "ten-truyen"                    # dùng truyện đã có local
#   ./crawler/workflow_full.sh --slug "ten-truyen" --url "https://…"  # crawl trước rồi wrap
#
# Tùy chọn:
#   --skip-rewrite       Bỏ bước rewrite chapter
#   --skip-wrap-chapter  Bỏ wrap §1 (summary/highlight/nextPreview)
#   --skip-wrap-novel    Bỏ wrap §2 (editorialReview/characterAnalysis/faq)
#   --skip-audit         Bỏ audit_indexable.py
#   --yes                Tự động confirm bước sync (không prompt)
#   --max-chapters N     Giới hạn số chương khi crawl (mặc định: hết)
#   -h, --help           In help

set -euo pipefail

# ── Đường dẫn ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Helpers ──────────────────────────────────────────────────────────
log()   { printf "\n\033[1;36m━━━ %s ━━━\033[0m\n" "$*"; }
info()  { printf "\033[0;36m→\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
die()   { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

# ── Parse args ───────────────────────────────────────────────────────
SLUG=""
URL=""
MAX_CHAPTERS=""
SKIP_REWRITE=0
SKIP_WRAP_CHAPTER=0
SKIP_WRAP_NOVEL=0
SKIP_AUDIT=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --slug)              SLUG="$2"; shift 2 ;;
    --url)               URL="$2"; shift 2 ;;
    --max-chapters)      MAX_CHAPTERS="$2"; shift 2 ;;
    --skip-rewrite)      SKIP_REWRITE=1; shift ;;
    --skip-wrap-chapter) SKIP_WRAP_CHAPTER=1; shift ;;
    --skip-wrap-novel)   SKIP_WRAP_NOVEL=1; shift ;;
    --skip-audit)        SKIP_AUDIT=1; shift ;;
    --yes|-y)            ASSUME_YES=1; shift ;;
    -h|--help)           usage ;;
    *)                   die "Tham số không hợp lệ: $1 (dùng --help)" ;;
  esac
done

[ -n "$SLUG" ] || die "Thiếu --slug (dùng --help để xem)"

cd "$SCRIPT_DIR"
command -v python3 >/dev/null || die "Thiếu 'python3' trong PATH"

# Auto-activate venv nếu có
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/venv/bin/activate"
fi

# ── In kế hoạch ──────────────────────────────────────────────────────
log "KẾ HOẠCH"
printf "  Slug:              %s\n" "$SLUG"
printf "  URL crawl:         %s\n" "${URL:-(bỏ qua — dùng DB local)}"
printf "  Max chapters:      %s\n" "${MAX_CHAPTERS:-hết}"
printf "  Rewrite chapter:   %s\n" "$([ $SKIP_REWRITE -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Wrap §1 chapter:   %s\n" "$([ $SKIP_WRAP_CHAPTER -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Wrap §2 novel:     %s\n" "$([ $SKIP_WRAP_NOVEL -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Audit:             %s\n" "$([ $SKIP_AUDIT -eq 0 ] && echo "có" || echo "BỎ")"
printf "  Auto-confirm sync: %s\n" "$([ $ASSUME_YES -eq 1 ] && echo "có" || echo "KHÔNG (sẽ hỏi)")"

# ── Bước 1: Crawl (optional) ─────────────────────────────────────────
if [ -n "$URL" ]; then
  log "BƯỚC 1 — CRAWL"
  args=(--url "$URL")
  [ -n "$MAX_CHAPTERS" ] && args+=(--max-chapters "$MAX_CHAPTERS")
  python3 run.py "${args[@]}"
  ok "Crawl xong"
else
  log "BƯỚC 1 — CRAWL (BỎ)"
  info "Không có --url, dùng truyện đã có trong DB local"
fi

# ── Bước 2: Rewrite ──────────────────────────────────────────────────
if [ $SKIP_REWRITE -eq 0 ]; then
  log "BƯỚC 2 — REWRITE CHƯƠNG"
  python3 run.py --rewrite-from-dir "$SLUG"
  ok "Rewrite xong"
else
  log "BƯỚC 2 — REWRITE (BỎ)"
fi

# ── Bước 3: Wrap §1 chapter ──────────────────────────────────────────
if [ $SKIP_WRAP_CHAPTER -eq 0 ]; then
  log "BƯỚC 3 — WRAP §1 (CHAPTER)"
  python3 run.py --wrap-slug "$SLUG"
  ok "Wrap §1 xong"
else
  log "BƯỚC 3 — WRAP §1 (BỎ)"
fi

# ── Bước 4: Wrap §2 novel ────────────────────────────────────────────
if [ $SKIP_WRAP_NOVEL -eq 0 ]; then
  log "BƯỚC 4 — WRAP §2 (NOVEL)"
  python3 run.py --review-slug "$SLUG"
  ok "Wrap §2 xong"
else
  log "BƯỚC 4 — WRAP §2 (BỎ)"
fi

# ── Bước 5: Audit ────────────────────────────────────────────────────
if [ $SKIP_AUDIT -eq 0 ]; then
  log "BƯỚC 5 — AUDIT"
  python3 audit_indexable.py || warn "Audit báo còn thiếu — xem output ở trên"
else
  log "BƯỚC 5 — AUDIT (BỎ)"
fi

# ── Bước 6: Dry-run sync ─────────────────────────────────────────────
log "BƯỚC 6 — DRY-RUN SYNC"
python3 run.py --sync-wrappers-slug "$SLUG" --sync-wrappers-dry-run | head -50 || true
ok "Dry-run OK — không có gì ghi pi4"

# ── Bước 7: Confirm + sync thật ──────────────────────────────────────
log "BƯỚC 7 — ĐẨY LÊN PI4"

if [ $ASSUME_YES -eq 0 ]; then
  printf "\nTiếp tục đẩy lên pi4? [y/N] "
  read -r answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) die "Dừng lại — chưa đẩy pi4. Chạy thủ công: python3 run.py --sync-wrappers-slug \"$SLUG\"" ;;
  esac
fi

python3 run.py --sync-wrappers-slug "$SLUG"

# ── Xong ─────────────────────────────────────────────────────────────
printf "\n"
ok "HOÀN TẤT A-Z cho '$SLUG'"
printf "\n"
printf "Verify:\n"
printf "  open \"https://<domain>/truyen/%s\"\n" "$SLUG"
printf "  curl -s https://<domain>/truyen/%s | grep -A 30 FAQPage\n" "$SLUG"
