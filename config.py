"""
Cấu hình crawler — nguồn: yeungontinh.baby
"""

import os

try:
    from dotenv import load_dotenv
    for p in [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', '.env.local'),
    ]:
        if os.path.exists(p):
            load_dotenv(p)
except ImportError:
    pass

# === Import mode ===
# "local" — ghi trực tiếp vào SQLite qua db_helper.py (cần chạy cùng máy với DB)
# "api"   — POST lên RPi qua /api/admin/import (crawler chạy trên máy khác)
IMPORT_MODE  = os.environ.get("IMPORT_MODE", "local")   # "local" | "api"
API_BASE_URL = os.environ.get("API_BASE_URL", "http://192.168.1.x:3000")
API_SECRET   = os.environ.get("IMPORT_SECRET", "")

# === Database (dùng cho IMPORT_MODE="local") ===
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'prisma', 'dev.db')

# === Lịch crawl ===
CRAWL_SCHEDULE = "08:00"
REQUEST_DELAY = 1.5

# === Rewriter thứ tự model được yêu tiên ===
# LƯU Ý: Llama (huggingface/groq) có lỗi tokenizer với tiếng Việt → sinh ra
# chữ hỏng kiểu "mắững", "tôôi", "vọững". Khuyên dùng Gemini/Claude/DeepSeek.
REWRITE_ENABLED = True
# Provider cho REWRITE (crawl chương) + splitter + retitle + hook + rewriter:
REWRITE_PROVIDER = "gemini"    # 1."gemini" | 2."anthropic" | 3."deepseek" | 4."groq" | 5."huggingface" | 6."ollama" | 7."local"
# Provider riêng cho WRAP §1 (chapter_wrapper) + WRAP §2 (novel_wrapper).
# Tách riêng vì wrap là content có giá trị cao (review/analysis/FAQ), nên dùng
# model mạnh hơn (Anthropic) — còn rewrite/split tốn nhiều token, dùng Gemini cho rẻ.
# Chỉ chấp nhận "gemini" hoặc "anthropic" (fallthrough sang Ollama nếu khác).
WRAP_PROVIDER    = "anthropic"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"    # Ưu tiên flash > flash-lite cho chất lượng tiếng Việt
GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"   # hoặc "deepseek-reasoner"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:12b")   # gemma3:12b (~8GB) | gemma3:4b (~3GB) | qwen2.5:7b

HF_REWRITE_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
HF_REWRITE_FALLBACK_MODELS = [
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",  # nhanh, tiếng Việt tốt
    "deepseek-ai/DeepSeek-V3",                   # chất lượng cao
    "deepseek-ai/DeepSeek-R1",                   # reasoning, chậm hơn
]

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
# Fallback models khi bị rate limit (theo thứ tự ưu tiên)
GROQ_FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",   # 12k TPM free
    "llama-3.1-8b-instant",      # 20k TPM free
    "llama3-70b-8192",           # fallback thêm
]

# === Validator LLM narrow-pass ===
# Sau khi vi_validator rule-based chạy xong, nếu còn âm tiết không tự sửa
# được thì gọi Gemini để sửa với ngữ cảnh câu.
VI_LLM_FIX_ENABLED = os.environ.get("VI_LLM_FIX_ENABLED", "true").lower() == "true"
VI_LLM_FIX_MODEL = "gemini-2.5-flash"
VI_LLM_FIX_MAX_CHARS = 8000   # cắt text gửi LLM để tiết kiệm token

REWRITE_CHUNK_SIZE = 1200   # DeepSeek/Gemini: 1200 chars input → ~2500 chars output an toàn trong 8192 tokens
REWRITE_CHUNK_SIZE_OLLAMA = 600   # Ollama local model: nhỏ hơn để model follow instruction tốt hơn
REWRITE_DELAY = 5.0         # Tăng delay giữa các chunk

# === Fake ranking data (tạo cảm giác truyện đã có nhiều người đọc & đánh giá) ===
FAKE_VIEWS_ENABLED = True
NOVEL_VIEWS_MIN   = 15_000   # lượt xem tối thiểu cho novel
NOVEL_VIEWS_MAX   = 280_000  # lượt xem tối đa cho novel
# Chương đầu = 100% views, chương cuối ~= CHAPTER_VIEWS_TAIL_RATIO * chapter_1_views
CHAPTER_VIEWS_TAIL_RATIO = 0.15  # 15% của chương đầu

# Rating: điểm ngẫu nhiên thực tế (3.5–4.9 sao)
NOVEL_RATING_MIN  = 3.5
NOVEL_RATING_MAX  = 4.9
# ratingCount ≈ RATING_RATE % của viewCount (ví dụ: 100k views → ~500–2000 đánh giá)
NOVEL_RATING_RATE_MIN = 0.005   # 0.5% views
NOVEL_RATING_RATE_MAX = 0.020   # 2.0% views

# === Website ===
SITE_URL = os.environ.get("SITE_URL", "https://hongtrantruyen.net")

