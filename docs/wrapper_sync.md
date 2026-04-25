# Wrapper Sync — Đẩy editorial từ local → pi4 qua HTTP

Module: `wrapper_sync.py` + endpoint `/api/admin/wrappers`

## Tại sao cần module này

**Tình huống thực tế:**

- Crawler + LLM (Gemini/Claude) chạy dưới **máy local** — vì pi4 không đủ RAM, bạn không muốn đưa API key LLM lên pi4, hoặc đơn giản là muốn dev cùng một chỗ.
- Next.js + DB production chạy trên **pi4** — nơi user đang tạo bookmark, comment, rating.

**Vấn đề:**

| Cách sync | Vấn đề |
|-----------|--------|
| rsync cả `dev.db` | Ghi đè bookmark/comment/rating của user pi4 |
| SSHFS mount DB từ pi4 | SQLite lock không an toàn qua network FS → nguy cơ corrupt |
| SSH pipe SQL | Phải escape thủ công, phức tạp |
| **HTTP API endpoint ✅** | Sạch, an toàn, có log, có retry |

Module này chọn cách HTTP: crawler local **đọc DB local** → POST payload JSON lên `/api/admin/wrappers` → pi4 dùng Prisma update đúng 6 cột wrapper.

## Kiến trúc

```
┌─────────────── MÁY LOCAL ───────────────┐       ┌─────────── PI4 ────────────┐
│                                         │       │                            │
│  1. Crawl truyện → dev.db (local)       │       │  dev.db (production)      │
│  2. python run.py --review-all          │       │    ├─ Novel                │
│     → wrap LLM → ghi local DB           │       │    ├─ Chapter              │
│  3. python run.py --sync-wrappers       │  HTTP │    ├─ Bookmark ← user data │
│     ├─ SELECT wrappers FROM local DB    │─────→ │    ├─ Comment  ← user data │
│     ├─ Build JSON payload               │ POST  │    └─ Rating   ← user data │
│     └─ POST → /api/admin/wrappers       │       │                            │
│                                         │       │  Next.js endpoint:         │
│  IMPORT_SECRET (shared token)           │       │    UPDATE Novel SET        │
│                                         │       │      editorialReview=...   │
│                                         │       │    UPDATE Chapter SET      │
│                                         │       │      summary=...           │
└─────────────────────────────────────────┘       └────────────────────────────┘
```

Chỉ touch 6 cột:
- `Novel.editorialReview`, `Novel.characterAnalysis`, `Novel.faq`
- `Chapter.summary`, `Chapter.highlight`, `Chapter.nextPreview`

**Không đụng**: bookmark, comment, rating, readingProgress, viewCount, user data bất kỳ.

## Cài đặt

### 1. Trên pi4 — đảm bảo `.env.local` có IMPORT_SECRET

```bash
ssh pi@<ip-pi4>
cd <thu-muc-du-an>
cat .env.local | grep IMPORT_SECRET
```

Nếu chưa có, sinh 1 token dài và add:

```bash
# Sinh token 32 byte
openssl rand -hex 32
# Ví dụ: a3f8b2c9d4e1f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0

echo 'IMPORT_SECRET="a3f8b2c9...f9a0"' >> .env.local
```

Restart Next.js để load env mới:

```bash
pm2 restart all
# hoặc systemctl restart ...
```

### 2. Trên pi4 — deploy code mới

```bash
git pull
pnpm install
npx prisma db push --skip-generate
npx prisma generate
pm2 restart all
```

Kiểm tra endpoint tồn tại:

```bash
curl -X POST http://localhost:3000/api/admin/wrappers -H "Content-Type: application/json" -d '{}'
# → {"error":"Unauthorized"}  ← OK, nghĩa là endpoint sống, chỉ từ chối vì thiếu secret
```

### 3. Trên máy local — `.env` của crawler

File: `crawler/.env` (hoặc env của shell)

```bash
API_BASE_URL="http://192.168.1.50:3000"     # IP LAN của pi4
IMPORT_SECRET="a3f8b2c9...f9a0"              # TRÙNG với pi4
```

