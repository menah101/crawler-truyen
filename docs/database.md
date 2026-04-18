# Database — Quản lý dữ liệu

Module: `db_helper.py`

## Các lệnh

```bash
# Xem tất cả truyện đã tải
python run.py --db-list

# Xóa 1 truyện (tìm theo từ khoá)
python run.py --db-delete "tên truyện"

# Xóa TOÀN BỘ database (không thể hoàn tác)
python run.py --db-delete-all
```

## Chuẩn hóa mô tả truyện

Module: `normalize_descriptions.py`

Làm sạch field `description` của tất cả truyện trong DB:

- Xóa câu kêu gọi nghe audio ("Nghe tiếp để biết...", "Hãy nghe...", ...)
- Xóa emoji
- Trim khoảng trắng thừa
- Giới hạn 200 ký tự, cắt tại dấu chấm gần nhất

```bash
# Xem trước thay đổi (không ghi DB)
python crawler/normalize_descriptions.py --dry-run

# Ghi vào DB (yêu cầu gõ "confirm")
python crawler/normalize_descriptions.py --apply
```

> Truyện mới crawl đã tự động được clean qua `sanitize_description()` trong `rewriter.py`. Script này chỉ cần chạy 1 lần để fix dữ liệu cũ.
