# AdSense Recovery — Khắc phục "Low-value content"

Playbook khi AdSense reject với lý do **"Nội dung có giá trị thấp"** (Low-value content / Thin content).

Lý do thường gặp:
1. Nội dung crawl + rewrite vẫn bị Google phát hiện là duplicate.
2. Mỗi trang truyện chỉ có metadata + danh sách chương → không có nội dung editorial riêng.
3. Có trang admin/auth được index → Google coi là "không có giá trị cho user".
4. Có truyện < 5 chương nhưng vẫn index → soft 404.
5. Thiếu E-E-A-T pages (About, Privacy, Terms, Contact, DMCA).

Site này đã implement §1 + §2 + §5. §3 + §4 cần làm thủ công.

---

## Tổng quan 5 bước

| # | Vấn đề | Giải pháp | Trạng thái |
|---|--------|-----------|------------|
| §1 | Chapter page chỉ có content rewrite → vẫn thin | `chapter_wrapper.py` sinh summary/highlight/nextPreview | ✅ Done |
| §2 | Novel page chỉ có metadata + list → thin | `novel_wrapper.py` sinh review/analysis/FAQ | ✅ Done |
| §3 | Thiếu E-E-A-T pages | Viết About / Privacy / Terms / Contact / DMCA | ⚠️ Thủ công |
| §4 | Ad-to-content ratio cao trong lúc review | Tắt AdSense script tạm thời | ⚠️ Thủ công |
| §5 | Admin/auth index + truyện mỏng soft 404 | robots.js + noindex metadata + `audit_indexable.py` | ✅ Done |

---

## Quy trình chạy sau khi bị reject

### Bước 1 — Audit trạng thái hiện tại

```bash
cd crawler
python audit_indexable.py
```

Kết quả in 5 nhóm:
- Truyện < 5 chương (thin novels)
- Truyện chưa wrap §2 (thiếu editorialReview / characterAnalysis / faq)
- Truyện có description yếu (< 80 ký tự)
- Chapter chưa wrap §1 (thiếu summary + highlight)
- Chapter < 300 từ (quá ngắn)

Xuất JSON nếu cần pipe vào script khác:

```bash
python audit_indexable.py --json > audit.json
```

Đổi ngưỡng:

```bash
python audit_indexable.py --min-chapters 10 --min-words 500
```

### Bước 2 — Wrap chapter (§1)

Chạy cho từng truyện hoặc all:

```bash
# Per-slug
python run.py --wrap-slug "ten truyen"

# Từ thư mục crawl (nếu chưa import DB)
python run.py --wrap-from-dir docx_output/2026-04-19/ten-truyen

# Chỉ vài chương
python run.py --wrap-slug "ten truyen" --wrap-chapter 1 2 3

# Ghi đè
python run.py --wrap-slug "ten truyen" --wrap-redo
```

Chi tiết: [chapter_wrapper.md](chapter_wrapper.md).

Cột DB được update: `Chapter.summary`, `Chapter.highlight`, `Chapter.nextPreview`.

### Bước 3 — Wrap novel (§2)

```bash
# Một truyện
python run.py --review-slug "ten truyen"

# Từ thư mục
python run.py --review-from-dir docx_output/2026-04-19/ten-truyen

# Toàn bộ DB (skip truyện đã có)
python run.py --review-all

# Ghi đè
python run.py --review-all --review-redo

# Rate-limit
python run.py --review-all --sleep 3.0
```

Chi tiết: [novel_wrapper.md](novel_wrapper.md).

Cột DB được update: `Novel.editorialReview`, `Novel.characterAnalysis`, `Novel.faq`.

Sau khi chạy, trang `/truyen/[slug]` render:
- Khối "Đánh Giá Biên Tập"
- Khối "Phân Tích Nhân Vật"
- Khối "Câu Hỏi Thường Gặp" (details collapsible)
- `<script type="application/ld+json">` schema FAQPage

### Bước 4 — Ẩn truyện mỏng (nếu còn)

Sau khi wrap, nếu audit vẫn liệt kê truyện < 5 chương, 2 lựa chọn:

**A. Bổ sung chương** — crawl thêm từ nguồn. `--watch-download` chỉ tải chương mới cho **những truyện đã add vào watchlist**, không tự bổ sung chương cũ:

```bash
# Add truyện vào watchlist trước (nếu chưa)
python run.py --watch-add "https://nguon.com/ten-truyen/"

# Tải chương mới cho mọi truyện trong watchlist
python run.py --watch-download

# Hoặc: re-crawl truyện cũ trực tiếp (ghi đè)
python run.py --url "https://nguon.com/ten-truyen/"
```

**B. Ẩn khỏi public** — đổi `publishStatus`:

```bash
# Qua DB (SQLite CLI hoặc Prisma Studio)
npx prisma studio
# → Novel table → set publishStatus = 'pending' cho slug cần ẩn
```

