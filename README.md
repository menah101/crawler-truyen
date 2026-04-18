# Hồng Trần Truyện — Crawler & Content Pipeline

Công cụ tự động tải truyện, viết lại bằng AI, và tạo nội dung cho kênh **Hồng Trần Truyện Audio** (YouTube / TikTok / Web).

---

## Tài liệu chi tiết

| Tài liệu | Mô tả | Module |
|-----------|--------|--------|
| [Cài đặt & Cấu hình](docs/setup.md) | Cài đặt lần đầu, cấu hình `.env` | `config.py` |
| [Scraper](docs/scraper.md) | Tải truyện từ nhiều nguồn | `scraper.py`, `run.py` |
| [Rewriter](docs/rewriter.md) | Viết lại truyện bằng AI, fallback chain | `rewriter.py` |
| [Chapter Rewriter](docs/chapter_rewriter.md) | Rewrite lại chapters/*.json đã có (in-place + backup) | `chapter_rewriter.py` |
| [DOCX Exporter](docs/docx_exporter.md) | Xuất file Word (.docx) | `docx_exporter.py` |
| [SEO Analyzer](docs/seo_analyzer.md) | Tiêu đề YouTube, mô tả, hashtag, tags website | `seo_analyzer.py` |
| [Image Generator](docs/image_generator.md) | Tạo 30 ảnh thumbnail 16:9 bằng FLUX | `image_generator.py`, `hf_image.py` |
| [Thumbnail Generator](docs/thumbnail_generator.md) | Tạo thumbnail YouTube từ ảnh + tiêu đề SEO | `thumbnail_generator.py` |
| [Shorts Pipeline](docs/shorts_pipeline.md) | Hook story + 8 cảnh ảnh → video Shorts | `shorts_pipeline.py`, `hook_generator.py` |
| [Merge Video](docs/merge_video.md) | Ghép video long-form, Ken Burns, subtitle | `merge_video.py` |
| [Overlay Label](docs/overlay_label.md) | Chèn logo/branding lên video | `merge_video.py` |
| [Cover Generator](docs/cover_generator.md) | Tạo ảnh bìa AI + FLUX | `cover_generator.py` |
| [Organize](docs/organize.md) | Sắp xếp thư mục output theo ngày | `organize.py` |
| [Watchlist](docs/watchlist.md) | Theo dõi truyện, tải chương mới tự động | `watchlist.py` |
| [Database](docs/database.md) | Quản lý DB, chuẩn hóa mô tả | `db_helper.py`, `normalize_descriptions.py` |
| [Vietnamese LLM Correct](docs/vi_llm_correct.md) | Sửa âm tiết tiếng Việt bị hỏng bằng AI | `vi_llm_correct.py`, `vi_validator.py` |

---

## Quick Start

```bash
cd crawler
pip install -r requirements.txt

# Tải + tạo toàn bộ nội dung cùng lúc
python run.py --url "https://yeungontinh.baby/truyen/ten-truyen/" --seo --images --shorts
```

---

## Sơ đồ luồng

```
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 1 — TẢI & TẠO NỘI DUNG                               │
│                                                             │
│  python run.py --url "URL" --seo --images --shorts          │
│         │                                                   │
│         ├── Crawl + viết lại bằng AI → database            │
│         ├── Xuất DOCX → ten-truyen.docx                     │
│         ├── Phân tích SEO → seo.txt                         │
│         ├── Tạo 30 thumbnail 16:9 → thumbnails/            │
│         ├── Tạo hook story + 8 ảnh → shorts/               │
│         └── Tạo ảnh bìa AI → cover.jpg                     │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 2 — THU ÂM / TTS                                      │
│                                                             │
│  • hook_story.txt → voice.mp3 (Shorts)                     │
│  • ten-truyen.docx → ten-truyen.mp3 (Long-form)            │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 3 — GHÉP VIDEO                                        │
│                                                             │
│  Shorts:    python merge_video.py shorts --latest           │
│  Long-form: python merge_video.py long --latest             │
│                                                             │
│  Thumbnail: python thumbnail_generator.py <novel_dir>       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  BƯỚC 4 — ĐĂNG LÊN                                         │
│                                                             │
│  • TikTok / Reels / YouTube Shorts ← _shorts.mp4           │
│  • YouTube Video ← _long.mp4 + thumbnail_youtube.jpg       │
│  • Copy tiêu đề + mô tả + hashtag từ seo.txt               │
└─────────────────────────────────────────────────────────────┘
```

---

## Cấu trúc thư mục output

```
docx_output/
  2026-03-25/
    ten-truyen/
      ten-truyen.docx             ← Truyện đã viết lại
      seo.txt                     ← SEO YouTube + tags website
      cover.jpg                   ← Ảnh bìa AI
      thumbnail_youtube.jpg       ← Thumbnail YouTube (1280×720)
      thumbnails/                 ← 30 ảnh 16:9 cho video
      shorts/                     ← Hook story + 8 cảnh + video Shorts
      long/                       ← Audio + video Long-form
```

---

## Lệnh tham khảo nhanh

```bash
# ── Tải + tạo tất cả ──────────────────────────────────────────
python run.py --url "URL" --seo --images --shorts

# ── Thumbnail YouTube ─────────────────────────────────────────
python thumbnail_generator.py docx_output/YYYY-MM-DD/ten-truyen
python thumbnail_generator.py docx_output/YYYY-MM-DD/ten-truyen --title-index 3

# ── Ghép video Shorts ─────────────────────────────────────────
python merge_video.py shorts --latest --fade --zoom alternate --label --subtitle

# ── Ghép video Long-form ──────────────────────────────────────
python merge_video.py long --latest --per-image 10 --zoom alternate --label --subtitle

# ── Tạo lại riêng lẻ (không crawl lại) ────────────────────────
python run.py --seo-only "tên truyện"
python run.py --images-only "tên truyện"
python run.py --shorts-only "tên truyện"
python run.py --cover-only "tên truyện"

# ── Rewrite lại chương đã có ──────────────────────────────────
python run.py --rewrite-from-dir docx_output/YYYY-MM-DD/ten-truyen/chapters
python run.py --rewrite-from-dir docx_output/.../chapters --rewrite-chapter 1 3

# ── Database ──────────────────────────────────────────────────
python run.py --db-list
python run.py --db-delete "tên truyện"

# ── Watchlist ─────────────────────────────────────────────────
python run.py --watch-add "URL"
python run.py --watch-download

# ── Sắp xếp thư mục ──────────────────────────────────────────
python organize.py --apply
```

---

## Tất cả các file

| File | Chức năng | Tài liệu |
|------|-----------|----------|
| `run.py` | Điều phối chính | [Scraper](docs/scraper.md) |
| `config.py` | Cấu hình API key, model AI | [Setup](docs/setup.md) |
| `scraper.py` | Lấy nội dung truyện từ website | [Scraper](docs/scraper.md) |
| `rewriter.py` | Viết lại truyện bằng AI | [Rewriter](docs/rewriter.md) |
| `chapter_rewriter.py` | Rewrite lại chapters/*.json đã có | [Chapter Rewriter](docs/chapter_rewriter.md) |
| `docx_exporter.py` | Xuất file Word (.docx) | [DOCX](docs/docx_exporter.md) |
| `seo_analyzer.py` | Tạo SEO YouTube + tags website | [SEO](docs/seo_analyzer.md) |
| `image_generator.py` | Tạo 30 ảnh thumbnail | [Images](docs/image_generator.md) |
| `hf_image.py` | Gọi FLUX.1-schnell API | [Images](docs/image_generator.md) |
| `thumbnail_generator.py` | Tạo thumbnail YouTube | [Thumbnail](docs/thumbnail_generator.md) |
| `hook_generator.py` | Tạo hook story cho Shorts | [Shorts](docs/shorts_pipeline.md) |
| `shorts_pipeline.py` | Tạo ảnh cho Shorts | [Shorts](docs/shorts_pipeline.md) |
| `merge_video.py` | Ghép video + label + subtitle | [Video](docs/merge_video.md) |
| `cover_generator.py` | Tạo ảnh bìa AI | [Cover](docs/cover_generator.md) |
| `organize.py` | Sắp xếp thư mục theo ngày | [Organize](docs/organize.md) |
| `watchlist.py` | Theo dõi truyện mới | [Watchlist](docs/watchlist.md) |
| `db_helper.py` | Thao tác database | [Database](docs/database.md) |
| `normalize_descriptions.py` | Chuẩn hóa mô tả truyện | [Database](docs/database.md) |
| `vi_llm_correct.py` | Sửa âm tiết tiếng Việt | [VI Correct](docs/vi_llm_correct.md) |
| `vi_validator.py` | Validate ngữ âm tiếng Việt | [VI Correct](docs/vi_llm_correct.md) |
| `srt_exporter.py` | Chuyển DOCX → phụ đề SRT | [Video](docs/merge_video.md) |
| `translator.py` | Dịch nội dung | — |
| `api_client.py` | API client cho remote import | — |
| `test_faces.py` | Test nhận diện khuôn mặt | — |
