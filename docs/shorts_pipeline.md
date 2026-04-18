# Shorts Pipeline — Video TikTok / YouTube Shorts

Module: `shorts_pipeline.py`, `hook_generator.py`

Pipeline tự động: **truyện → hook story 400-600 chữ → 8 cảnh ảnh → ghép video**.

## Sử dụng

```bash
python run.py --url "https://..." --shorts

# Tạo lại Shorts cho truyện đã có trong database
python run.py --shorts-only "hanh phuc do toi tu tao"
```

## Output

```
shorts/
  hook_story.txt      ← Script đọc (400-600 chữ) — dùng làm voice over
  scenes.json         ← Thông tin 8 cảnh + đường dẫn ảnh
  seo_shorts.txt      ← Caption TikTok + tiêu đề/mô tả YouTube Shorts
  images/
    scene_001.jpg ... scene_008.jpg
```

## Shorts SEO — TikTok & YouTube Shorts

SEO cho Shorts được tạo **tự động** sau khi chạy `--shorts`. File `seo_shorts.txt` chứa:

- **TikTok caption**: 150 ký tự đầu (hook hiện trước "Xem thêm") + nội dung mở rộng + 10-15 hashtag
- **YouTube Shorts title**: Tối đa 100 ký tự, hook mạnh
- **YouTube Shorts description**: 2-3 dòng + URL đọc truyện + hashtag

```bash
# Tạo lại Shorts SEO từ hook_story.txt đã có
python run.py --shorts-seo docx_output/2026-03-25/ten-truyen/shorts
```

## Ghép video Shorts

**Bước 1:** Đặt file MP3 (giọng đọc/TTS) vào thư mục `shorts/`

**Bước 2:** Ghép video:

```bash
# Truyện mới nhất
python merge_video.py shorts --latest

# Chỉ định đường dẫn
python merge_video.py shorts docx_output/2026-03-25/ten-truyen/shorts

# Khuyên dùng
python merge_video.py shorts --latest --fade --zoom alternate --label --subtitle
```

### Options

| Option | Mô tả |
|--------|-------|
| `--latest` | Tự tìm truyện mới nhất trong `docx_output/` |
| `--fade` | Crossfade mượt giữa các cảnh |
| `--zoom in` | Zoom vào nhẹ mỗi cảnh (Ken Burns, 1.0→1.25) |
| `--zoom out` | Zoom ra nhẹ mỗi cảnh (1.25→1.0) |
| `--zoom alternate` | Xen kẽ zoom-in / zoom-out *(đẹp nhất)* |
| `--label` | Overlay label từ thư mục `label/short/` |
| `--label-dir <path>` | Chỉ định thư mục label khác |
| `--subtitle` | Tạo subtitle từ MP3 (Whisper) rồi nhúng vào video |
| `--whisper-model` | Model Whisper: `tiny` / `small` / `medium` |
| `--mp3 <file>` | Chỉ định file MP3 |
| `--output <file>` | Chỉ định đường dẫn output |
| `--width <px>` | Chiều rộng video (mặc định: 1080) |

### Kết quả

- File: `shorts/ten-truyen_shorts.mp4`
- Tỷ lệ 9:16 dọc (1080×1920)
- H.264 + AAC 192k