Hoặc export tạm thời:

```bash
export API_BASE_URL="http://192.168.1.50:3000"
export IMPORT_SECRET="a3f8b2c9...f9a0"
```

### 4. Kiểm tra kết nối

```bash
cd crawler
python -c "
from config import API_BASE_URL, API_SECRET
print('URL:', API_BASE_URL)
print('Token:', API_SECRET[:8] + '…' if API_SECRET else '(trống)')
"
```

## Quy trình chạy hoàn chỉnh

### Kịch bản: wrap + sync 1 truyện vừa crawl xong

```bash
# ==== LOCAL ====
cd crawler

# (1) Crawl + rewrite như cũ (ghi thẳng local DB)
python run.py --url "https://yeungontinh.baby/truyen/ten-truyen/"

# (2) Wrap §1 — editorial cho từng chương
python run.py --wrap-slug "ten truyen"

# (3) Wrap §2 — review/analysis/FAQ cho novel
python run.py --review-slug "ten truyen"

# (4) Kiểm tra local DB có content chưa
python audit_indexable.py

# (5) Dry-run: xem payload sẽ gửi
python run.py --sync-wrappers-slug "ten truyen" --sync-wrappers-dry-run

# (6) Push thật lên pi4
python run.py --sync-wrappers-slug "ten truyen"
```

Kết quả mong đợi:

```
🔄 Sync editorial wrappers: local → pi4
📦 Local có 1 novel + 50 chapter wrapper
   (filter slug LIKE '%ten truyen%')
→ Push 1 novel…
→ Push chapter batch 1 (50 chương)…

✅ Kết quả sync:
   Novel updated:   1
   Chapter updated: 50
```

### Kịch bản: bulk sync toàn bộ

Sau khi wrap hàng loạt trên local:

```bash
python run.py --review-all              # wrap tất cả novel
# (chapter wrapper thường chạy từng slug vì tốn token)

# Dry-run toàn bộ trước khi push
python run.py --sync-wrappers --sync-wrappers-dry-run | head -50

# Push thật
python run.py --sync-wrappers
```

Với site 100 truyện × 50 chương:
- ~5000 chapter wrapper → chia batch 100 → 50 request
- Mỗi request ~1-2s → tổng ~1-2 phút

## CLI reference

### Qua `run.py` (khuyên dùng)

```bash
python run.py --sync-wrappers                              # sync tất cả
python run.py --sync-wrappers-slug "ten truyen"            # filter slug
python run.py --sync-wrappers --sync-wrappers-dry-run      # dry-run
```

### Standalone `wrapper_sync.py`

Cho use-case phức tạp hơn:

```bash
python wrapper_sync.py --all                               # sync all
python wrapper_sync.py --slug "ten truyen"                 # filter
python wrapper_sync.py --all --novels-only                 # chỉ novel wrappers
python wrapper_sync.py --all --chapters-only               # chỉ chapter wrappers
python wrapper_sync.py --all --batch 50                    # nhỏ batch nếu pi4 chậm
python wrapper_sync.py --all --dry-run                     # preview
```

## Endpoint API

### `POST /api/admin/wrappers`

File: [src/app/api/admin/wrappers/route.js](../../src/app/api/admin/wrappers/route.js)

**Headers**:
- `Content-Type: application/json`
- `X-Import-Secret: <IMPORT_SECRET trong .env.local pi4>`

**Body**:
```json
{
  "novels": [
    {
      "slug": "ten-truyen",
      "editorialReview": "Văn phong nhẹ nhàng...",
      "characterAnalysis": "Nhân vật chính là một cô gái...",
      "faq": "[{\"q\":\"Truyện có bao nhiêu chương?\",\"a\":\"50 chương\"}]"
    }
  ],
  "chapters": [
    {
      "novelSlug": "ten-truyen",
      "number": 1,
      "summary": "Chương mở đầu...",
      "highlight": "Điểm nhấn: cuộc gặp gỡ định mệnh...",
      "nextPreview": "Chương sau sẽ hé lộ..."
    }
  ]
}
```

