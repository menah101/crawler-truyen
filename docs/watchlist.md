# Watchlist — Theo dõi truyện

Module: `watchlist.py`

Tự động kiểm tra và tải chương mới cho truyện đang theo dõi.

## Sử dụng

```bash
# Thêm truyện vào danh sách
python run.py --watch-add "https://yeungontinh.baby/truyen/ten-truyen/"

# Xem danh sách
python run.py --watch-list

# Kiểm tra chương mới (không tải)
python run.py --watch-check

# Tải tất cả chương mới
python run.py --watch-download

# Xóa khỏi danh sách
python run.py --watch-remove "https://..."
```
