# Cách 3 — HTTP API Sync (Crawler local → DB pi4)

Tài liệu này hướng dẫn **từng bước đơn giản** cách đẩy editorial wrappers (editorialReview, faq, summary, highlight…) từ DB local lên DB pi4 qua HTTP.

> Chi tiết kỹ thuật module xem [wrapper_sync.md](wrapper_sync.md).

---

## 1. Ý tưởng chính

Có **2 DB tách rời**:

```
MÁY LOCAL                          PI4 (production)
─────────                          ────────────────
dev.db (local)                     dev.db (pi4)
 ├─ Novel / Chapter content         ├─ Novel / Chapter content
 └─ Wrapper fields (LLM)            ├─ Wrapper fields (LLM)
                                    └─ Bookmark / Comment / Rating  ← user tạo
```

Crawler + LLM chạy local (tiết kiệm API key, CPU). Sau đó đẩy **chỉ 6 cột wrapper** lên pi4 qua HTTP:
- Novel: `editorialReview`, `characterAnalysis`, `faq`
- Chapter: `summary`, `highlight`, `nextPreview`

Bookmark / comment / rating của user trên pi4 **không bị đụng**.

### Quan trọng — 2 bước RIÊNG BIỆT, KHÔNG tự động

```
Bước A (ghi LOCAL)           Bước B (đẩy PI4)
─────────────────            ───────────────
python run.py --wrap-slug    python run.py --sync-wrappers
python run.py --review-slug  hoặc --sync-wrappers-slug
        │                             │
        ▼                             ▼
  dev.db local                  pi4 qua HTTP
```

Chạy `--wrap-slug` **KHÔNG tự đẩy lên pi4**. Muốn pi4 có data, phải gõ `--sync-wrappers` thủ công.

---

## 2. Setup 1 lần đầu

### 2.1. Pi4 — tạo token chung

```bash
ssh pi@<ip-pi4>
cd <thu-muc-du-an>

# Nếu chưa có IMPORT_SECRET, sinh mới
openssl rand -hex 32
# → a3f8b2c9d4e1f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0

echo 'IMPORT_SECRET="a3f8b2c9…f9a0"' >> .env.local
```

Nếu pi4 **đã có** `IMPORT_SECRET` (do dùng `/api/admin/import`) → dùng lại, không đổi.

### 2.2. Pi4 — deploy code mới

```bash
git pull
pnpm install
npx prisma db push --skip-generate
npx prisma generate
pm2 restart all
```

### 2.3. Pi4 — kiểm tra endpoint

```bash
curl -X POST http://localhost:3000/api/admin/wrappers \
  -H "Content-Type: application/json" \
  -d '{}'
# Mong đợi: {"error":"Unauthorized"}   ← tốt, endpoint sống
```

Nếu thấy **404** → chưa pull code / chưa restart.

### 2.4. Local — cấu hình env

File `crawler/.env`:
```bash
API_BASE_URL="http://192.168.1.50:3000"      # IP LAN pi4
IMPORT_SECRET="a3f8b2c9…f9a0"                 # TRÙNG pi4
```

### 2.5. Local — test kết nối

```bash
cd crawler

curl -s -X POST $API_BASE_URL/api/admin/wrappers \
  -H "X-Import-Secret: $IMPORT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"novels":[],"chapters":[]}'
# Mong đợi: {"success":true,"novels":{"updated":0,...},"chapters":...}
```

