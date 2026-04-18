# Cài đặt & Cấu hình

## Cài đặt lần đầu

```bash
cd crawler
pip install -r requirements.txt

# ffmpeg (cần để tạo video)
brew install ffmpeg          # macOS
# sudo apt install ffmpeg    # Ubuntu/Linux
```

> **Yêu cầu:** Python 3.11+

## Cấu hình .env

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