**Response 200**:
```json
{
  "success": true,
  "novels":   { "updated": 1, "notFound": [] },
  "chapters": { "updated": 50, "notFound": [] }
}
```

**Response 401** — sai `X-Import-Secret`:
```json
{ "error": "Unauthorized" }
```

**Response 400** — body không phải array:
```json
{ "error": "novels/chapters must be arrays" }
```

### Behaviour notes

- Field `undefined` bị **bỏ qua** — không ghi đè giá trị pi4 bằng NULL. Muốn xóa field, phải truyền `null` explicit.
- Novel/Chapter không tìm thấy (slug khác, chưa import) → thêm vào `notFound`, không fail.
- Endpoint tự chạy nhiều `prisma.update` trong 1 request — **không có transaction**: nếu fail giữa chừng, các update trước đó vẫn giữ. Muốn atomic, chia batch nhỏ.

## Gotchas / troubleshooting

### ❌ 401 Unauthorized

Nguyên nhân: `IMPORT_SECRET` local ≠ pi4.

Fix:
```bash
# Pi4
ssh pi@pi4 "cat <app>/.env.local | grep IMPORT_SECRET"

# Local
grep IMPORT_SECRET crawler/.env
```

2 giá trị phải **giống hệt**, kể cả quote.

### ❌ Connection refused / timeout

Nguyên nhân: pi4 không expose port 3000 trên LAN, hoặc firewall chặn.

Fix:
```bash
# Trên pi4, check port 3000 bind 0.0.0.0
ss -tlnp | grep 3000
# Nếu thấy 127.0.0.1:3000 → pi4 chỉ listen localhost
# Sửa PORT / HOST trong script start, hoặc dùng reverse proxy (nginx)
```

Hoặc port-forward qua SSH:
```bash
ssh -L 3000:localhost:3000 pi@pi4 -N &
# Sau đó ở local, set API_BASE_URL=http://localhost:3000
```

### ❌ "Novel không tìm thấy trên pi4"

Nguyên nhân: truyện tồn tại ở local DB nhưng chưa được import lên pi4 (khác slug hoặc chưa crawl trên pi4).

Fix:
- Nếu local đang dùng `/api/admin/import` để push novel → đảm bảo chạy import trước khi sync wrapper.
- Nếu local là DB riêng không sync với pi4 → không chạy được cách này; phải crawl trực tiếp trên pi4.

### ❌ Field bị update thành NULL ngoài ý muốn

Endpoint bỏ qua `undefined` nhưng KHÔNG bỏ qua `null` hay empty string. Nếu bạn truyền `"faq": ""`, pi4 sẽ ghi `""` đè lên dữ liệu cũ. Hàm `collect_novels()` trong `wrapper_sync.py` đã lọc `!= ''` nên không có vấn đề, nhưng nếu tự build payload thì lưu ý.

### ❌ Chạy 2 lần có sao không?

**An toàn** — endpoint idempotent. Chạy 2 lần sync cùng data → pi4 update cùng giá trị → không phá gì.

## Security

- `IMPORT_SECRET` nên dài ≥ 32 ký tự, sinh bằng `openssl rand -hex 32`.
- Endpoint chỉ nên expose qua LAN, hoặc qua HTTPS + reverse proxy nếu ra internet.
- **Không commit** `IMPORT_SECRET` vào git. `.env.local` và `crawler/.env` đã nằm trong `.gitignore`.
- Token share với `/api/admin/import` — nếu đã rotate 1, rotate cả hai.

## Tham khảo

- [adsense_recovery.md](adsense_recovery.md) — playbook tổng hợp §1 + §2 + §5
- [chapter_wrapper.md](chapter_wrapper.md) — cách sinh wrappers §1
- [novel_wrapper.md](novel_wrapper.md) — cách sinh wrappers §2
- [src/app/api/admin/wrappers/route.js](../../src/app/api/admin/wrappers/route.js) — endpoint source
- [crawler/wrapper_sync.py](../wrapper_sync.py) — client source
- [crawler/api_client.py](../api_client.py) — endpoint `import` cùng pattern auth
