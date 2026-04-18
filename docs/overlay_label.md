# Overlay Label — Chèn logo/branding lên video

Chèn ảnh/logo lên video đã render — dùng để thêm branding, watermark, banner kênh.

## Cấu trúc thư mục `label/`

```
crawler/
  label/
    short/                 ← Label cho video Shorts (9:16)
      center-top.png
      right-top.png
      left-top.png
      right-bottom.png
      left-bottom.png
      center.png
    long/                  ← Label cho video Long-form (16:9)
      center-top.png
      right-bottom.png
      ...
```

> Hỗ trợ cả `.png` và `.mp4` (overlay động, lặp vòng).

## Vị trí và tỷ lệ

| Tên file | Vị trí | Tỷ lệ kích thước |
|----------|--------|-----------------|
| `center-top.png` | Căn giữa ngang, cách top 120px | 100% chiều rộng video |
| `right-top.png` | Góc phải trên, cách mép 10px | 20% chiều rộng video |
| `left-top.png` | Góc trái trên, cách mép 10px | 20% chiều rộng video |
| `right-bottom.png` | Góc phải dưới, sát mép | 30% chiều rộng video |
| `left-bottom.png` | Góc trái dưới, cách mép 10px | 20% chiều rộng video |
| `center.png` | Chính giữa màn hình | 50% chiều rộng video |

## Sử dụng

```bash
# Overlay tự động sau khi render (thêm --label)
python merge_video.py shorts --latest --zoom alternate --label
python merge_video.py long --latest --zoom alternate --per-image 10 --label

# Dùng thư mục label khác
python merge_video.py shorts --latest --label --label-dir /path/to/labels
```

Có thể đặt nhiều file cùng lúc — tất cả đều được overlay.
