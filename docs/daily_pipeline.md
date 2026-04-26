# Daily Pipeline — Crawl 5 truyện/ngày + sync pi4

Module: `daily_pipeline.sh` + `push_to_pi4.py`

Tự động hoá quy trình **1 ngày**: đọc list URL từ JSON → crawl 5 truyện (chỉ DOCX + DB local) → wrap §1+§2 → audit → push novel mới + wrapper lên pi4.

## File JSON đầu vào

`crawler/data_crawler/YYYY-MM-DD.json`:

```json
{
  "stories": [
    {"url": "https://vivutruyen.net/dan-quen-anh-full/"},
    {"url": "https://vivutruyen.net/hoa-chua-tan-full/"},
    {"url": "https://vivutruyen.net/4-nam-thu-tinh-trong-ong-nghiem-full/"},
    {"url": "https://vivutruyen.net/kho-bau-quoc-gia/"},
    {"url": "https://vivutruyen.net/bua-yeu-vi-chanh-tuyet/"}
  ]
}
```

Tên file = ngày crawl. Khi không truyền `--json`, script tự dùng `data_crawler/$(date +%Y-%m-%d).json`.

## Cách chạy

```bash
cd crawler

# Mặc định: JSON theo ngày hôm nay, có hỏi confirm
./daily_pipeline.sh

# Auto-confirm cho cron
./daily_pipeline.sh --yes

# Chỉ định JSON khác
./daily_pipeline.sh --json data_crawler/2026-03-26.json --yes

# Dry-run preview (không gọi API/LLM)
./daily_pipeline.sh --dry-run --yes
```

### Skip steps

```bash
./daily_pipeline.sh --skip-crawl   # bỏ crawl, làm wrap+sync trên slug đã có
./daily_pipeline.sh --skip-wrap    # bỏ wrap, chỉ crawl+sync
./daily_pipeline.sh --skip-sync    # crawl+wrap, không push pi4
```

## Quy trình 4 bước

```
┌──────────────────────────────────────────────────┐
│  BƯỚC 1 — CRAWL + SEO (IMPORT_MODE=local)        │
│                                                  │
│  for URL in JSON:                                │
│    python run.py --url "$URL" --seo              │
│    # tự lưu DOCX + seo.txt, không hỏi            │
│    # KHÔNG --images (thumbnail), KHÔNG --shorts  │
│    # ghi Novel + Chapter vào local prisma/dev.db │
│                                                  │
│  BƯỚC 1b — COVER AI                              │
│  for SLUG in crawled_slugs:                      │
│    python run.py --cover-only "$SLUG"            │
│    # local mode không tự gen cover, phải gọi tay │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  BƯỚC 2 — WRAP §1 + §2 (LLM, ghi local)          │
│                                                  │
│  for SLUG in crawled_slugs:                      │
│    python run.py --wrap-slug   "$SLUG"  # §1     │
│    python run.py --review-slug "$SLUG"  # §2     │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  BƯỚC 3 — AUDIT                                  │
│                                                  │
│  python audit_indexable.py | head -60            │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  BƯỚC 4 — SYNC PI4                               │
│                                                  │
│  4a. python push_to_pi4.py --slugs <slugs>       │
│      → POST /api/admin/import (tạo Novel mới)    │
│                                                  │
│  4b. python run.py --sync-wrappers               │
│      → POST /api/admin/wrappers (update 6 cột)   │
└──────────────────────────────────────────────────┘
```

## `push_to_pi4.py` — utility riêng

Khác `wrapper_sync.py`:

| Endpoint | Mục đích | Module |
|----------|---------|--------|
| `/api/admin/import` | TẠO novel + chapter mới | `push_to_pi4.py` |
| `/api/admin/wrappers` | UPDATE 6 cột editorial | `wrapper_sync.py` |

Idempotent: nếu novel đã tồn tại trên pi4 → response `note: "novel_resumed"`, chỉ thêm chapter mới.

```bash
# Push 1 truyện
python push_to_pi4.py --slug "ten-truyen"

# Push nhiều
python push_to_pi4.py --slugs ten-truyen-1 ten-truyen-2

# Push novel có chapter mới trong 24h qua
python push_to_pi4.py --since-hours 24

# Push toàn bộ published (cẩn thận — payload to)
python push_to_pi4.py --all

# Dry-run preview
python push_to_pi4.py --since-hours 24 --dry-run
```

## Cấu hình bắt buộc

`crawler/.env`:

```bash
# LLM cho rewrite/wrap
GEMINI_API_KEY=AIza...

# Pi4 endpoint
API_BASE_URL="http://192.168.1.50:4000"
IMPORT_SECRET="<chia sẻ với pi4 .env.local>"
```

`crawler/config.py`:

