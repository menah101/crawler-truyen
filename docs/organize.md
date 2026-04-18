# Organize — Sắp xếp thư mục theo ngày

Module: `organize.py`

Truyện mới tải tự vào thư mục ngày hôm nay. Truyện cũ (dạng phẳng) cần sắp xếp thủ công.

## Sử dụng

```bash
# Xem trước — chưa thay đổi gì
python organize.py

# Thực hiện sắp xếp
python organize.py --apply

# Xem cấu trúc hiện tại
python organize.py --list
```

## Trước → Sau

```
# Trước                        # Sau
docx_output/                   docx_output/
  ten-truyen-a/                  2026-03-24/
  ten-truyen-b/                    ten-truyen-a/
  ten-truyen-c/                    ten-truyen-b/
                                 2026-03-25/
                                   ten-truyen-c/
```