- **401** → token lệch giữa local và pi4.
- **Connection refused** → pi4 đang listen 127.0.0.1, xem [§5 Troubleshoot](#5-troubleshoot).

---

## 3. Quy trình làm 1 truyện

```bash
cd crawler

# BƯỚC 1 — Crawl nội dung (ghi local)
python run.py --url "https://.../ten-truyen/"

# BƯỚC 2 — Wrap chapter §1 (LLM → local)
python run.py --wrap-slug "ten truyen"

# BƯỚC 3 — Wrap novel §2 (LLM → local)
python run.py --review-slug "ten truyen"

# BƯỚC 4 — Xem trước payload (tùy chọn, không gọi API)
python run.py --sync-wrappers-slug "ten truyen" --sync-wrappers-dry-run

# BƯỚC 5 — Đẩy lên pi4
python run.py --sync-wrappers-slug "ten truyen"
```

Output bước 5 kiểu:
```
📦 Local có 1 novel + 50 chapter wrapper
→ Push 1 novel…
→ Push chapter batch 1 (50 chương)…

✅ Kết quả sync:
   Novel updated:   1
   Chapter updated: 50
```

Sau đó mở `https://<domain>/truyen/ten-truyen` là thấy.

### Chú ý về `--sync-wrappers-slug`

Dùng SQL `LIKE '%ten truyen%'` → nếu slug có trùng prefix/suffix (ví dụ `ten-truyen`, `ten-truyen-2`, `ten-truyen-ngoai-truyen`) thì **cả nhóm được đẩy cùng lúc**. Thường không sao, chỉ cần biết.

---

## 4. Quy trình đẩy NGUYÊN SITE 1 lần

Khi đã wrap xong nhiều truyện và muốn đẩy tất cả lên pi4 cùng lúc:

```bash
cd crawler

# BƯỚC 1 — Xem trước (không gọi API)
python run.py --sync-wrappers-dry-run | head -80

# BƯỚC 2 — Đẩy hết
python run.py --sync-wrappers
```

### Script làm gì?

1. Quét **toàn bộ** DB local, lấy mọi Novel + Chapter có ít nhất 1 field wrapper.
2. POST **1 request** cho toàn bộ novel.
3. POST chapter theo **batch 100 chương/request**.

Ví dụ: 50 truyện × 200 chương = 10.000 chapter
→ 1 request novel + 100 request chapter = **101 HTTP call** (không phải 10.050).

### Nếu pi4 chậm / RAM thấp

Giảm batch:
```bash
python wrapper_sync.py --all --batch 30
```

### Chỉ đẩy 1 loại

```bash
python wrapper_sync.py --all --novels-only      # bỏ chapter
python wrapper_sync.py --all --chapters-only    # bỏ novel
```

### Chạy lại nếu fail

Endpoint idempotent — update cùng giá trị 2 lần không sao. Nếu batch 5/10 lỗi, các batch 1-4 đã ghi, chạy lại lệnh là tiếp tục được.

---

## 5. Pattern hybrid: đồng bộ pi4 → local trước khi wrap

Dùng khi DB local đã lệch nhiều so với pi4 (slug khác, thiếu novel, id lệch). Thay vì vật lộn với `notFound`, kéo snapshot pi4 về làm nguồn gốc chung.

### 5.1. Ý tưởng

```
PI4 ──snapshot file──▶ LOCAL     (bước 1: kéo về)
                       │
                       ▼
                 wrap + review    (bước 2: LLM ghi local)
                       │
LOCAL ──HTTP POST─────▶ PI4       (bước 3: đẩy 6 cột wrapper)
```

| Chiều | Công cụ | Vì sao an toàn |
|-------|---------|----------------|
| PI4 → LOCAL | `sqlite3 .backup` + `scp` | Đè local không sao — local là dev env |
| LOCAL → PI4 | HTTP endpoint | Chỉ update 6 cột. Bookmark/comment user tạo **trong lúc bạn wrap** không bị mất |

**⚠️ KHÔNG BAO GIỜ** `scp local → pi4` file `dev.db` — sẽ xoá toàn bộ user data pi4 tạo trong thời gian wrap.

### 5.2. Quy trình

```bash
cd crawler

# BƯỚC 1 — Push wrapper tồn đọng TRƯỚC khi đè local
# (nếu local đang có wrapper chưa đẩy, bước sau sẽ xoá mất)
python run.py --sync-wrappers || echo "(không có gì để push)"

# BƯỚC 2 — Backup DB pi4 (dùng .backup, an toàn với DB đang chạy)
ssh pi@pi4 "cd /path/to/app && sqlite3 prisma/dev.db '.backup /tmp/dev.db.bak'"
scp pi@pi4:/tmp/dev.db.bak ./path/to/local/dev.db
ssh pi@pi4 "rm /tmp/dev.db.bak"

# BƯỚC 3 — Wrap như bình thường
python run.py --wrap-slug "ten truyen"
python run.py --review-slug "ten truyen"

# BƯỚC 4 — Đẩy lên pi4
python run.py --sync-wrappers-slug "ten truyen"
```

### 5.3. Vì sao không dùng `scp dev.db` trực tiếp?

Nếu pi4 đang ghi (user tạo bookmark), file `dev.db` có WAL chưa flush → `scp` lấy file **partial**, mở ra có thể corrupt. Lệnh `sqlite3 '.backup'` an toàn với DB đang chạy.

Hoặc có thể rsync cả 3 file cùng lúc (ít khuyên dùng):
```bash
rsync pi@pi4:.../dev.db* ./path/to/local/
```

### 5.4. Cảnh báo

**Thứ tự bắt buộc**: push wrapper local **trước**, rồi mới kéo snapshot pi4 về. Nếu kéo trước, wrapper local chưa đẩy sẽ mất.

**Dữ liệu user lọt vào máy local**: snapshot pi4 có toàn bộ bookmark/comment/rating thật.
- Không commit `dev.db` (đã trong `.gitignore`).
- Xoá snapshot cũ khi không cần.
- Không chạy trên máy chia sẻ.

**Stale**: snapshot là chụp tại thời điểm backup. Pi4 vẫn nhận chapter mới qua crawler khác (nếu có) trong lúc bạn wrap — những chapter mới đó chưa có wrapper cho tới chu kỳ sau.

### 5.5. Script gợi ý

Tạo `crawler/sync_from_pi4.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PI4_HOST="pi@192.168.1.50"
PI4_APP="/path/to/app"
LOCAL_DB="./path/to/dev.db"

echo "→ Push wrapper tồn đọng lên pi4…"
python run.py --sync-wrappers || echo "  (không có gì để push)"

echo "→ Backup pi4 DB…"
ssh "$PI4_HOST" "cd $PI4_APP && sqlite3 prisma/dev.db '.backup /tmp/dev.db.bak'"
scp "$PI4_HOST:/tmp/dev.db.bak" "$LOCAL_DB"
ssh "$PI4_HOST" "rm /tmp/dev.db.bak"

echo "✅ Local đã đồng bộ snapshot pi4"
```

Dùng:
```bash
chmod +x crawler/sync_from_pi4.sh
./crawler/sync_from_pi4.sh
```

---

## 6. Troubleshoot

### ❌ `401 Unauthorized`

Token local ≠ pi4:
```bash
ssh pi@pi4 "grep IMPORT_SECRET /path/to/app/.env.local"
grep IMPORT_SECRET crawler/.env
```
Phải giống hệt (kể cả dấu nháy).

### ❌ `Connection refused`

Pi4 listen `127.0.0.1` thay vì `0.0.0.0`:
```bash
# Trên pi4
ss -tlnp | grep 3000
```

**Giải pháp A** — sửa Next.js listen `0.0.0.0`:
```bash
next start -H 0.0.0.0
```

**Giải pháp B** — SSH tunnel:
```bash
# Trên local (chạy nền)
ssh -L 3000:localhost:3000 pi@pi4 -N &
export API_BASE_URL=http://localhost:3000
```

### ❌ `Novel không tìm thấy trên pi4`

Output:
```
⚠️  Novel không tìm thấy trên pi4: ['ten-truyen-khac']
```

Nguyên nhân:
- Chưa import novel lên pi4 qua `/api/admin/import`.
- Slug pi4 lệch local (ví dụ pi4 có suffix random do trùng slug).

→ Import novel lên pi4 trước, rồi chạy lại `--sync-wrappers`.

### ❌ `Timeout`

Batch quá lớn. Giảm:
```bash
python wrapper_sync.py --all --batch 30
```

---

## 7. Verify sau sync

### A. Check DB pi4

```bash
ssh pi@pi4
cd <app>
sqlite3 prisma/dev.db

sqlite> SELECT slug, LENGTH(editorialReview), LENGTH(faq)
        FROM Novel WHERE slug = 'ten-truyen';
# Mong đợi: ten-truyen|1250|856

sqlite> SELECT COUNT(*) FROM Chapter
        WHERE summary IS NOT NULL
        AND novelId IN (SELECT id FROM Novel WHERE slug='ten-truyen');
# Mong đợi: 50 (nếu novel có 50 chương)
```

### B. Check render

Mở `https://<domain>/truyen/ten-truyen`:
- Có khối "Đánh Giá Biên Tập"
- Có khối "Phân Tích Nhân Vật"
- Có khối "Câu Hỏi Thường Gặp"

Mở trang chapter: có `<aside>` trên + `<section>` dưới content.

### C. Check JSON-LD SEO

```bash
curl -s https://<domain>/truyen/ten-truyen | grep -A 50 "FAQPage"
```
Phải có `"@type":"FAQPage"` + array `mainEntity`.

---

## 8. Cheat sheet

| Mục đích | Lệnh |
|----------|------|
| Wrap chapter 1 truyện (local) | `python run.py --wrap-slug "ten truyen"` |
| Wrap novel 1 truyện (local) | `python run.py --review-slug "ten truyen"` |
| Wrap novel toàn site (local) | `python run.py --review-all` |
| Dry-run sync 1 truyện | `python run.py --sync-wrappers-slug "ten truyen" --sync-wrappers-dry-run` |
| Đẩy 1 truyện lên pi4 | `python run.py --sync-wrappers-slug "ten truyen"` |
| Dry-run sync toàn site | `python run.py --sync-wrappers-dry-run` |
| **Đẩy TOÀN BỘ lên pi4** | `python run.py --sync-wrappers` |
| Chỉ đẩy novel (bỏ chapter) | `python wrapper_sync.py --all --novels-only` |
| Chỉ đẩy chapter | `python wrapper_sync.py --all --chapters-only` |
| Batch nhỏ (pi4 yếu) | `python wrapper_sync.py --all --batch 30` |
| Đồng bộ snapshot pi4 → local | `./crawler/sync_from_pi4.sh` (xem §5) |

---

## 9. Security

- `IMPORT_SECRET` ≥ 32 ký tự (`openssl rand -hex 32`).
- Không commit (đã có trong `.gitignore`).
- Dùng trong LAN là OK. Mở ra internet → bắt buộc HTTPS + reverse proxy.
- Rotate token: sửa pi4 `.env.local` + local `crawler/.env` đồng thời, restart pi4.

---

## 10. Giới hạn

- **Không atomic**: nếu batch lỗi giữa chừng, các item trước đã ghi. Workaround: batch nhỏ + chạy lại (idempotent).
- **Không tạo novel mới**: endpoint chỉ update. Novel phải tồn tại pi4 trước (import qua `/api/admin/import`).
- **Không tự động**: sync là thủ công. Mỗi lần wrap xong phải chạy `--sync-wrappers` để đẩy.

---

## Tham khảo

- [wrapper_sync.md](wrapper_sync.md) — chi tiết module
- [chapter_wrapper.md](chapter_wrapper.md) — §1 LLM wrapper chapter
- [novel_wrapper.md](novel_wrapper.md) — §2 LLM wrapper novel
- [adsense_recovery.md](adsense_recovery.md) — playbook tổng
- [src/app/api/admin/wrappers/route.js](../../src/app/api/admin/wrappers/route.js) — source endpoint