```python
REWRITE_PROVIDER = "gemini"   # nếu chưa đổi từ "deepseek"/"anthropic"
```

## Schedule cron

Chạy 1h sáng mỗi ngày (sau khi đã prep file JSON ngày hôm đó):

```cron
0 1 * * * cd /home/user/truyen-web/crawler && ./daily_pipeline.sh --yes >> logs/daily.log 2>&1
```

Hoặc launch manual mỗi ngày khi sẵn sàng.

## Hành vi đặc biệt

### Stdin redirect `</dev/null`

Mỗi `python3 run.py --url ...` được chạy với `</dev/null` để đảm bảo:
- Không bị treo bởi `input("...")` prompt
- `sys.stdin.isatty()` returns False → các prompt tự skip

### Slug detection

Sau khi crawl URL `https://vivutruyen.net/dan-quen-anh-full/`, script query:
```sql
SELECT slug FROM Novel WHERE sourceUrl = 'https://vivutruyen.net/dan-quen-anh-full' LIMIT 1
```

(URL bỏ trailing `/` để match với cách crawler ghi `sourceUrl`).

### Bao gồm vs bỏ qua

Script GỌI tự động:
- **Crawl + rewrite chương** (mặc định)
- **DOCX export** (auto trong non-tty mode, theo `DOCX_EXPORT_ENABLED`)
- **SEO** (`--seo` flag) — sinh `seo.txt` (tiêu đề/mô tả/hashtag YouTube)
- **Cover AI** (`--cover-only`) — vì local mode không tự gen cover, phải gọi tay sau crawl

Script BỎ QUA (user tự chạy sau bằng câu lệnh khác):
- **Thumbnail (16:9)**: `python run.py --images-only "ten-truyen"`
- **Shorts (9:16 + hook)**: `python run.py --shorts-only "ten-truyen"`

Lý do: thumbnail + shorts tốn nhiều LLM/HF credit + thời gian (~5 phút/truyện), tách ra để chạy chọn lọc cho truyện hot.

## Troubleshooting

### Crawl fail nhưng pipeline vẫn tiếp tục

Script chỉ wrap + sync những URL crawl thành công. Slug fail được liệt kê ở cuối:

```
⚠ Crawl fail: https://...
```

Re-run thủ công cho URL fail rồi `--skip-crawl` để wrap+sync:

```bash
python run.py --url "https://failed-url/"
./daily_pipeline.sh --skip-crawl --yes
```

### push_to_pi4 lỗi `notFound`

Pi4 chưa có novel này → `/api/admin/import` sẽ tạo mới. Nếu vẫn báo notFound nghĩa là endpoint `/api/admin/import` deploy chưa OK trên pi4. Verify:

```bash
curl -X POST $API_BASE_URL/api/admin/import \
  -H "X-Import-Secret: $IMPORT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"novel": {}, "chapters": []}'
# Mong đợi: 400 với "Dữ liệu không hợp lệ" — KHÔNG phải 404
```

### Wrap §2 báo skip nhưng audit vẫn thấy thiếu

Bug đã fix tại [novel_wrapper.py:270-273](../novel_wrapper.py#L270-L273). Nếu vẫn gặp:

```bash
python run.py --review-slug "ten-truyen" --review-redo
```

### Pi4 chapter khác local sau khi split/merge

`/api/admin/import` mặc định **RESUME mode** — SKIP chapter trùng `(novelId, number)`. Sau khi split (4 → 10 chương) hoặc merge (5 → 4 chương) ở local, pi4 vẫn giữ cấu trúc cũ.

Fix: chạy `push_to_pi4.py` với `--replace`:

```bash
# Push lại các novel đã split/merge với REPLACE mode (xoá chapter cũ trên pi4)
python push_to_pi4.py --slug "ten-truyen" --replace

# Hoặc push tất cả novel có chapter mới trong 24h qua, REPLACE mode
python push_to_pi4.py --since-hours 24 --replace

# Đồng bộ toàn site (cẩn thận — payload to)
python push_to_pi4.py --all --replace
```

⚠️ REPLACE mode KHÔNG đụng Bookmark/Comment/Rating (đều ở Novel level). Nhưng `Chapter.viewCount` reset về fake views mới (vì delete + insert).

## Tham khảo

- [quy_trinh_a_z.md](quy_trinh_a_z.md) — playbook tổng (manual)
- [scraper.md](scraper.md) — chi tiết crawl
- [chapter_wrapper.md](chapter_wrapper.md) — wrap §1
- [novel_wrapper.md](novel_wrapper.md) — wrap §2
- [wrapper_sync.md](wrapper_sync.md) — push wrapper local → pi4
- [api_client.md](api_client.md) — endpoint `/api/admin/import`
- [audit.md](audit.md) — kiểm tra content nguy cơ AdSense
