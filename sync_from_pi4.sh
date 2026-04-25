#!/usr/bin/env bash
#
# sync_from_pi4.sh — Pattern hybrid: đẩy wrapper tồn đọng lên pi4,
# rồi kéo snapshot DB pi4 về local để chuẩn bị mẻ wrap tiếp theo.
#
# Xem chi tiết: crawler/docs/cach_3_http_sync.md §5
#
# Cách dùng:
#   ./crawler/sync_from_pi4.sh
#
# Cấu hình qua env var (override mặc định bên dưới):
#   PI4_HOST     — ví dụ "pi@192.168.1.50"
#   PI4_APP_DIR  — đường dẫn app trên pi4, ví dụ "/home/pi/truyen-web"
#
# Có thể set trong crawler/.env hoặc export trước khi chạy.

set -euo pipefail

# ── Đường dẫn script + project ───────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_DB="$PROJECT_DIR/prisma/dev.db"

# ── Load env từ crawler/.env nếu có ──────────────────────────────────
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

# ── Cấu hình pi4 (sửa mặc định hoặc set env var) ─────────────────────
PI4_HOST="${PI4_HOST:-pi@192.168.1.50}"
PI4_APP_DIR="${PI4_APP_DIR:-/home/pi/truyen-web}"
PI4_DB_REL="prisma/dev.db"
PI4_TMP="/tmp/dev.db.bak.$$"

# ── Helpers ──────────────────────────────────────────────────────────
log()  { printf "\033[1;36m→\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

cleanup_remote() {
  ssh "$PI4_HOST" "rm -f $PI4_TMP" 2>/dev/null || true
}
trap cleanup_remote EXIT

# ── Precheck ─────────────────────────────────────────────────────────
command -v ssh  >/dev/null || die "Thiếu 'ssh' trong PATH"
command -v scp  >/dev/null || die "Thiếu 'scp' trong PATH"
command -v python3 >/dev/null || die "Thiếu 'python3' trong PATH"

log "Kiểm tra SSH tới $PI4_HOST…"
ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI4_HOST" "echo ok" >/dev/null \
  || die "Không SSH được tới $PI4_HOST (cần SSH key, chưa prompt password)"

# ── Bước 1: Push wrapper local tồn đọng lên pi4 ──────────────────────
log "Push wrapper tồn đọng lên pi4 (để không mất khi đè local)…"
cd "$SCRIPT_DIR"
if python3 run.py --sync-wrappers; then
  ok "Push xong"
else
  warn "Push fail hoặc không có gì để push — tiếp tục"
fi

# ── Bước 2: Backup pi4 DB bằng sqlite3 .backup ───────────────────────
log "Backup pi4 DB qua sqlite3 '.backup' (an toàn với DB đang chạy)…"
ssh "$PI4_HOST" "cd '$PI4_APP_DIR' && sqlite3 '$PI4_DB_REL' \".backup $PI4_TMP\""
ok "Snapshot tạo tại $PI4_HOST:$PI4_TMP"

# ── Bước 3: Kéo về local ─────────────────────────────────────────────
log "Kéo snapshot về $LOCAL_DB…"
mkdir -p "$(dirname "$LOCAL_DB")"
# Đổi tên file cũ trước khi đè (backup phòng hờ)
if [ -f "$LOCAL_DB" ]; then
  mv "$LOCAL_DB" "$LOCAL_DB.prev"
  log "Backup local cũ → $LOCAL_DB.prev"
fi
scp "$PI4_HOST:$PI4_TMP" "$LOCAL_DB"
ok "Snapshot về local thành công"

# ── Bước 4: Dọn file tạm pi4 (EXIT trap sẽ chạy, nhưng xoá tường minh)
ssh "$PI4_HOST" "rm -f $PI4_TMP"

# ── Tổng kết ─────────────────────────────────────────────────────────
printf "\n"
ok "Local đã đồng bộ snapshot pi4"
printf "\n"
printf "Tiếp theo:\n"
printf "  python3 run.py --wrap-slug \"ten truyen\"\n"
printf "  python3 run.py --review-slug \"ten truyen\"\n"
printf "  python3 run.py --sync-wrappers-slug \"ten truyen\"\n"
