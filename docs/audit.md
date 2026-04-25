# Audit Indexable — Quét content có nguy cơ AdSense reject

Module: `audit_indexable.py`

Liệt kê truyện/chương trong DB local có nguy cơ bị Google gắn nhãn **"Low-value content"** hoặc **"Soft 404"** trước khi resubmit AdSense.

## Dùng

```bash
cd crawler
python audit_indexable.py
```

In report 5 nhóm + khuyến nghị lệnh fix tương ứng.

### Options

| Flag | Default | Ý nghĩa |
|------|---------|---------|
| `--min-chapters N` | `5` | Ngưỡng thin novel (truyện < N chương = thin) |
| `--min-words N` | `300` | Ngưỡng chapter ngắn |
| `--json` | — | Xuất JSON thay vì report text |

```bash
# Ngưỡng nghiêm khắc hơn
python audit_indexable.py --min-chapters 10 --min-words 500

# JSON để pipe vào script
python audit_indexable.py --json > audit.json
jq '.thinNovels[] | .slug' audit.json
```

## 5 nhóm signal

| # | Nhóm | Điều kiện | Fix |
|---|------|-----------|-----|
| 1 | **Thin novels** | `Novel.publishStatus='published'` AND `COUNT(chapter published) < min_chapters` | Bổ sung chương hoặc đổi `publishStatus='pending'` |
| 2 | **Novel chưa wrap §2** | Thiếu 1 trong 3: `editorialReview` / `characterAnalysis` / `faq` | `python run.py --review-all` |
| 3 | **Description yếu** | `description` rỗng hoặc < 80 ký tự (`MIN_DESC_LEN` hardcode) | Viết lại description thủ công hoặc qua `normalize_descriptions.py` |
| 4 | **Chapter chưa wrap §1** | `summary` hoặc `highlight` rỗng (note: `nextPreview` KHÔNG check) | `python run.py --wrap-slug "<slug>"` |
| 5 | **Chapter ngắn** | `wordCount < min_words`, sort tăng dần, limit 200 | Re-rewrite hoặc gộp với chương khác |

⚠️ Audit **chỉ kiểm tra** truyện/chương `publishStatus='published'`. Truyện `pending` không xuất hiện trong report (cố ý — không cần fix nếu không public).

## Output JSON schema

```json
{
  "thinNovels":         [{"slug": "...", "title": "...", "chapters": 3}],
  "unwrappedNovels":    [{"slug": "...", "title": "...", "hasReview": false, "hasAnalysis": true, "hasFaq": false}],
  "weakDescription":    [{"slug": "...", "title": "...", "descLen": 45}],
  "unwrappedChapters":  [{"id": 123, "number": 5, "title": "...", "wordCount": 800, "novelSlug": "...", "novelTitle": "..."}],
  "shortChapters":      [{"number": 12, "title": "...", "wordCount": 180, "novelSlug": "...", "novelTitle": "..."}],
  "thresholds":         {"minChapters": 5, "minWords": 300, "minDescLen": 80}
}
```

## Workflow điển hình

```bash
# 1. Audit hiện trạng
python audit_indexable.py

# 2. Wrap §2 cho mọi novel còn thiếu
python run.py --review-all

# 3. Wrap §1 cho mọi chương còn thiếu
python run.py --wrap-all

# 4. Đẩy lên pi4
python run.py --sync-wrappers

# 5. Audit lại để xác nhận
python audit_indexable.py
```

## Tham khảo

- [adsense_recovery.md](adsense_recovery.md) — playbook 7 bước khắc phục reject
- [chapter_wrapper.md](chapter_wrapper.md) — wrap §1
- [novel_wrapper.md](novel_wrapper.md) — wrap §2
- [audit_indexable.py](../audit_indexable.py) — source
