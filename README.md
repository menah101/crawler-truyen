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
| [Social Publisher](docs/social_publisher.md) | Chia sẻ truyện lên Telegram/Discord/X tự động | `social_publisher.py` |
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
| [Chapter Wrapper](docs/chapter_wrapper.md) | Sinh summary/highlight/nextPreview cho mỗi chương (AdSense §1) | `chapter_wrapper.py` |
| [Novel Wrapper](docs/novel_wrapper.md) | Sinh review/analysis/FAQ cho mỗi truyện (AdSense §2) | `novel_wrapper.py` |
| [AdSense Recovery](docs/adsense_recovery.md) | Playbook khi bị reject "Low-value content" | `audit_indexable.py`, §1+§2+§5 |
| [Wrapper Sync](docs/wrapper_sync.md) | Push editorial wrappers từ local → pi4 qua HTTP | `wrapper_sync.py`, `/api/admin/wrappers` |
| [Cách 3 — HTTP Sync](docs/cach_3_http_sync.md) | Concept + setup: vì sao chọn HTTP, so sánh 3 phương án | `wrapper_sync.py` |
| [Audit Indexable](docs/audit.md) | Quét content nguy cơ AdSense reject (5 nhóm signal) | `audit_indexable.py` |
| [Chapter Splitter](docs/chapter_splitter.md) | Tách chương cho thin novels — giữ 100% nội dung | `chapter_splitter.py` |
| [Chapter Merger](docs/chapter_merger.md) | Gộp chương ngắn (< 300 từ) vào chương kế trước/sau | `chapter_merger.py` |
| [API Client](docs/api_client.md) | POST truyện mới lên pi4 (`IMPORT_MODE="api"`) | `api_client.py`, `/api/admin/import` |
| [TTS Generator](docs/tts.md) | Edge TTS — chuyển chapters thành MP3 | `tts_generator.py` |
| [Push Audio](docs/push_audio.md) | Đẩy MP3 chương từ docx_output/ → pi4 (S3 + Chapter.audioUrl) | `push_audio_to_pi4.py`, `/api/admin/upload-audio` |
| [Quy trình A-Z](docs/quy_trinh_a_z.md) | Playbook tổng từ crawl → wrap → sync pi4 | `run.py`, `workflow_full.sh` |
| [Daily Pipeline](docs/daily_pipeline.md) | Crawl 5 truyện/ngày từ JSON + wrap + sync pi4 (cron-friendly) | `daily_pipeline.sh`, `push_to_pi4.py` |

---

## Quick Start

```bash
cd crawler
pip install -r requirements.txt

# Tải + tạo toàn bộ nội dung cùng lúc
python run.py --url "https://yeungontinh.baby/truyen/ten-truyen/" --seo --images --shorts
```

### LLM provider — 2 setting riêng

`crawler/config.py` tách provider theo task để tối ưu cost vs chất lượng:

| Setting | Default | Dùng cho |
|---------|---------|----------|
| `REWRITE_PROVIDER` | `gemini` | crawl, split, retitle, hook (rẻ, tốn nhiều token) |
| `WRAP_PROVIDER` | `anthropic` | wrap §1 + §2 (chất lượng cao, hiển thị trên web) |

`.env` chỉ cần API key:
```bash
GEMINI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...
```

Cost ước tính 100 truyện × 50 chương: **~$30** (vs ~$200 nếu dùng full Anthropic). Xem [docs/setup.md](docs/setup.md#chọn-llm-provider).

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
python run.py --shorts-from-dir docx_output/YYYY-MM-DD/ten-truyen   # không cần DB
python run.py --cover-only "tên truyện"

# ── Rewrite lại chương đã có ──────────────────────────────────
python run.py --rewrite-from-dir docx_output/YYYY-MM-DD/ten-truyen/chapters
python run.py --rewrite-from-dir docx_output/.../chapters --rewrite-chapter 1 3

# ── Editorial wrapper (AdSense §1 + §2) ───────────────────────
python run.py --wrap-slug "ten truyen"            # summary/highlight cho mọi chương
python run.py --review-slug "ten truyen"          # review/analysis/FAQ cho novel
python run.py --review-all                        # wrap §2 cho tất cả truyện
python audit_indexable.py                         # audit content mỏng / chưa wrap
python run.py --sync-wrappers                     # đẩy wrapper local → pi4 qua HTTP

# ── Chia sẻ truyện lên MXH ────────────────────────────────────
python run.py --social-publish docx_output/YYYY-MM-DD/ten-truyen --social-dry-run
python run.py --social-publish docx_output/YYYY-MM-DD/ten-truyen --social-only telegram,discord

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
| `social_publisher.py` | Đăng truyện lên Telegram/Discord/X | [Social Publisher](docs/social_publisher.md) |
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
| `chapter_wrapper.py` | Sinh editorial cho mỗi chương | [Chapter Wrapper](docs/chapter_wrapper.md) |
| `novel_wrapper.py` | Sinh editorial + FAQ cho mỗi truyện | [Novel Wrapper](docs/novel_wrapper.md) |
| `audit_indexable.py` | Audit AdSense-risk content | [Audit](docs/audit.md) |
| `chapter_splitter.py` | Tách thin novels thành nhiều chương | [Chapter Splitter](docs/chapter_splitter.md) |
| `chapter_merger.py` | Gộp chương ngắn vào chương kế trước/sau | [Chapter Merger](docs/chapter_merger.md) |
| `push_to_pi4.py` | Push novel mới local → pi4 qua /api/admin/import | [Daily Pipeline](docs/daily_pipeline.md) |
| `daily_pipeline.sh` | Orchestrator crawl 5 truyện/ngày + sync pi4 | [Daily Pipeline](docs/daily_pipeline.md) |
| `wrapper_sync.py` | Push wrapper local → pi4 qua HTTP | [Wrapper Sync](docs/wrapper_sync.md) |
| `tts_generator.py` | Edge TTS chapters → MP3 | [TTS](docs/tts.md) |
| `push_audio_to_pi4.py` | Đẩy MP3 chương từ docx_output/ → pi4 (S3 + DB) | [Push Audio](docs/push_audio.md) |
| `api_client.py` | POST novel mới lên pi4 (IMPORT_MODE='api') | [API Client](docs/api_client.md) |
| `srt_exporter.py` | Chuyển DOCX → phụ đề SRT | [Video](docs/merge_video.md) |
| `translator.py` | Dịch Anh → Việt (chỉ dùng cho `sources/webnovel.py`) | — |
| `test_faces.py` | Test nhận diện khuôn mặt (dev tool) | — |
