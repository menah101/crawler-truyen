# Scraper — Tải truyện

Module: `scraper.py` | Điều phối: `run.py`

## Tải 1 truyện theo URL

```bash
python run.py --url "https://yeungontinh.baby/truyen/ten-truyen/"
```

## Tải + tạo toàn bộ nội dung cùng lúc (khuyên dùng)

```bash
python run.py --url "https://..." --seo --images --shorts
```

## Các lệnh khác

```bash
# Tải ngẫu nhiên 1 truyện từ nguồn mặc định
python run.py

# Tải ngẫu nhiên 3 truyện
python run.py --count 3

# Chọn nguồn khác
python run.py --source truyenfull --url "https://truyenfull.io/ten-truyen/"

# Chỉ tải chương 1, 5, 10
python run.py --url "https://..." --chapters 1 5 10

# Giới hạn tối đa 20 chương
python run.py --url "https://..." --max-chapters 20

# Chế độ tương tác — chọn nguồn và truyện thủ công
python run.py --interactive

# Chạy tự động hàng ngày lúc 8:00 sáng
python run.py --schedule

# Test nhanh (1 truyện, 3 chương đầu)
python run.py --test

# Xem danh sách nguồn có sẵn
python run.py --list-sources
```

## Các nguồn hỗ trợ

| Nguồn | Lệnh |
|-------|-------|
| yeungontinh.baby | `--source yeungontinh` *(mặc định)* |
| truyenfull.io | `--source truyenfull` |
| metruyencv.com | `--source metruyencv` |
| monkeyd.xyz | `--source monkeyd` |
| vivutruyen.com | `--source vivutruyen` |
| saytruyen.com | `--source saytruyen` |
| truyenfullvision.com | `--source truyenfullvision` |
| tvtruyen.com | `--source tvtruyen` |
| hongtruyenhot.net | `--source hongtruyenhot` |

> Tự nhận diện nguồn theo URL — không cần `--source` nếu dùng `--url`.