# === DOCX Export ===
# Xuất truyện đã viết lại ra file .docx sau khi crawl xong
DOCX_EXPORT_ENABLED = os.environ.get("DOCX_EXPORT_ENABLED", "false").lower() == "true"
DOCX_OUTPUT_DIR     = os.environ.get("DOCX_OUTPUT_DIR",
                          os.path.join(os.path.dirname(__file__), 'docx_output'))
DOCX_CHANNEL_NAME   = os.environ.get("DOCX_CHANNEL_NAME", "")   # VD: "Hồng Trần Truyện"

# === SRT Export ===
# Chuyển file DOCX đã xuất sang phụ đề SRT
SRT_EXPORT_ENABLED    = os.environ.get("SRT_EXPORT_ENABLED", "false").lower() == "true"
SRT_OUTPUT_DIR        = os.environ.get("SRT_OUTPUT_DIR",
                            os.path.join(os.path.dirname(__file__), 'docx_output'))
SRT_DURATION_PER_LINE = float(os.environ.get("SRT_DURATION_PER_LINE", "20"))
SRT_WORDS_PER_SECOND  = float(os.environ.get("SRT_WORDS_PER_SECOND", "0.25"))

# === HuggingFace (image generation — FLUX.1-schnell) ===
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
HF_IMAGE_STEPS = 4           # schnell works best with 1-4 steps

# Chain (model, provider) — thử tuần tự đến khi 1 combo trả ảnh. Cấu trúc
# phẳng này cho phép fallback QUA model khác khi model chính fail toàn bộ
# provider. Thứ tự: free → same-model paid → fallback-model paid.
#
# Entry format: (model_id, provider, attempts, delay_seconds).
#
# Giá tham khảo (tại thời điểm cấu hình, đọc lại HF billing dashboard):
#   • FLUX.1-schnell  — ~$0.003/ảnh  (4 steps, nhanh, aesthetic C-drama tốt)
#   • FLUX.1-dev      — ~$0.025/ảnh  (28 steps, chất lượng cao hơn schnell)
#   • SD 3.5 Large    — ~$0.065/ảnh  (khác family, last resort)
HF_IMAGE_CHAIN = [
    # Tier 1 — FLUX.1-schnell qua cả 3 provider (ưu tiên free)
    ("black-forest-labs/FLUX.1-schnell", "hf-inference", 1, 0),
    ("black-forest-labs/FLUX.1-schnell", "fal-ai",       1, 0),
    ("black-forest-labs/FLUX.1-schnell", "replicate",    1, 0),
    # Tier 2 — FLUX.1-dev (cùng family, chất lượng cao hơn — aesthetic vẫn
    # nhất quán với schnell). Bỏ qua hf-inference vì provider đã deprecate.
    ("black-forest-labs/FLUX.1-dev",     "fal-ai",       1, 0),
    ("black-forest-labs/FLUX.1-dev",     "replicate",    1, 0),
    # Tier 3 — SD 3.5 Large (khác family). Chỉ dùng khi FLUX toàn diện chết.
    ("stabilityai/stable-diffusion-3.5-large", "fal-ai", 1, 0),
]
# Kích thước tối ưu (bội số 64):
#   9:16 → 768×1344  (YouTube Shorts / TikTok)
#   16:9 → 1344×768  (YouTube Thumbnail)
HF_IMAGE_RATIO = os.environ.get("HF_IMAGE_RATIO", "9:16")   # "9:16" | "16:9" | "1:1"

# === Cover Generation (ảnh bìa truyện) ===
# Tự động tạo cover khi crawl truyện mới (dùng FLUX.1-schnell 16:9)
COVER_ENABLED = os.environ.get("COVER_ENABLED", "true").lower() == "true"
COVER_MAX_SIZE_KB = 200       # Nén ảnh cover < 200KB

# === Genre mapping ===
GENRE_MAP = {
    'ngôn tình': 'ngon-tinh',
    'cổ đại': 'co-trang',
    'cổ trang': 'co-trang',
    'tiên hiệp': 'tien-hiep',
    'huyền huyễn': 'huyen-huyen',
    'xuyên không': 'xuyen-khong',
    'đam mỹ': 'dam-my',
    'lịch sử': 'lich-su',
    'đô thị': 'do-thi',
    'hài hước': 'hai-huoc',
    'ngược': 'nguoc',
    'trọng sinh': 'trong-sinh',
    'cung đấu': 'cung-dinh',
    'cung đình': 'cung-dinh',
    'hiện đại': 'ngon-tinh',
    'nữ cường': 'co-trang',
    'học đường': 'ngon-tinh',
    # English genres (webnovel và các nguồn tiếng Anh khác)
    'romance': 'ngon-tinh',
    'fantasy': 'huyen-huyen',
    'eastern fantasy': 'tien-hiep',
    'xianxia': 'tien-hiep',
    'xuanhuan': 'huyen-huyen',
    'historical': 'lich-su',
    'historical romance': 'co-trang',
    'urban': 'do-thi',
    'urban life': 'do-thi',
    'comedy': 'hai-huoc',
    'action': 'huyen-huyen',
    'bl': 'dam-my',
    'boys love': 'dam-my',
    'transmigration': 'xuyen-khong',
    'reincarnation': 'trong-sinh',
    'palace intrigue': 'cung-dinh',
    'harem': 'ngon-tinh',
}
