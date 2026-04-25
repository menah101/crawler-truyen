# Chapter Wrapper — Sinh editorial cho từng chương

Module: `chapter_wrapper.py`

## Mục đích

Chống AdSense policy violation **"Low-value content"**. Nội dung chương gốc được crawl + rewrite vẫn có thể bị Google coi là duplicate. Giải pháp: thêm 3 block editorial tự sinh cho mỗi chương — nội dung này **100% do LLM viết mới**, không trùng nguồn.

| Field | Độ dài | Vị trí hiển thị |
|-------|--------|----------------|
| `summary` | 2-3 câu, 40-80 từ | Trên đầu chương, trước content — như teaser |
| `highlight` | 1-2 câu, 20-40 từ | Sau content — "Điểm nhấn chương này" |
| `nextPreview` | 1 câu, 15-25 từ | Sau content — "Chương tiếp theo" |

## Dùng

Có 2 chế độ ghi tách biệt — chọn theo nguồn data:

| Flag | Đọc từ | Ghi vào | Khi nào dùng |
|------|--------|---------|--------------|
| `--wrap-from-dir DIR` | `chapters/*.json` trên đĩa | Ghi đè JSON (thêm key `summary`, `highlight`, `next_preview`) | Truyện đã crawl xong nhưng **chưa import DB** |
| `--wrap-slug KEYWORD` | DB `Chapter.content` | UPDATE cột `summary`, `highlight`, `nextPreview` | Truyện **đã có trong DB** local |

⚠️ 2 chế độ KHÔNG đồng bộ với nhau. Wrap JSON xong, lúc import DB qua `/api/admin/import` thì 3 field này được map sang cột tương ứng. Nếu đã import rồi mới wrap JSON, cần wrap lại bằng `--wrap-slug` để vào DB.

### 1. Wrap chapters JSON từ thư mục crawl (chưa import DB)

```bash
# Qua run.py (khuyên dùng)
python run.py --wrap-from-dir docx_output/2026-04-19/ten-truyen

# Hoặc standalone
python chapter_wrapper.py --dir docx_output/2026-04-19/ten-truyen/chapters \
                         --title "Âm Thanh Trong Tiếng Mưa" \
                         --genres "Ngôn tình"
```

Kết quả: mỗi file `chapters/NNNN.json` có thêm 3 key `summary`, `highlight`, `next_preview` (snake_case trong JSON).

### 2. Wrap chapters đã import vào DB

```bash
# Qua run.py
python run.py --wrap-slug "ten truyen"

# Standalone
python chapter_wrapper.py --slug "ten truyen"
```

Kết quả: UPDATE 3 cột `summary`, `highlight`, `nextPreview` (camelCase trong DB) của bảng `Chapter`. Slug khớp `LIKE '%keyword%'` + `LIMIT 1` ([db_helper.py:83-87](../db_helper.py#L83-L87)) — chỉ wrap **1 truyện** mỗi call.

### 3. Chỉ wrap vài chương

```bash
python run.py --wrap-slug "ten truyen" --wrap-chapter 1 2 3 10
```

### 4. Ghi đè wrapper đã có

Mặc định skip chương nào đã có `summary + highlight`. Ép ghi đè:

```bash
python run.py --wrap-from-dir ... --wrap-redo
python run.py --wrap-slug "..." --wrap-redo
```

### 5. Wrap toàn site

```bash
# Wrap §1 cho mọi novel có chapter chưa wrap (auto-skip nếu đã có summary+highlight)
python run.py --wrap-all

# Ép wrap lại tất cả (kể cả chương đã có)
python run.py --wrap-all --wrap-redo
```

`--wrap-all` chỉ loop những novel **còn chương chưa wrap** (query DISTINCT ở [chapter_wrapper.py wrap_all_chapters_in_db](../chapter_wrapper.py)) — không tốn API trên truyện đã xong. Resumable: Ctrl+C giữa chừng, chạy lại sẽ tiếp từ chương chưa wrap.

## Schema

File: [prisma/schema.prisma](../../prisma/schema.prisma) — model `Chapter`:

```prisma
model Chapter {
  // ...
  summary     String?    // 2-3 câu teaser đầu chương
  highlight   String?    // 1-2 câu bình luận biên tập
  nextPreview String?    // 1 câu gợi chương sau
}
```

Tất cả nullable — chương cũ chưa wrap render bình thường (không có block editorial).

## Hiển thị trên web

[src/app/(main)/truyen/[slug]/chuong/[number]/page.js](../../src/app/(main)/truyen/[slug]/chuong/[number]/page.js) render 2 block:

- **Trên content**: `<aside>` style italic, border-l-4 — hiển thị `summary`.
- **Dưới content**: `<section>` card chứa 💡 Điểm nhấn (`highlight`) + 📖 Chương tiếp theo (`nextPreview`, chỉ khi có chương sau).

## LLM

Dùng chung config với `hook_generator.py` và `rewriter.py`:
- `REWRITE_PROVIDER=gemini|anthropic|ollama` trong `.env`
- Lần lượt fallback nếu provider chính fail
- Detect CJK drift → retry 1 lần với prompt nghiêm khắc hơn

## Workflow khuyến nghị

```bash
# 1. Crawl + rewrite như cũ
python run.py --url "..." --seo --images

# 2. (MỚI) Wrap editorial cho mọi chương
python run.py --wrap-from-dir docx_output/YYYY-MM-DD/ten-truyen

# 3. Import DB (nếu làm qua JSON) hoặc skip (nếu crawler ghi thẳng DB)
# Sau import, field summary/highlight/nextPreview đã có trong DB

# 4. Hoặc: chapters đã trong DB, wrap luôn trong DB
python run.py --wrap-slug "ten truyen"

# 5. Publish như bình thường → AdSense crawl thấy content có value
```

## Chi phí

- Mỗi chương ≈ 2500 ký tự input + 200 ký tự output → ~1000 tokens với Gemini 2.5 Flash.
- 1 truyện 50 chương: ~50K tokens ≈ $0.02 (Gemini), $0.15 (Claude Haiku).
- Rate limit: `--sleep 1.0` mặc định (có thể hạ xuống 0 nếu provider cho phép).

## Lưu ý AdSense

Wrapper editorial chỉ là **1 trong 5 điều** cần làm khi bị reject "low-value content":

1. ✅ **Wrapper editorial** (module này).
2. Review/phân tích riêng ở trang `/truyen/[slug]` (LLM sinh dựa trên toàn truyện).
3. E-E-A-T pages: About / Privacy / Terms / Contact / DMCA đầy đủ.
4. Ad-to-content ratio thấp trong lúc review (có thể tắt ad script tạm).
5. Check GSC "Duplicate content" / "Soft 404" < 20% tổng URL.
