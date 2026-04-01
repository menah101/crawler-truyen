# 🏯 Hồng Trần Truyện — Crawler & Content Pipeline

Công cụ tự động tải truyện, viết lại bằng AI, và tạo nội dung cho kênh **Hồng Trần Truyện Audio** (YouTube / TikTok / Web).

---

## Mục lục

1. [Cài đặt lần đầu](#1-cài-đặt-lần-đầu)
2. [Cấu hình .env](#2-cấu-hình-env)
3. [Tải truyện](#3-tải-truyện)
4. [Xuất file DOCX](#4-xuất-file-docx)
5. [Phân tích SEO](#5-phân-tích-seo)
6. [Tạo ảnh thumbnail](#6-tạo-ảnh-thumbnail)
7. [Tạo video Shorts](#7-tạo-video-shorts-tiktok--youtube-shorts)
8. [Tạo video Long-form](#8-tạo-video-long-form-youtube)
   - [Subtitle tự động](#subtitle-tự-động-karaoke-style)
9. [Overlay Label](#9-overlay-label)
10. [Sắp xếp thư mục theo ngày](#10-sắp-xếp-thư-mục-theo-ngày)
11. [Watchlist — theo dõi truyện](#11-watchlist--theo-dõi-truyện)
12. [Quản lý database](#12-quản-lý-database)
13. [Cấu trúc thư mục output](#13-cấu-trúc-thư-mục-output)
14. [Sơ đồ luồng hoàn chỉnh](#14-sơ-đồ-luồng-hoàn-chỉnh)
15. [Lệnh tham khảo nhanh](#lệnh-tham-khảo-nhanh)

---

## 1. Cài đặt lần đầu

```bash
# Vào thư mục crawler
cd crawler

# Cài thư viện Python
pip install -r requirements.txt

# Cài ffmpeg (cần để tạo video)
brew install ffmpeg          # macOS
# sudo apt install ffmpeg    # Ubuntu/Linux
```

> **Yêu cầu:** Python 3.11+

---

## 2. Cấu hình .env

Tạo file `.env` trong thư mục `crawler/`:

```env
# ── AI để viết lại truyện ──────────────────────────────────────
REWRITE_PROVIDER=gemini             # gemini | anthropic | groq | deepseek | ollama

GEMINI_API_KEY=AIza...              # https://aistudio.google.com  (miễn phí)
ANTHROPIC_API_KEY=sk-ant-...        # https://console.anthropic.com
GROQ_API_KEY=gsk_...                # https://console.groq.com  (miễn phí)
DEEPSEEK_API_KEY=sk-...             # https://platform.deepseek.com

# ── AI tạo ảnh (FLUX.1-schnell trên HuggingFace) ──────────────
HF_API_TOKEN=hf_...                 # https://huggingface.co/settings/tokens
HF_IMAGE_RATIO=9:16                 # 9:16 (Shorts) | 16:9 (YouTube)

# ── Website ───────────────────────────────────────────────────
SITE_URL=https://hongtrantruyen.net

# ── Xuất file DOCX ────────────────────────────────────────────
DOCX_EXPORT_ENABLED=true
DOCX_CHANNEL_NAME=Hồng Trần Truyện Audio

# ── Xuất phụ đề SRT ───────────────────────────────────────────
SRT_EXPORT_ENABLED=true
SRT_DURATION_PER_LINE=20
SRT_WORDS_PER_SECOND=0.25
```

> Không có API key nào là bắt buộc — nếu thiếu, chức năng đó sẽ tự bỏ qua.

---

## 3. Tải truyện

### Tải 1 truyện theo URL (cách thường dùng nhất)

```bash
python run.py --url "https://yeungontinh.baby/truyen/ten-truyen/"
```

### Tải + tạo toàn bộ nội dung cùng lúc (khuyên dùng)

```bash
python run.py --url "https://..." --seo --images --shorts
```

### Các lệnh khác

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

### Các nguồn hỗ trợ

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

---

## 4. Xuất file DOCX

Sau khi tải, crawler tự hỏi có muốn xuất DOCX không. Hoặc xuất thủ công:

```bash
# Xuất DOCX cho truyện đã có trong database
python run.py --docx-build "tên truyện"

# Tìm theo từ khoá
python run.py --docx-from-db "ly hon"
```

File lưu vào:
```
docx_output/2026-03-25/ten-truyen/ten-truyen.docx
```

---

## 5. Phân tích SEO

Tạo tiêu đề YouTube, mô tả, hashtag, tóm tắt — dùng AI phân tích nội dung truyện.

```bash
# Kết hợp khi tải
python run.py --url "https://..." --seo

# Phân tích cho truyện đã tải
python run.py --seo-only "tên truyện"
```

**Output** — file `seo.txt` trong thư mục truyện:

```
=== TIÊU ĐỀ YOUTUBE ===
【Truyện Audio】 Ký tên rồi ra đi, anh mới hiểu mình đã mất gì | Hồng Trần Truyện Audio

=== MÔ TẢ YOUTUBE ===
Ký tên để ra đi, anh chỉ còn lạnh lùng nhìn theo... | Nghe Ký Hôn audio miễn phí trên kênh Hồng Trần Truyện Audio.
...
👉 Đọc truyện đầy đủ tại: https://hongtrantruyen.net/truyen/ky-hon

=== TAGS ===
Ký Hôn, ngôn tình, truyện audio, ...

=== TÓM TẮT (Pinned Comment) ===
...
```

**Quy tắc tiêu đề:**
- Bắt đầu bằng `【Truyện Audio】`
- Hook cụ thể từ nội dung truyện (không chung chung)
- Kết thúc `| Hồng Trần Truyện Audio`
- Tối đa 80 ký tự
- Không chứa tên truyện trong tiêu đề (chỉ trong mô tả và tags)

---

## 6. Tạo ảnh thumbnail

Tạo **30 ảnh thumbnail** tỷ lệ **16:9** (1344×768, chuẩn YouTube) — mỗi ảnh khác nhau về góc chụp và nội dung, bám sát nội dung truyện.

AI tự nhận diện thể loại để tạo đúng phong cách:

| Thể loại | Phong cách hình ảnh |
|----------|---------------------|
| **CỔ TRANG** | Hanfu, cung điện, ánh nến vàng, sương mù cổ phong |
| **HIỆN ĐẠI** | Trang phục hiện đại, căn hộ, văn phòng, thành phố |
| **THẬP NIÊN** | Thời trang retro 60s–2000s, phim cũ Kodachrome |

```bash
# Kết hợp khi tải
python run.py --url "https://..." --images

# Tạo lại (xoá ảnh cũ trước nếu muốn)
rm docx_output/.../thumbnails/*.jpg
python run.py --url "https://..." --images

# Tạo lại thumbnail cho truyện đã có trong database (không crawl lại)
python run.py --images-only "hanh phuc do toi tu tao"
```

30 ảnh phân bổ đa dạng:

| Góc chụp | Số lượng | Mô tả |
|----------|----------|-------|
| `wide` | 6 | Toàn cảnh, bối cảnh hoành tráng |
| `atmospheric` | 6 | Ánh sáng + không khí gợi cảm xúc |
| `close_up` | 6 | Mặt nhân vật, biểu cảm mạnh |
| `detail` | 4 | Vật thể biểu tượng (thư, trang sức...) |
| `action` | 4 | Cảnh chuyển động, góc nghiêng |
| `medium` | 3 | Nửa thân + môi trường |
| `two_shot` | 1 | Hai nhân vật đối diện |

Ảnh lưu vào: `docx_output/2026-03-25/ten-truyen/thumbnails/`

---

## 7. Tạo video Shorts (TikTok / YouTube Shorts)

Pipeline tự động: **truyện → hook story 400-600 chữ → 8 cảnh ảnh → ghép video**.

```bash
python run.py --url "https://..." --shorts

# Tạo lại Shorts cho truyện đã có trong database (không crawl lại)
python run.py --shorts-only "hanh phuc do toi tu tao"
```

**Output** trong thư mục `shorts/`:

```
shorts/
  hook_story.txt      ← Script đọc (400-600 chữ) — dùng làm voice over
  scenes.json         ← Thông tin 8 cảnh + đường dẫn ảnh
  seo_shorts.txt      ← Caption TikTok + tiêu đề/mô tả YouTube Shorts (tự động tạo)
  images/
    scene_001.jpg ... scene_008.jpg
```

### Shorts SEO — TikTok & YouTube Shorts

SEO cho Shorts được tạo **tự động** sau khi chạy `--shorts`. File `seo_shorts.txt` chứa:

- **TikTok caption**: 150 ký tự đầu (hook hiện trước "Xem thêm") + nội dung mở rộng + 10-15 hashtag
- **YouTube Shorts title**: Tối đa 100 ký tự, hook mạnh
- **YouTube Shorts description**: 2-3 dòng + URL đọc truyện + hashtag

```bash
# Tạo lại Shorts SEO từ hook_story.txt đã có (không crawl lại)
python run.py --shorts-seo docx_output/2026-03-25/ten-truyen/shorts

# Tạo lại cho truyện mới nhất
python run.py --shorts-seo docx_output/2026-03-25/hanh-phuc-do-toi-tu-tao/shorts
```

> Dùng `--shorts-seo` khi muốn thử lại prompt khác hoặc kết quả AI lần đầu chưa ưng ý.

### Ghép video Shorts

**Bước 1:** Đặt file MP3 (giọng đọc/TTS) vào thư mục `shorts/`

**Bước 2:** Ghép video:

```bash
# Cú pháp đầy đủ
python merge_video.py shorts <shorts_dir> [options]

# Truyện mới nhất (--latest tự tìm trong docx_output/)
python merge_video.py shorts --latest

# Chỉ định đường dẫn
python merge_video.py shorts docx_output/2026-03-25/ten-truyen/shorts
```

**Các option:**

| Option | Mô tả |
|--------|-------|
| `--latest` | Tự tìm truyện mới nhất trong `docx_output/` |
| `--fade` | Crossfade mượt giữa các cảnh |
| `--zoom in` | Zoom vào nhẹ mỗi cảnh (Ken Burns, 1.0→1.25) |
| `--zoom out` | Zoom ra nhẹ mỗi cảnh (1.25→1.0) |
| `--zoom alternate` | Xen kẽ zoom-in / zoom-out *(đẹp nhất, mượt nhất)* |
| `--label` | Overlay label từ thư mục `label/short/` |
| `--label-dir <path>` | Chỉ định thư mục label khác |
| `--subtitle` | Tạo subtitle từ MP3 (Whisper) rồi nhúng vào video |
| `--whisper-model` | Model Whisper: `tiny` / `small` / `medium` (mặc định: `tiny`) |
| `--mp3 <file>` | Chỉ định file MP3 (tự tìm nếu bỏ trống) |
| `--output <file>` | Chỉ định đường dẫn output |
| `--width <px>` | Chiều rộng video (mặc định: 1080) |

```bash
# Ví dụ thực tế (khuyên dùng)
python merge_video.py shorts --latest --fade --zoom alternate --label --subtitle

# Chỉ định file MP3 cụ thể (khi không đặt trong thư mục shorts/)
python merge_video.py shorts --latest --fade --zoom alternate --mp3 /path/to/voice.mp3

# Full path + mp3 riêng
python merge_video.py shorts docx_output/2026-03-25/ten-truyen/shorts --mp3 docx_output/2026-03-25/ten-truyen/shorts/voice.mp3 --fade --zoom alternate --label
```

**Kết quả:** `shorts/ten-truyen_shorts.mp4`
- Tỷ lệ 9:16 dọc (chuẩn TikTok / Reels / YouTube Shorts)
- Độ phân giải: 1080×1920
- H.264 + AAC 192k, tối ưu streaming

---

## 8. Tạo video Long-form (YouTube)

Ghép **30 ảnh thumbnail lặp vòng** với file audio truyện đầy đủ → video YouTube thông thường.

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

> Thư mục `long/` được tự tạo khi chạy lệnh ghép.

### Bước 3 — Ghép video

```bash
# Cú pháp đầy đủ
python merge_video.py long <novel_dir> [options]

# Truyện mới nhất
python merge_video.py long --latest --per-image 10 --zoom alternate

# Chỉ định đường dẫn
python merge_video.py long docx_output/2026-03-25/ten-truyen --per-image 10 --zoom alternate
```

**Các option:**

| Option | Mô tả |
|--------|-------|
| `--latest` | Tự tìm truyện mới nhất trong `docx_output/` |
| `--per-image <s>` | Số giây mỗi ảnh hiển thị (mặc định: 15) |
| `--zoom in` | Zoom vào nhẹ mỗi ảnh (1.0→1.25) |
| `--zoom out` | Zoom ra nhẹ mỗi ảnh (1.25→1.0) |
| `--zoom alternate` | Xen kẽ zoom-in / zoom-out *(mượt nhất ở ranh giới ảnh)* |
| `--label` | Overlay label từ thư mục `label/long/` |
| `--label-dir <path>` | Chỉ định thư mục label khác |
| `--subtitle` | Tạo subtitle từ MP3 (Whisper) rồi nhúng vào video |
| `--whisper-model` | Model Whisper: `tiny` / `small` / `medium` (mặc định: `tiny`) |
| `--mp3 <file>` | Chỉ định file MP3 (tự tìm trong `long/` nếu bỏ trống) |
| `--output <file>` | Chỉ định đường dẫn output |
| `--width <px>` | Chiều rộng output (mặc định: 1920) |

```bash
# Ví dụ thực tế (khuyên dùng)
python merge_video.py long --latest --per-image 10 --zoom alternate --label --subtitle

# Chỉ định file MP3 cụ thể (khi audio không nằm trong thư mục long/)
python merge_video.py long --latest --per-image 10 --zoom alternate --mp3 /path/to/full_audio.mp3

# Full path + mp3 riêng
python merge_video.py long docx_output/2026-03-25/ten-truyen --mp3 docx_output/2026-03-25/ten-truyen/long/ten-truyen.mp3 --per-image 10 --zoom alternate --label
```

> **Lưu ý:** `--fade` không hỗ trợ mode long. Dùng `--zoom` thay thế.

**Kết quả:** `long/ten-truyen_long.mp4`
- 30 ảnh tự động lặp vòng đến hết file audio
- Ví dụ: audio 30 phút + mỗi ảnh 10s → 180 lần hiển thị qua 30 ảnh
- Full HD 1920px, tối ưu cho YouTube

### Chi tiết Ken Burns effect (zoom)

Zoom dùng **easing cosine** `(1−cos(π·t))/2` — chậm đầu, nhanh giữa, chậm cuối — trông tự nhiên hơn linear.

| Mode | Hành vi | Ranh giới ảnh |
|------|---------|---------------|
| `in` | Mỗi ảnh zoom 1.0→1.25 | Reset về 1.0 (có cut nhẹ) |
| `out` | Mỗi ảnh zoom 1.25→1.0 | Reset về 1.25 (có cut nhẹ) |
| `alternate` | Chẵn zoom-in, lẻ zoom-out | **Liền mạch** — ảnh 0 kết thúc ở 1.25, ảnh 1 bắt đầu từ 1.25 |

### Subtitle tự động (karaoke-style)

Dùng `--subtitle` để tạo subtitle chính xác đồng bộ với giọng đọc thật — chạy **sau khi render xong**, không ảnh hưởng tốc độ render.

```bash
# Cài 1 lần
pip install faster-whisper

# Shorts với subtitle
python merge_video.py shorts --latest --fade --zoom alternate --label --subtitle

# Long với subtitle, model chính xác hơn
python merge_video.py long --latest --per-image 10 --zoom alternate --label --subtitle --whisper-model small
```

**Luồng xử lý:**
```
render video  →  overlay label  →  Whisper transcribe MP3  →  mux SRT vào MP4
  (nặng CPU)      (nhanh)           (1-5 phút, CPU-only)       (vài giây, -c copy)
```

**Chọn model Whisper:**

| Model | RAM | Thời gian (3 phút audio) | Gợi ý |
|-------|-----|--------------------------|-------|
| `tiny` | ~400 MB | ~30 giây | Mặc định, đủ dùng |
| `small` | ~1 GB | ~1 phút | Chính xác hơn |
| `medium` | ~3 GB | ~3 phút | Rất chính xác |

> Subtitle được nhúng dưới dạng **soft subtitle** vào MP4 — người xem có thể bật/tắt. YouTube và VLC hỗ trợ đọc. File `.srt` cũng được lưu cùng thư mục để upload riêng lên TikTok nếu cần.

**Thêm subtitle vào video cũ (không render lại):**

```bash
# Shorts cũ
python merge_video.py subtitle --video docx_output/2026-03-25/ten-truyen/shorts/ten-truyen_shorts.mp4 --mp3 docx_output/2026-03-25/ten-truyen/shorts/voice.mp3

# Long cũ, model chính xác hơn
python merge_video.py subtitle --video docx_output/2026-03-25/ten-truyen/long/ten-truyen_long.mp4 --mp3 docx_output/2026-03-25/ten-truyen/long/ten-truyen.mp3 --model small
```

---

## 9. Overlay Label

Chèn ảnh/logo lên video đã render — dùng để thêm branding, watermark, banner kênh.

### Cấu trúc thư mục `label/`

```
crawler/
  label/
    short/                 ← Label dùng cho video Shorts (9:16)
      center-top.png       ← Banner kênh (căn giữa, cách top 120px)
      right-top.png        ← Logo góc phải trên
      left-top.png         ← Logo góc trái trên
      right-bottom.png     ← Watermark góc phải dưới
      left-bottom.png      ← Watermark góc trái dưới
      center.png           ← Overlay giữa màn hình
    long/                  ← Label dùng cho video Long-form (16:9)
      center-top.png
      right-bottom.png
      ...
```

> Chỉ cần đặt file vào đúng thư mục và đúng tên — ffmpeg tự nhận và overlay. Hỗ trợ cả `.png` và `.mp4` (overlay động, lặp vòng).

### Vị trí và tỷ lệ mặc định

| Tên file | Vị trí | Tỷ lệ kích thước |
|----------|--------|-----------------|
| `center-top.png` | Căn giữa ngang, cách top 120px | 100% chiều rộng video |
| `right-top.png` | Góc phải trên, cách mép 10px | 20% chiều rộng video |
| `left-top.png` | Góc trái trên, cách mép 10px | 20% chiều rộng video |
| `right-bottom.png` | Góc phải dưới, sát mép | 30% chiều rộng video |
| `left-bottom.png` | Góc trái dưới, cách mép 10px | 20% chiều rộng video |
| `center.png` | Chính giữa màn hình | 50% chiều rộng video |

### Cách dùng

```bash
# Overlay tự động sau khi render (thêm --label)
python merge_video.py shorts --latest --zoom alternate --label
python merge_video.py long --latest --zoom alternate --per-image 10 --label

# Dùng thư mục label khác
python merge_video.py shorts --latest --label --label-dir /path/to/labels
```

**Cách hoạt động:**
1. Render video như bình thường
2. Quét thư mục `label/` tìm file theo tên vị trí
3. Scale từng label về đúng kích thước
4. Dùng `filter_complex` overlay lên video
5. Ghi đè lên file video gốc (không tạo file mới)

> Có thể đặt nhiều file cùng lúc — tất cả đều được overlay. Thứ tự: theo danh sách vị trí.

---

## 10. Sắp xếp thư mục theo ngày

Truyện mới tải tự vào thư mục ngày hôm nay. Truyện cũ (dạng phẳng) cần sắp xếp thủ công:

```bash
# Xem trước — chưa thay đổi gì
python organize.py

# Thực hiện sắp xếp
python organize.py --apply

# Xem cấu trúc hiện tại
python organize.py --list
```

**Trước → Sau:**

```
# Trước                        # Sau
docx_output/                   docx_output/
  ten-truyen-a/                  2026-03-24/
  ten-truyen-b/                    ten-truyen-a/
  ten-truyen-c/                    ten-truyen-b/
                                 2026-03-25/
                                   ten-truyen-c/
```

---

## 11. Watchlist — theo dõi truyện

Tự động kiểm tra và tải chương mới cho truyện đang theo dõi.

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

---

## 12. Quản lý database

```bash
# Xem tất cả truyện đã tải
python run.py --db-list

# Xóa 1 truyện (tìm theo từ khoá)
python run.py --db-delete "tên truyện"

# Xóa TOÀN BỘ database ⚠️ không thể hoàn tác
python run.py --db-delete-all
```

---

## 13. Cấu trúc thư mục output

Sau khi chạy đầy đủ pipeline, thư mục 1 truyện trông như sau:

```
docx_output/
  2026-03-25/
    ten-truyen/
      │
      ten-truyen.docx           ← Truyện đã viết lại (dùng làm TTS)
      seo.txt                   ← Tiêu đề + mô tả + hashtag + URL YouTube
      │
      thumbnails/               ← 30 ảnh 16:9 (1344×768) cho video long-form
      │   thumb_01_wide.jpg
      │   thumb_02_atmospheric.jpg
      │   ...
      │   thumb_30_close_up.jpg
      │
      shorts/                   ← Nội dung TikTok / YouTube Shorts
      │   hook_story.txt        ← Script đọc (400-600 chữ)
      │   scenes.json           ← Dữ liệu 8 cảnh + đường dẫn ảnh
      │   voice.mp3             ← (bạn upload)
      │   ten-truyen_shorts.mp4 ← Video đã render
      │   images/
      │       scene_001.jpg ... scene_008.jpg
      │
      long/                     ← Nội dung YouTube long-form
          ten-truyen.mp3        ← (bạn upload)
          ten-truyen_long.mp4   ← Video đã render
```

---

## 14. Sơ đồ luồng hoàn chỉnh

```
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 1 — TẢI & TẠO NỘI DUNG (1 lệnh duy nhất)            │
│                                                             │
│  python run.py --url "URL" --seo --images --shorts          │
│         │                                                   │
│         ├── Crawl + viết lại bằng AI → database            │
│         ├── Xuất DOCX → ten-truyen.docx                     │
│         ├── Phân tích SEO → seo.txt  (+ URL đọc truyện)    │
│         ├── Tạo 30 thumbnail 16:9 → thumbnails/            │
│         └── Tạo hook story + 8 ảnh → shorts/               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 2 — BẠN TỰ LÀM                                       │
│                                                             │
│  • Đọc hook_story.txt → thu âm / TTS → voice.mp3           │
│  • Đọc ten-truyen.docx → thu âm / TTS → ten-truyen.mp3     │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 3 — GHÉP VIDEO                                        │
│                                                             │
│  Shorts (TikTok / Reels / YouTube Shorts):                  │
│  python merge_video.py shorts --latest                      │
│         [--fade] [--zoom alternate] [--label]               │
│  → ten-truyen_shorts.mp4  (dọc 9:16, 1080×1920)            │
│                                                             │
│  Long-form (YouTube):                                       │
│  python merge_video.py long --latest --per-image 10         │
│         [--zoom alternate] [--label]                        │
│  → ten-truyen_long.mp4   (ngang Full HD 1920px)            │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 4 — ĐĂNG LÊN                                         │
│                                                             │
│  • TikTok / Reels / YouTube Shorts ← _shorts.mp4           │
│  • YouTube Video ← _long.mp4                               │
│  • Copy tiêu đề + mô tả + hashtag từ seo.txt               │
│  • URL đọc truyện đã có sẵn trong mô tả                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Lệnh tham khảo nhanh

```bash
# ── Tải + tạo tất cả cùng lúc ──────────────────────────────────
python run.py --url "URL" --seo --images --shorts

# ── Ghép video Shorts ─────────────────────────────────────────
python merge_video.py shorts --latest --fade --zoom alternate --label
python merge_video.py shorts docx_output/YYYY-MM-DD/ten-truyen/shorts --fade --zoom alternate --label

# ── Ghép video Long-form ──────────────────────────────────────
python merge_video.py long --latest --per-image 10 --zoom alternate --label
python merge_video.py long docx_output/YYYY-MM-DD/ten-truyen --per-image 10 --zoom alternate --label

# ── Sắp xếp thư mục cũ ────────────────────────────────────────
python organize.py --apply

# ── Xem truyện đã tải ─────────────────────────────────────────
python run.py --db-list

# ── Phân tích SEO riêng (long-form YouTube) ───────────────────
python run.py --seo-only "tên truyện"

# ── Subtitle (Whisper, chính xác với giọng đọc) ───────────────
python merge_video.py shorts --latest --fade --zoom alternate --subtitle
python merge_video.py long --latest --per-image 10 --zoom alternate --subtitle --whisper-model small

# ── Tạo lại Shorts SEO (TikTok + YouTube Shorts) ──────────────
python run.py --shorts-seo docx_output/YYYY-MM-DD/ten-truyen/shorts

# ── Truyện cũ đã có DOCX — tạo lại thumbnail / shorts không crawl ──
python run.py --images-only "hanh phuc do toi tu tao"    # tạo lại thumbnail 16:9
python run.py --shorts-only "hanh phuc do toi tu tao"    # tạo lại hook story + ảnh shorts
```

---

## Các file trong thư mục crawler

| File | Chức năng |
|------|-----------|
| `run.py` | Điều phối chính — chạy tất cả từ đây |
| `config.py` | Cấu hình API key, thư mục, model AI |
| `scraper.py` | Lấy nội dung truyện từ website |
| `rewriter.py` | Viết lại truyện bằng AI |
| `docx_exporter.py` | Xuất file Word (.docx) |
| `seo_analyzer.py` | Tạo tiêu đề + mô tả SEO + URL đọc truyện |
| `hook_generator.py` | Tạo hook story 400-600 chữ cho Shorts |
| `shorts_pipeline.py` | Tạo ảnh cho từng scene Shorts |
| `merge_video.py` | Ghép ảnh + MP3 → video MP4 (shorts & long) |
| `organize.py` | Sắp xếp thư mục output theo ngày |
| `watchlist.py` | Theo dõi truyện cập nhật chương mới |
| `db_helper.py` | Thao tác với database SQLite |
| `srt_exporter.py` | Chuyển DOCX → phụ đề SRT |
| `label/` | Thư mục chứa PNG/MP4 để overlay lên video |
