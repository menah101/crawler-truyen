# Quy trình A-Z: Từ crawl truyện đến pi4

Tài liệu gộp các bước từ **crawl truyện mới** → **rewrite** → **wrap LLM** → **đẩy lên pi4**. Đây là playbook tổng, các mục chi tiết xem link cuối mỗi bước.

---

## Sơ đồ tổng

```
┌───────────────────────── LOCAL ──────────────────────────┐   ┌──── PI4 ────┐
│                                                          │   │             │
│  1. Crawl URL ──▶ Novel + Chapter (raw)                  │   │             │
│                        │                                 │   │             │
│  2. Rewrite ──▶ Chapter content (đã viết lại)            │   │             │
│                        │                                 │   │             │
│  3. Wrap §1 ──▶ summary / highlight / nextPreview        │   │             │
│                        │                                 │   │             │
│  4. Wrap §2 ──▶ editorialReview / characterAnalysis / faq│   │             │
│                        │                                 │   │             │
│  5. Audit  ──▶ Kiểm tra còn thiếu gì                     │   │             │
│                        │                                 │   │             │
│  6. Sync  ─────────────┼──── HTTP POST ─────────────────▶│── dev.db    │
│                                                          │   │ (6 cột)    │
└──────────────────────────────────────────────────────────┘   └─────────────┘
```

Mỗi bước ghi vào **local DB** trước. Chỉ bước 6 mới đẩy lên pi4.

---

## Prereq — Setup 1 lần

