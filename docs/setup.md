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
# ── API keys ──────────────────────────────────────────────────
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

## Chọn LLM provider

LLM được tách thành **2 setting riêng** trong [config.py](../config.py):

| Setting | Default | Dùng cho | Khuyến nghị |
|---------|---------|----------|-------------|
| `REWRITE_PROVIDER` | `gemini` | Rewrite chương khi crawl, splitter, retitle, hook story (shorts) | `gemini` — rẻ, nhanh, đủ chất lượng cho task tốn token |
| `WRAP_PROVIDER` | `anthropic` | Wrap §1 (chapter summary/highlight) + Wrap §2 (review/analysis/FAQ) | `anthropic` — chất lượng cao, ít CJK drift, content hiển thị trên web |

Sửa trong [`crawler/config.py`](../config.py) (không phải `.env`):

```python
REWRITE_PROVIDER = "gemini"      # cho crawl/split/retitle/hook
WRAP_PROVIDER    = "anthropic"   # cho wrap §1+§2
```

**Cả 2 chỉ chấp nhận `"gemini"` hoặc `"anthropic"`** — provider khác sẽ fallthrough về Ollama (cần `OLLAMA_BASE_URL` chạy local).

### Ước tính cost (cho 100 truyện × 50 chương)

| Task | Tokens | Gemini Flash | Claude Haiku 4.5 |
|------|--------|--------------|------------------|
| Rewrite (REWRITE) | ~50M | $25 | $200 |
| Split (REWRITE) | ~3M | $0.30 | $2.5 |
| Wrap §1 (WRAP) | ~5M | $0.50 | $4 |
| Wrap §2 (WRAP) | ~250K | $0.10 | $0.80 |

→ Setup mặc định (REWRITE=gemini, WRAP=anthropic): **~$30/100 truyện** thay vì $200 (full Anthropic) hoặc $26 (full Gemini, chất lượng wrap kém hơn).
