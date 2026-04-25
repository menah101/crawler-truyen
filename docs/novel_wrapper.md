# Novel Wrapper — Sinh editorial cho trang `/truyen/[slug]`

Module: `novel_wrapper.py`

## Mục đích

Đi cùng `chapter_wrapper.py` để chống AdSense policy **"Low-value content"**:

- `chapter_wrapper` → tăng value cho trang **chapter** (summary/highlight/nextPreview)
- `novel_wrapper`   → tăng value cho trang **novel** (review/analysis/FAQ)

Mỗi truyện sinh 3 block 100% do LLM viết mới:

| Field | Độ dài | Vị trí hiển thị |
|-------|--------|----------------|
| `editorialReview`   | 150-300 từ | Khối "Đánh Giá Biên Tập" trên trang novel |
| `characterAnalysis` | 150-250 từ | Khối "Phân Tích Nhân Vật" trên trang novel |
| `faq`               | 5-7 Q&A, JSON array | Khối `<details>` + FAQPage JSON-LD |

## Dùng

### 1. Wrap 1 truyện đã có trong DB

```bash
# Qua run.py (khuyên dùng)
python run.py --review-slug "ten truyen"

# Standalone
python novel_wrapper.py --slug "ten truyen"
```

Kết quả: update trực tiếp 3 cột `editorialReview`, `characterAnalysis`, `faq` của bảng `Novel`.

### 2. Wrap từ thư mục crawl (chưa import DB)

```bash
python run.py --review-from-dir docx_output/2026-04-19/ten-truyen
```

Kết quả: ghi file `novel_wrapper.json` trong thư mục truyện. Khi import DB, 3 field sẽ được map sang cột tương ứng.

### 3. Wrap tất cả truyện trong DB

```bash
python run.py --review-all
```

Skip những truyện đã có đủ 3 field. Ép ghi đè:

```bash
python run.py --review-all --review-redo
```

### 4. Rate-limit

```bash
python run.py --review-all --sleep 3.0
```

Default sleep giữa các truyện = 2 giây.

## Schema

File: [prisma/schema.prisma](../../prisma/schema.prisma) — model `Novel`:

```prisma
model Novel {
  // ...
  editorialReview   String?   // 150-300 từ review biên tập
  characterAnalysis String?   // Phân tích nhân vật chính
  faq               String?   // JSON array [{q, a}, ...]
}
```

Tất cả nullable — truyện cũ chưa wrap render bình thường (không có block editorial, không có FAQ JSON-LD).

## Hiển thị trên web

[src/app/(main)/truyen/[slug]/page.js](../../src/app/(main)/truyen/[slug]/page.js) render:

- **Đánh Giá Biên Tập** — card gradient, render `editorialReview` dạng paragraph.
- **Phân Tích Nhân Vật** — card, render `characterAnalysis`.
- **Câu Hỏi Thường Gặp** — `<details>` collapsible, parse `faq` JSON.
- **JSON-LD FAQPage** — inject vào `<head>` khi có FAQ, giúp Google hiện rich snippet.

## Prompt rules

- Prompt khóa `100% tiếng Việt có dấu. KHÔNG ký tự CJK.`
- Sample chapter 0 / 1/3 / 2/3 / cuối (như `hook_generator`) — đủ bao quát mà không quá dài.
- Detect CJK drift trên output → retry 1 lần prompt cứng hơn → strip ký tự CJK nếu vẫn còn.

## FAQ parsing

LLM trả về dạng:

```
Q: Truyện này có bao nhiêu chương?
A: ...
Q: ...
A: ...
```

`_parse_faq()` tách thành `[{q, a}, ...]` rồi lưu dưới dạng JSON string trong cột `faq`. Trang novel `JSON.parse(novel.faq)` để render.

## LLM

Dùng chung config với `chapter_wrapper.py` / `hook_generator.py` / `rewriter.py`:
- `REWRITE_PROVIDER=gemini|anthropic|ollama` trong `.env`
- Fallback chain nếu provider chính fail
- CJK drift detect + retry

## Chi phí

- Mỗi truyện ≈ 3000 ký tự input + 800 ký tự output → ~2500 tokens với Gemini 2.5 Flash.
- 100 truyện: ~250K tokens ≈ $0.10 (Gemini), $0.80 (Claude Haiku 4.5).
- Chậm: ~5-10s / truyện (prompt dài hơn chapter wrapper nhiều).

## Audit

Khi bị AdSense reject, chạy:

```bash
python audit_indexable.py
```

Liệt kê:
- Truyện < 5 chương (thin content candidates)
- Truyện chưa wrap §2 (thiếu review/analysis/faq)
- Truyện có description yếu (< 80 ký tự)
- Chapter chưa wrap §1
- Chapter < 300 từ

Xem: [audit_indexable.py](../audit_indexable.py).

## Workflow khuyến nghị cho AdSense review

```bash
# 1. Wrap §1 cho mọi chương (nếu chưa)
python run.py --wrap-slug "ten truyen"

# 2. Wrap §2 cho mọi truyện
python run.py --review-all

# 3. Audit xem còn truyện/chương nào yếu
python audit_indexable.py

# 4. Ẩn (publishStatus=pending) hoặc viết thêm cho truyện < 5 chương
# 5. Rebuild + redeploy → Google re-crawl → resubmit AdSense
```

## Lưu ý

- `novel_wrapper` chỉ giải quyết §2 trong 5 điều cần làm. Cần kết hợp:
  1. ✅ Chapter wrapper (`chapter_wrapper.py`)
  2. ✅ Novel wrapper (module này)
  3. E-E-A-T pages: About / Privacy / Terms / Contact / DMCA
  4. Ad-to-content ratio thấp trong lúc review (tắt ad script nếu cần)
  5. ✅ Audit `audit_indexable.py` + GSC "Duplicate content" / "Soft 404" < 20%