- Crawler: xem [setup.md](setup.md)
- Sync pi4: xem [cach_3_http_sync.md §2](cach_3_http_sync.md#2-setup-1-lần-đầu)
- LLM key (Gemini/Claude): xem [.env](../.env) — `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`
- Endpoint pi4 live:
  ```bash
  curl -X POST http://<pi4-ip>:3000/api/admin/wrappers -d '{}'
  # Mong đợi: {"error":"Unauthorized"}
  ```

---

## Quy trình cho 1 truyện mới

### Bước 1 — Crawl

```bash
cd crawler
python run.py --url "https://<nguon>/<ten-truyen>/"
```

- Script tự detect source từ URL (xem `--list-sources`).
- Ghi vào local `prisma/dev.db`: `Novel` + `Chapter` (content gốc).
- Giới hạn chương: thêm `--max-chapters 50`.
- Test nhanh: `--test` (1 truyện, 3 chương).

📖 Chi tiết: [scraper.md](scraper.md)

### Bước 2 — Rewrite chương

Chapter crawl về thường bị Google xem là duplicate. Rewrite để unique.

```bash
# Rewrite toàn bộ truyện từ DB
python run.py --rewrite-from-dir "ten truyen"

# Hoặc chỉ rewrite vài chương
python run.py --rewrite-from-dir "ten truyen" --rewrite-chapter 1 2 3
```

- Ghi đè `Chapter.content`.
- Có backup tự động. Tắt backup: `--rewrite-no-backup`.

📖 Chi tiết: [rewriter.md](rewriter.md), [chapter_rewriter.md](chapter_rewriter.md)

### Bước 3 — Wrap chapter §1 (LLM)

Sinh `summary`, `highlight`, `nextPreview` cho từng chương — khối `<aside>` + `<section>` trên trang chapter.

```bash
python run.py --wrap-slug "ten truyen"
```

- Chỉ wrap chương **chưa có**. Wrap lại tất cả: thêm `--wrap-redo`.
- Wrap vài chương cụ thể: `--wrap-chapter 1 2 3`.

📖 Chi tiết: [chapter_wrapper.md](chapter_wrapper.md)

### Bước 4 — Wrap novel §2 (LLM)

Sinh `editorialReview`, `characterAnalysis`, `faq` cho novel — khối "Đánh Giá Biên Tập" / "Phân Tích Nhân Vật" / "Câu Hỏi Thường Gặp" trên trang novel.

```bash
python run.py --review-slug "ten truyen"
```

- Chỉ wrap field chưa có. Redo: `--review-redo`.

📖 Chi tiết: [novel_wrapper.md](novel_wrapper.md)

### Bước 5 — Audit

Xem còn thiếu gì trước khi đẩy lên pi4.

```bash
python audit_indexable.py
```

Kết quả 5 nhóm:
- Truyện < 5 chương
- Truyện chưa wrap §2
- Truyện description yếu (< 80 ký tự)
- Chapter chưa wrap §1
- Chapter < 300 từ

Nếu có thiếu → quay lại bước 3/4 cho truyện đó.

📖 Chi tiết: [adsense_recovery.md](adsense_recovery.md)

### Bước 6 — Sync lên pi4

Preview payload (không gọi API):
```bash
python run.py --sync-wrappers-slug "ten truyen" --sync-wrappers-dry-run
```

Đẩy thật:
```bash
python run.py --sync-wrappers-slug "ten truyen"
```

Output mong đợi:
```
📦 Local có 1 novel + 50 chapter wrapper
→ Push 1 novel…
→ Push chapter batch 1 (50 chương)…
✅ Kết quả sync:
   Novel updated:   1
   Chapter updated: 50
```

Nếu thấy `⚠️ Novel không tìm thấy trên pi4`: pi4 chưa có novel này → import qua `/api/admin/import` trước, rồi chạy lại.

📖 Chi tiết: [cach_3_http_sync.md](cach_3_http_sync.md)

### Bước 7 — Verify

```bash
# Check render
open "https://<domain>/truyen/ten-truyen"
# Phải thấy: 3 khối editorial + aside + section trên chapter

# Check JSON-LD SEO
curl -s https://<domain>/truyen/ten-truyen | grep -A 30 "FAQPage"
```

---

## Quy trình one-shot (chạy liền mạch)

Chép dán chạy 1 lần cho 1 truyện:

```bash
cd crawler

SLUG="ten-truyen"
URL="https://nguon.com/$SLUG/"

python run.py --url "$URL"                           && \
python run.py --rewrite-from-dir "$SLUG"             && \
python run.py --wrap-slug "$SLUG"                    && \
python run.py --review-slug "$SLUG"                  && \
python audit_indexable.py                            && \
python run.py --sync-wrappers-slug "$SLUG" --sync-wrappers-dry-run
# Kiểm tra dry-run OK, rồi:
python run.py --sync-wrappers-slug "$SLUG"
```

---

## Quy trình BULK — nhiều truyện

### Kịch bản 1: Đẩy toàn bộ wrapper tồn đọng

Đã wrap nhiều truyện rồi, muốn đẩy hết lên pi4 1 lần:

```bash
cd crawler

python run.py --sync-wrappers-dry-run | head -80     # preview
python run.py --sync-wrappers                        # đẩy hết
```

Xem [cach_3_http_sync.md §4](cach_3_http_sync.md#4-quy-trình-đẩy-nguyên-site-1-lần).

### Kịch bản 2: Wrap toàn site rồi đẩy

```bash
cd crawler

python run.py --wrap-all               # wrap §1 cho mọi novel có chapter chưa wrap
python run.py --review-all             # wrap §2 cho mọi novel
python audit_indexable.py              # kiểm tra
python run.py --sync-wrappers          # đẩy tất cả
```

⚠️ Nhiều truyện × nhiều chương = rất tốn LLM credit. `--wrap-slug` mặc định skip chương đã có wrapper, rerun an toàn. Cân nhắc chạy theo mẻ + ước lượng trước:

```bash
sqlite3 ../prisma/dev.db "SELECT COUNT(*) FROM Chapter WHERE summary IS NULL OR summary=''"
```

### Kịch bản 3: Hybrid (khuyên dùng khi DB lệch)

Kéo snapshot pi4 về làm source of truth, wrap trên local, đẩy ngược lại.

```bash
./crawler/sync_from_pi4.sh     # push tồn đọng + backup pi4 → local
python run.py --wrap-slug "ten truyen"
python run.py --review-slug "ten truyen"
python run.py --sync-wrappers-slug "ten truyen"
```

Xem [cach_3_http_sync.md §5](cach_3_http_sync.md#5-pattern-hybrid-đồng-bộ-pi4--local-trước-khi-wrap).

---

## Cheat sheet tổng

| Bước | Lệnh | Ghi vào đâu |
|------|------|-------------|
| Crawl | `python run.py --url "..."` | local |
| Rewrite | `python run.py --rewrite-from-dir "slug"` | local |
| Wrap chapter §1 | `python run.py --wrap-slug "slug"` | local |
| Wrap novel §2 | `python run.py --review-slug "slug"` | local |
| Audit | `python audit_indexable.py` | (chỉ đọc) |
| Dry-run sync | `python run.py --sync-wrappers-slug "slug" --sync-wrappers-dry-run` | — |
| Sync 1 truyện | `python run.py --sync-wrappers-slug "slug"` | pi4 |
| Sync toàn site | `python run.py --sync-wrappers` | pi4 |
| Hybrid backup | `./crawler/sync_from_pi4.sh` | local ← pi4 |

---

## Khi có vấn đề

| Triệu chứng | Xem |
|-------------|-----|
| Crawl fail | [scraper.md](scraper.md) |
| Rewrite lỗi LLM | [rewriter.md](rewriter.md) |
| Wrap fail (Gemini/Claude) | [chapter_wrapper.md](chapter_wrapper.md), [novel_wrapper.md](novel_wrapper.md) |
| Sync 401 / timeout / notFound | [cach_3_http_sync.md §6](cach_3_http_sync.md#6-troubleshoot) |
| Novel/Chapter lệch pi4 | Dùng hybrid (§5 cach_3_http_sync) |
| AdSense reject lại | [adsense_recovery.md](adsense_recovery.md) |

---

## Tham khảo

- [cach_3_http_sync.md](cach_3_http_sync.md) — HTTP sync chi tiết
- [wrapper_sync.md](wrapper_sync.md) — module sync internals
- [adsense_recovery.md](adsense_recovery.md) — playbook AdSense §1-§5
- [setup.md](setup.md) — setup crawler từ đầu
- [database.md](database.md) — schema DB
