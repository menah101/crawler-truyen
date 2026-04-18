# Chapter Rewriter — Rewrite lại từng chương JSON

Module: `chapter_rewriter.py`

Đọc các file `chapters/NNNN.json` đã có, gọi `rewrite_chapter()` (fallback chain Gemini → DeepSeek → Anthropic → Ollama → local), rồi ghi đè lại. Mặc định tự backup toàn bộ thư mục `chapters/` sang `chapters_backup_<timestamp>/` trước khi chạy.

## Cấu trúc JSON mong đợi

```json
{
  "number": 1,
  "title": "Chương 1",
  "content": "..."
}
```

## Dùng qua `run.py`

```bash
# Rewrite tất cả chương trong thư mục
python run.py --rewrite-from-dir docx_output/2026-04-17/am-thanh-trong-tieng-mua/chapters

# Chỉ rewrite chương 1 và 3
python run.py --rewrite-from-dir docx_output/.../chapters --rewrite-chapter 1 3

# Bỏ qua backup (cẩn thận — không hồi phục được)
python run.py --rewrite-from-dir docx_output/.../chapters --rewrite-no-backup
```

Flag có thể trỏ trực tiếp vào thư mục `chapters/` hoặc thư mục truyện chứa `chapters/`.

## Dùng như script standalone

```bash
python chapter_rewriter.py docx_output/2026-04-17/ten-truyen/chapters
python chapter_rewriter.py docx_output/2026-04-17/ten-truyen --chapter 1 3
python chapter_rewriter.py docx_output/.../chapters --no-backup --title "Tên Truyện"
```

## Dùng như module Python

```python
from chapter_rewriter import rewrite_chapters_dir

stats = rewrite_chapters_dir(
    'docx_output/2026-04-17/ten-truyen/chapters',
    only_numbers={1, 3},   # None = tất cả
    backup=True,
    novel_title='Tên Truyện',
)
# stats = {'total': 4, 'rewritten': 2, 'skipped': 2, 'failed': 0, 'backup_dir': '...'}
```

## Hành vi

- File content < 100 ký tự → bỏ qua (coi như trống, tránh gọi AI vô ích).
- `rewrite_chapter()` raise exception → fallback sang `split_paragraphs()` (chia đoạn raw, không AI).
- File JSON lỗi format → đếm vào `failed`, tiếp tục các file khác.
- `novel_title` tự đọc dòng đầu `seo.txt` nếu không truyền.
- Backup dir nằm cạnh `chapters/` trong thư mục truyện, không chồng lên nhau nhờ timestamp.

## Khi nào dùng

- Muốn re-rewrite một truyện đã crawl xong (VD: provider cũ cho kết quả kém).
- Rewrite một chương đơn bị hỏng output (dùng `--rewrite-chapter N`).
- Rewrite truyện import thủ công mà không qua DB.