Truyện `publishStatus != 'published'` sẽ:
- Không xuất hiện trong sitemap ([sitemap.js](../../src/app/sitemap.js#L9-L13))
- Không hiển thị trên homepage
- Không được Google re-index

### Bước 5 — Viết E-E-A-T pages (§3) — thủ công

Tối thiểu cần 5 trang tĩnh, mỗi trang ≥ 300 từ content thật:

| Trang | Slug đề xuất | Nội dung |
|-------|--------------|----------|
| Giới thiệu | `/gioi-thieu` | Site làm gì, ai đứng sau, giá trị cho độc giả |
| Chính sách quyền riêng tư | `/privacy` | GDPR-friendly, nêu rõ cookie + AdSense + analytics |
| Điều khoản | `/terms` | Quyền/nghĩa vụ user, quyền sở hữu nội dung |
| Liên hệ | `/lien-he` | Email thật, form contact, thời gian phản hồi |
| DMCA | `/dmca` | Quy trình gỡ nội dung vi phạm bản quyền |

Add link vào footer. AdSense review cần các page này tồn tại và có content.

### Bước 6 — Giảm ad-to-content ratio (§4) — thủ công

Trong lúc AdSense đang review lại:

**A. Ẩn Ad banner**: [src/components/ads/AdBannerClient.js](../../src/components/ads/AdBannerClient.js) đã có logic dynamic hide. Có thể tăng `minFillRate` tạm thời.

**B. Ẩn hoàn toàn AdSense script**: comment out trong [src/app/layout.js](../../src/app/layout.js) phần `<Script src="https://pagead2..."/>` và `public/ads.txt`.

**C. Giữ nội dung nhưng tắt ad**: dùng env flag `NEXT_PUBLIC_ADS_ENABLED=false` (nếu đã setup) hoặc hardcode `false` trong AdBannerClient.

Sau khi AdSense approve, bật lại.

### Bước 6.5 — Đẩy wrapper lên production (nếu crawler chạy local)

Nếu wrap trên máy local nhưng web chạy trên pi4, đồng bộ 6 cột wrapper:

```bash
python run.py --sync-wrappers-dry-run    # xem payload
python run.py --sync-wrappers            # push thật
```

Chi tiết: [wrapper_sync.md](wrapper_sync.md).

### Bước 7 — Resubmit AdSense

1. Deploy build mới có đầy đủ wrapper content.
2. Vào Google Search Console → Sitemaps → submit `https://<domain>/sitemap.xml`.
3. Vào GSC → URL Inspection → request indexing cho vài URL mới wrap.
4. Đợi 1-2 tuần cho Google re-crawl.
5. Vào AdSense → Sites → Request Review.

---

## Verify sau khi wrap

### 1. Kiểm tra content thực render trên web

Mở: `https://<domain>/truyen/<slug>`

Phải thấy 3 khối mới:
- "Đánh Giá Biên Tập"
- "Phân Tích Nhân Vật"
- "Câu Hỏi Thường Gặp"

Mở: `https://<domain>/truyen/<slug>/chuong/1`

Phải thấy:
- `<aside>` teaser trên content
- `<section>` highlight + next preview dưới content

### 2. Kiểm tra JSON-LD

View source page novel, search `application/ld+json`. Phải có schema FAQPage với array `mainEntity`.

Test bằng Google Rich Results Test:
```
https://search.google.com/test/rich-results?url=https://<domain>/truyen/<slug>
```

### 3. Kiểm tra sitemap

```
https://<domain>/sitemap.xml
```

Phải có entry cho mọi novel + chapter published. KHÔNG được có `/admin/...` hay `/dang-nhap`.

### 4. Kiểm tra robots

```
https://<domain>/robots.txt
```

Phải disallow `/admin/`, `/api/`, `/dang-nhap`, `/dang-ky`.

### 5. Kiểm tra noindex

View source trang `/admin` (nếu đang login admin) hoặc `/dang-nhap`:

```html
<meta name="robots" content="noindex, nofollow" />
```

---

## Troubleshooting

### LLM trả về tiếng Trung / Nhật

Cả `chapter_wrapper.py` và `novel_wrapper.py` đã có CJK detection + retry. Nếu vẫn xuất hiện, check log. Có thể:

1. Provider model cũ → đổi `REWRITE_PROVIDER` trong `.env`.
2. Source chapter còn sót ký tự CJK (hiếm) → chạy `vi_llm_correct.py` trước.

### Rate limit / quota

```bash
python run.py --review-all --sleep 5.0
```

Hoặc chạy từng batch 10 truyện, nghỉ 30s giữa các batch.

### Wrap xong nhưng web không hiển thị

1. Check `npx prisma studio` → cột có data chưa.
2. Rebuild: `pnpm build && pnpm start` (production) hoặc `pnpm dev`.
3. Clear Next.js cache: `rm -rf .next/cache`.

### Audit không thấy truyện

Script `audit_indexable.py` chỉ kiểm tra novel `publishStatus = 'published'`. Truyện `pending` sẽ không xuất hiện.

---

## Chi phí ước tính

| Task | Truyện | Chapters | Token | USD (Gemini 2.5 Flash) |
|------|--------|----------|-------|------------------------|
| Wrap §1 | 1 truyện | 50 chương | 50K | $0.02 |
| Wrap §2 | 1 truyện | — | 2.5K | $0.001 |
| **Toàn site 100 truyện × 50 chương** | **100** | **5000** | **~5M** | **~$2** |

Dùng Claude Haiku 4.5 đắt hơn ~8x. Ollama local miễn phí nhưng chậm.

---

## Tham khảo

- [chapter_wrapper.md](chapter_wrapper.md) — chi tiết module §1
- [novel_wrapper.md](novel_wrapper.md) — chi tiết module §2
- [crawler/audit_indexable.py](../audit_indexable.py) — script audit
- [src/app/robots.js](../../src/app/robots.js), [src/app/sitemap.js](../../src/app/sitemap.js) — §5
- [AdSense policy "Low-value content"](https://support.google.com/adsense/answer/9335564)
- [Google E-E-A-T guidelines](https://developers.google.com/search/blog/2022/12/google-raters-guidelines-e-e-a-t)
