# Merge Video — Ghép video Long-form YouTube

Module: `merge_video.py`

Ghép **30 ảnh thumbnail lặp vòng** với file audio truyện đầy đủ → video YouTube thông thường.

## Quy trình

### Bước 1 — Tạo thumbnail (nếu chưa có)

```bash
python run.py --url "https://..." --images
```

### Bước 2 — Đặt file audio vào thư mục `long/`

```
ten-truyen/
  thumbnails/          ← 30 ảnh (bước 1)
  long/
    ten-truyen.mp3     ← đặt file audio vào đây
```

### Bước 3 — Ghép video

```bash
# Truyện mới nhất
python merge_video.py long --latest --per-image 10 --zoom alternate

# Chỉ định đường dẫn
python merge_video.py long docx_output/2026-03-25/ten-truyen --per-image 10 --zoom alternate

# Khuyên dùng
python merge_video.py long --latest --per-image 10 --zoom alternate --label --subtitle
```

## Options

| Option | Mô tả |
|--------|-------|
| `--latest` | Tự tìm truyện mới nhất trong `docx_output/` |
| `--per-image <s>` | Số giây mỗi ảnh hiển thị (mặc định: 15) |
| `--zoom in/out/alternate` | Ken Burns effect |
| `--label` | Overlay label từ thư mục `label/long/` |
| `--subtitle` | Tạo subtitle từ MP3 (Whisper) |
| `--whisper-model` | Model Whisper: `tiny` / `small` / `medium` |
| `--mp3 <file>` | Chỉ định file MP3 |
| `--output <file>` | Chỉ định đường dẫn output |
| `--width <px>` | Chiều rộng output (mặc định: 1920) |

> **Lưu ý:** `--fade` không hỗ trợ mode long. Dùng `--zoom` thay thế.

## Kết quả

- File: `long/ten-truyen_long.mp4`
- 30 ảnh tự động lặp vòng đến hết file audio
- Full HD 1920px

## Ken Burns effect (zoom)

Zoom dùng **easing cosine** `(1−cos(π·t))/2` — chậm đầu, nhanh giữa, chậm cuối.

| Mode | Hành vi | Ranh giới ảnh |
|------|---------|---------------|
| `in` | Mỗi ảnh zoom 1.0→1.25 | Reset về 1.0 (có cut nhẹ) |
| `out` | Mỗi ảnh zoom 1.25→1.0 | Reset về 1.25 (có cut nhẹ) |
| `alternate` | Chẵn zoom-in, lẻ zoom-out | **Liền mạch** — ảnh kết thúc ở 1.25, ảnh tiếp bắt đầu từ 1.25 |

## Subtitle tự động (karaoke-style)

```bash
# Cài 1 lần
pip install faster-whisper

# Shorts với subtitle
python merge_video.py shorts --latest --fade --zoom alternate --label --subtitle

# Long với subtitle
python merge_video.py long --latest --per-image 10 --zoom alternate --label --subtitle --whisper-model small
```

**Luồng xử lý:**
```
render video → overlay label → Whisper transcribe MP3 → mux SRT vào MP4
```

**Chọn model Whisper:**

| Model | RAM | Thời gian (3 phút audio) | Gợi ý |
|-------|-----|--------------------------|-------|
| `tiny` | ~400 MB | ~30 giây | Mặc định, đủ dùng |
| `small` | ~1 GB | ~1 phút | Chính xác hơn |
| `medium` | ~3 GB | ~3 phút | Rất chính xác |

Subtitle được nhúng dưới dạng **soft subtitle** — người xem bật/tắt được. File `.srt` cũng được lưu riêng.

**Thêm subtitle vào video cũ (không render lại):**

```bash
python merge_video.py subtitle --video path/to/video.mp4 --mp3 path/to/audio.mp3
```
