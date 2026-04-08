"""
Cover Generator — Tạo ảnh bìa (cover) cho truyện khi crawl.

Quy trình:
1. Dùng AI phân tích truyện → xác định nhân vật chính, xung đột, cao trào, cảm xúc
2. Tạo 3 prompt theo 3 thể loại: Hiện đại / Hiện đại thập niên / Cổ trang
3. Chọn prompt phù hợp với thể loại truyện
4. Gọi FLUX.1-schnell tạo ảnh 9:16 (dọc, phù hợp bìa truyện)
5. Nén ảnh < 200KB
"""

import io
import logging
import re
import requests
from PIL import Image

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# ERA mapping từ genre slug → loại prompt cần chọn
# ─────────────────────────────────────────────────────────────────
_GENRE_TO_ERA = {
    "co-trang": "co-trang",
    "cung-dinh": "co-trang",
    "tien-hiep": "co-trang",
    "huyen-huyen": "co-trang",
    "vo-hiep": "co-trang",
    "lich-su": "co-trang",
    "xuyen-khong": "co-trang",

    "ngon-tinh": "hien-dai",
    "hien-dai": "hien-dai",
    "do-thi": "hien-dai",
    "hai-huoc": "hien-dai",
    "trong-sinh": "hien-dai",
    "dam-my": "hien-dai",
}

# ─────────────────────────────────────────────────────────────────
# PROMPT: yêu cầu AI phân tích truyện và tạo 3 prompt ảnh bìa
# ─────────────────────────────────────────────────────────────────

_COVER_ANALYSIS_PROMPT = """Bạn là chuyên gia tạo prompt hình ảnh cho ảnh bìa truyện châu Á.

Nhiệm vụ:
1. Đọc câu chuyện tôi cung cấp
2. Xác định:
   - Nhân vật chính (ngoại hình, tính cách)
   - Xung đột chính
   - Cao trào mạnh nhất
   - Cảm xúc chủ đạo
   - Bối cảnh nổi bật nhất
3. Chọn 1 khoảnh khắc ĐẮT GIÁ NHẤT phù hợp với thể loại truyện

Sau đó tạo CHÍNH XÁC 3 prompt TIẾNG ANH, tương ứng 3 thể loại:

1. Hiện đại (modern)
2. Hiện đại thập niên (republic / 80s–90s / military era)
3. Cổ trang (ancient / historical chinese)

YÊU CẦU BẮT BUỘC:
- Ảnh bìa DỌC (portrait 9:16) — nhân vật nổi bật trong frame
- Nhân vật PHẢI là người châu Á: "beautiful asian, east asian, chinese/vietnamese/korean appearance, black hair, dark almond eyes, porcelain skin, delicate facial features"
- Phong cách Á Đông: C-drama, K-drama, phim truyền hình Việt Nam, manhwa, donghua
- Loại trừ: "no western features, no european, no caucasian, no blonde hair, no blue eyes"
- KHÔNG có text: "no text, no watermark, no title, no subtitle"
- Phong cách: cinematic, dramatic, emotional, Asian drama aesthetic

BỐ CỤC ĐA DẠNG — chọn 1 trong các kiểu sau tùy nội dung truyện:
  * Chân dung cảm xúc: 1 nhân vật close-up từ đầu đến vai, cảm xúc mãnh liệt trên gương mặt
  * Đối đầu: 2 nhân vật đối mặt nhau, ánh mắt căng thẳng, khoảng cách giữa họ kể chuyện
  * Lưng quay: nhân vật quay lưng bước đi, bóng dáng cô đơn trong bối cảnh rộng
  * Ôm ấp/bảo vệ: 1 nhân vật ôm chặt người kia, cảm xúc bám víu tuyệt vọng
  * Cô đơn giữa cảnh rộng: nhân vật nhỏ bé giữa bối cảnh hoành tráng (cung điện, thành phố, mưa)
  * Bí ẩn: nhân vật nửa sáng nửa tối, gương mặt che khuất một nửa, tạo cảm giác bí ẩn
  * Phản bội: 1 nhân vật foreground đau đớn + 1-2 nhân vật background lạnh lùng bước đi
  * Hồi ức: nhân vật hiện tại mờ ảo + hình ảnh quá khứ hạnh phúc lồng ghép
  * Nguy hiểm: nhân vật trong tình huống căng thẳng (mưa bão, lửa cháy, vực thẳm)

Mô tả rõ:
  * ngoại hình châu Á (mắt hạnh nhân, da trắng, tóc đen, gương mặt thanh tú)
  * cảm xúc phù hợp với cảnh (không nhất thiết phải khóc — có thể lạnh lùng, quyết tâm, sợ hãi, yêu thương)
  * bố cục dọc portrait, ánh sáng cinematic
- Chất lượng: ultra realistic, 4k, depth of field
- Mỗi prompt PHẢI kết thúc bằng: "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"

FORMAT TRẢ VỀ (CHÍNH XÁC):

[HIEN_DAI]
(prompt tiếng Anh)

[THAP_NIEN]
(prompt tiếng Anh)

[CO_TRANG]
(prompt tiếng Anh)

KHÔNG giải thích. KHÔNG thêm chữ vào ảnh. CHỈ trả prompt."""


def _extract_prompts(ai_response: str) -> dict:
    """Parse AI response → dict với key: hien-dai, thap-nien, co-trang."""
    prompts = {}
    # Tìm từng section
    patterns = {
        "hien-dai": r'\[HIEN_DAI\]\s*\n(.+?)(?=\n\[|\Z)',
        "thap-nien": r'\[THAP_NIEN\]\s*\n(.+?)(?=\n\[|\Z)',
        "co-trang": r'\[CO_TRANG\]\s*\n(.+?)(?=\n\[|\Z)',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, ai_response, re.DOTALL)
        if match:
            prompt = match.group(1).strip()
            # Loại bỏ dấu ngoặc nếu AI thêm
            prompt = prompt.strip('()')
            prompts[key] = prompt

    return prompts


def _select_era(genres_str: str) -> str:
    """Chọn era phù hợp từ danh sách genre."""
    if not genres_str:
        return "co-trang"  # default

    for genre in genres_str.split(','):
        genre = genre.strip()
        if genre in _GENRE_TO_ERA:
            return _GENRE_TO_ERA[genre]

    return "co-trang"


# ─────────────────────────────────────────────────────────────────
# AI: gọi Gemini/HuggingFace để phân tích truyện → 3 prompts
# ─────────────────────────────────────────────────────────────────

def _analyze_with_gemini(story_text: str, api_key: str) -> str | None:
    """Gọi Gemini để phân tích truyện và tạo 3 prompt."""
    try:
        from config import GEMINI_MODEL, GEMINI_FALLBACK_MODELS
    except ImportError:
        GEMINI_MODEL = "gemini-2.5-flash-lite"
        GEMINI_FALLBACK_MODELS = []

    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    full_prompt = f"{_COVER_ANALYSIS_PROMPT}\n\n---\n\nCâu chuyện:\n{story_text}"

    for m in models:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048},
                },
                timeout=120,
            )
        except Exception as e:
            logger.error(f"  ❌ Cover Gemini {m} error: {e}")
            continue

        if resp.status_code == 429:
            logger.warning(f"  ⚠️ Cover Gemini {m}: rate limit (429)")
            continue

        if resp.status_code != 200:
            logger.error(f"  ❌ Cover Gemini {m}: {resp.status_code}")
            continue

        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return parts[0]["text"].strip()
        except (KeyError, IndexError, TypeError):
            continue

    return None


def _analyze_with_huggingface(story_text: str, api_token: str) -> str | None:
    """Gọi HuggingFace để phân tích truyện và tạo 3 prompt."""
    try:
        from config import HF_REWRITE_MODEL, HF_REWRITE_FALLBACK_MODELS
    except ImportError:
        HF_REWRITE_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        HF_REWRITE_FALLBACK_MODELS = []

    models = [HF_REWRITE_MODEL] + [m for m in HF_REWRITE_FALLBACK_MODELS if m != HF_REWRITE_MODEL]
    full_prompt = f"{_COVER_ANALYSIS_PROMPT}\n\n---\n\nCâu chuyện:\n{story_text}"

    for m in models:
        try:
            resp = requests.post(
                "https://router.huggingface.co/together/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": m,
                    "max_tokens": 2048,
                    "temperature": 0.9,
                    "messages": [{"role": "user", "content": full_prompt}],
                },
                timeout=180,
            )
        except Exception as e:
            logger.error(f"  ❌ Cover HF {m} error: {e}")
            continue

        if resp.status_code in (429, 503):
            logger.warning(f"  ⚠️ Cover HF {m}: {resp.status_code}")
            continue

        if resp.status_code != 200:
            logger.error(f"  ❌ Cover HF {m}: {resp.status_code}")
            continue

        try:
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            continue

    return None


def _analyze_story(description: str, chapters: list, genres_str: str) -> str | None:
    """
    Phân tích truyện bằng AI → trả về raw AI response.
    Ưu tiên: Gemini → HuggingFace.
    """
    # Chuẩn bị text cho AI (mô tả + 3 chương đầu, giới hạn ~3000 ký tự)
    story_parts = []
    if description:
        story_parts.append(f"Mô tả: {description}")

    # Lấy nội dung 3 chương đầu (hoặc ít hơn)
    for ch in chapters[:3]:
        content = ch.get('content', '')
        if content:
            # Giới hạn mỗi chương ~800 ký tự
            story_parts.append(f"--- Chương {ch.get('number', '?')} ---\n{content[:800]}")

    story_text = "\n\n".join(story_parts)
    if not story_text:
        return None

    # Giới hạn tổng text gửi AI
    story_text = story_text[:4000]

    try:
        from config import GEMINI_API_KEY, HF_API_TOKEN
    except ImportError:
        GEMINI_API_KEY = ""
        HF_API_TOKEN = ""

    # Thử Gemini trước
    if GEMINI_API_KEY:
        result = _analyze_with_gemini(story_text, GEMINI_API_KEY)
        if result:
            return result

    # Fallback: HuggingFace
    if HF_API_TOKEN:
        result = _analyze_with_huggingface(story_text, HF_API_TOKEN)
        if result:
            return result

    logger.warning("  ⚠️ Không thể phân tích truyện cho cover — thiếu API key")
    return None


# ─────────────────────────────────────────────────────────────────
# Image: gọi FLUX.1-schnell tạo ảnh + nén < 200KB
# ─────────────────────────────────────────────────────────────────

# Kích thước 9:16 tối ưu cho FLUX (bội số 64) — dọc, phù hợp bìa truyện
_COVER_WIDTH = 768
_COVER_HEIGHT = 1344

# NSFW filter
_NSFW_KEYWORDS = [
    "nude", "nudity", "naked", "sex", "sexual", "erotic", "porn",
    "breast", "nipples", "genitals", "nsfw", "lingerie", "topless",
    "bare skin", "exposed skin", "undressed", "revealing outfit",
    "shirtless", "bikini", "underwear",
]

# Negative concepts (FLUX không có negative prompt riêng)
_NEGATIVE_SUFFIX = (
    "portrait orientation 9:16, asian drama aesthetic, "
    "beautiful asian east asian features, black hair, dark almond eyes, porcelain skin, "
    "safe for work, fully clothed characters, no nudity, no bare skin, "
    "no text, no watermark, no title, no words on image, no subtitle, "
    "no western features, no blonde hair, no blue eyes, "
    "perfect anatomy, correct human body, no extra limbs, no deformed hands"
)


def _is_safe(prompt: str) -> bool:
    low = prompt.lower()
    return not any(w in low for w in _NSFW_KEYWORDS)


def _generate_flux_image(prompt: str, api_token: str) -> Image.Image | None:
    """Gọi FLUX.1-schnell tạo ảnh 9:16 (portrait)."""
    try:
        from config import HF_IMAGE_MODEL
    except ImportError:
        HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

    api_url = f"https://router.huggingface.co/hf-inference/models/{HF_IMAGE_MODEL}"

    # Thêm negative suffix + safety
    full_prompt = f"{prompt}, {_NEGATIVE_SUFFIX}"

    try:
        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_token}"},
            json={
                "inputs": full_prompt,
                "parameters": {
                    "width": _COVER_WIDTH,
                    "height": _COVER_HEIGHT,
                    "num_inference_steps": 12,    # nhiều steps hơn cho cover quality
                    "guidance_scale": 3.5,
                },
            },
            timeout=120,
        )

        if resp.status_code != 200:
            logger.error(f"  ❌ FLUX error: {resp.status_code} — {resp.text[:200]}")
            return None

        return Image.open(io.BytesIO(resp.content))

    except Exception as e:
        logger.error(f"  ❌ FLUX image generation error: {e}")
        return None


def _compress_image(img: Image.Image, max_size_kb: int = 200) -> bytes:
    """Nén ảnh JPEG < max_size_kb KB."""
    # Thử quality từ cao → thấp
    for quality in [90, 85, 80, 75, 70, 60, 50, 40]:
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        size_kb = buf.tell() / 1024
        if size_kb <= max_size_kb:
            return buf.getvalue()

    # Nếu vẫn lớn, resize nhỏ hơn rồi nén lại
    w, h = img.size
    img_small = img.resize((w * 3 // 4, h * 3 // 4), Image.LANCZOS)
    for quality in [80, 70, 60, 50]:
        buf = io.BytesIO()
        img_small.save(buf, format='JPEG', quality=quality, optimize=True)
        size_kb = buf.tell() / 1024
        if size_kb <= max_size_kb:
            return buf.getvalue()

    # Fallback: resize rất nhỏ
    img_tiny = img.resize((w // 2, h // 2), Image.LANCZOS)
    buf = io.BytesIO()
    img_tiny.save(buf, format='JPEG', quality=60, optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────
# FALLBACK: prompt mặc định khi AI không khả dụng
# ─────────────────────────────────────────────────────────────────

import random as _random

# Mỗi era có nhiều fallback — random chọn 1 để đa dạng bố cục
_FALLBACK_PROMPTS = {
    "co-trang": [
        (   # Chân dung cảm xúc
            "C-drama ancient Chinese drama poster, portrait composition 9:16, "
            "beautiful asian woman extreme close-up from face to shoulders, "
            "long flowing black hair with gold hairpin, porcelain skin, dark almond eyes, "
            "single tear rolling down cheek, intense emotional gaze, "
            "wearing crimson hanfu, cherry blossoms falling around her, "
            "dramatic rim light on hair, shallow depth of field, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
        (   # Cô đơn giữa cảnh rộng
            "C-drama ancient Chinese drama poster, portrait composition 9:16, "
            "beautiful asian woman in white hanfu standing alone on moonlit stone bridge, "
            "small figure against vast misty mountain landscape, black hair flowing in wind, "
            "porcelain skin, delicate features, melancholy atmosphere, "
            "red lanterns reflected on water below, fog and cherry petals in air, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
        (   # Đối đầu
            "C-drama ancient Chinese drama poster, portrait composition 9:16, "
            "two beautiful asian people facing each other in grand palace hall, "
            "woman in red hanfu and man in dark hanfu, intense eye contact, "
            "dramatic tension between them, golden candlelight, jade pillars, "
            "black hair, porcelain skin, delicate asian features, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
    ],
    "hien-dai": [
        (   # Lưng quay — cô đơn
            "K-drama modern Asian romance poster, portrait composition 9:16, "
            "beautiful asian woman seen from behind walking alone in rainy city street at night, "
            "straight black hair, elegant coat, holding broken umbrella, "
            "neon lights reflecting on wet pavement, lonely silhouette, "
            "city bokeh background, cinematic mood, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
        (   # Bí ẩn — nửa sáng nửa tối
            "K-drama modern Asian drama poster, portrait composition 9:16, "
            "beautiful asian woman half-face portrait, split lighting, "
            "one side illuminated by warm golden light other side in deep shadow, "
            "glass skin, dark almond eyes with mysterious gaze, straight black hair, "
            "modern elegant outfit, abstract city reflection on glass, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
        (   # Ôm ấp/bảo vệ
            "K-drama modern Asian romance poster, portrait composition 9:16, "
            "handsome asian man embracing beautiful asian woman from behind protectively, "
            "her eyes closed with relieved expression, his determined protective gaze, "
            "both with black hair, delicate asian features, modern casual clothes, "
            "warm golden hour light through apartment window, intimate emotional moment, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
    ],
    "thap-nien": [
        (   # Hồi ức
            "Vietnamese drama 1980s poster, portrait composition 9:16, "
            "double exposure effect, beautiful vietnamese woman with black hair in vintage ao dai, "
            "present-day sad expression overlaid with ghostly happy memory of couple laughing, "
            "porcelain skin, dark eyes, delicate asian features, "
            "warm Kodachrome tones, film grain, vintage aesthetic, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
        (   # Nguy hiểm/căng thẳng
            "Vietnamese drama 1980s poster, portrait composition 9:16, "
            "beautiful vietnamese woman with black hair standing in heavy rain at old harbor, "
            "vintage ao dai soaked, determined fierce gaze, storm clouds above, "
            "porcelain skin, dark eyes, delicate asian features, "
            "dramatic lightning illuminating her face, vintage film aesthetic, "
            "portrait orientation 9:16, asian drama aesthetic, no text, no watermark, "
            "no words on image, ultra realistic, 4k, depth of field, cinematic, dramatic lighting, high contrast"
        ),
    ],
}


def _get_fallback_prompt(era: str) -> str:
    """Random chọn 1 fallback prompt từ pool."""
    prompts = _FALLBACK_PROMPTS.get(era, _FALLBACK_PROMPTS["co-trang"])
    return _random.choice(prompts)


# ─────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────

def generate_cover(
    title: str,
    description: str,
    genres_str: str,
    chapters: list,
    output_path: str | None = None,
) -> str | None:
    """
    Tạo ảnh bìa cho truyện.

    Args:
        title:       Tên truyện
        description: Mô tả truyện
        genres_str:  Danh sách genre (slug, phân cách bởi dấu phẩy)
        chapters:    List dict chapters [{'number': ..., 'content': ...}, ...]
        output_path: Đường dẫn lưu file (nếu None → lưu cùng thư mục truyện)

    Returns:
        Đường dẫn file cover đã tạo, hoặc None nếu thất bại
    """
    try:
        from config import HF_API_TOKEN
    except ImportError:
        HF_API_TOKEN = ""

    if not HF_API_TOKEN:
        logger.warning("  ⚠️ HF_API_TOKEN chưa cấu hình — bỏ qua tạo cover")
        return None

    logger.info(f"  🎨 Đang tạo cover cho: {title}")

    # 1. Xác định era từ genre
    era = _select_era(genres_str)
    logger.info(f"     Era: {era}")

    # 2. Phân tích truyện bằng AI → 3 prompts
    ai_response = _analyze_story(description, chapters, genres_str)

    if ai_response:
        prompts = _extract_prompts(ai_response)
        # Chọn prompt theo era
        selected_prompt = prompts.get(era)

        # Fallback: thử era khác nếu không có
        if not selected_prompt:
            for key in ["hien-dai", "co-trang", "thap-nien"]:
                if key in prompts:
                    selected_prompt = prompts[key]
                    logger.info(f"     Fallback: dùng prompt [{key}] thay [{era}]")
                    break

        if selected_prompt:
            logger.info(f"     Prompt AI: {selected_prompt[:100]}...")
        else:
            logger.warning("     AI không trả đúng format — dùng prompt mặc định")
            selected_prompt = None
    else:
        selected_prompt = None

    # Fallback: dùng prompt mặc định (random từ pool)
    if not selected_prompt:
        selected_prompt = _get_fallback_prompt(era)
        logger.info(f"     Dùng prompt mặc định [{era}]")

    # Safety check
    if not _is_safe(selected_prompt):
        logger.warning("     Prompt không an toàn — dùng fallback")
        selected_prompt = _get_fallback_prompt(era)

    # 3. Tạo ảnh bằng FLUX
    logger.info("     Đang gọi FLUX.1-schnell tạo ảnh 9:16 (portrait)...")
    img = _generate_flux_image(selected_prompt, HF_API_TOKEN)
    if img is None:
        logger.error("  ❌ Không tạo được ảnh cover")
        return None

    # 4. Nén < 200KB
    img_bytes = _compress_image(img, max_size_kb=200)
    size_kb = len(img_bytes) / 1024
    logger.info(f"     Ảnh: {img.size[0]}x{img.size[1]} — {size_kb:.0f}KB")

    # 5. Lưu file
    if not output_path:
        import os
        from datetime import datetime
        try:
            from config import DOCX_OUTPUT_DIR
        except ImportError:
            DOCX_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'docx_output')
        from docx_exporter import _slugify
        today = datetime.now().strftime('%Y-%m-%d')
        novel_dir = os.path.join(DOCX_OUTPUT_DIR, today, _slugify(title))
        os.makedirs(novel_dir, exist_ok=True)
        output_path = os.path.join(novel_dir, 'cover.jpg')

    # Đảm bảo thư mục tồn tại
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'wb') as f:
        f.write(img_bytes)

    logger.info(f"  ✅ Cover đã lưu: {output_path}")
    return output_path


def generate_cover_from_dir(
    chapters_dir: str,
    genres_str: str = "",
) -> str | None:
    """
    Tạo cover từ thư mục chapters JSON đã có.

    Args:
        chapters_dir: Đường dẫn đến thư mục chapters/ chứa các file .json
        genres_str:   Genre slug (tuỳ chọn, dùng để chọn era)

    Returns:
        Đường dẫn file cover.jpg hoặc None
    """
    import os
    import json

    if not os.path.isdir(chapters_dir):
        logger.error(f"  ❌ Thư mục không tồn tại: {chapters_dir}")
        return None

    # Đọc chapters từ JSON
    chapters = []
    json_files = sorted(f for f in os.listdir(chapters_dir) if f.endswith('.json'))
    if not json_files:
        logger.error(f"  ❌ Không tìm thấy file .json trong: {chapters_dir}")
        return None

    for jf in json_files:
        try:
            with open(os.path.join(chapters_dir, jf), encoding='utf-8') as f:
                ch = json.load(f)
                chapters.append(ch)
        except Exception as e:
            logger.warning(f"  ⚠️ Lỗi đọc {jf}: {e}")

    if not chapters:
        logger.error("  ❌ Không đọc được chapter nào")
        return None

    # Xác định novel_dir (parent của chapters/)
    novel_dir = os.path.dirname(chapters_dir.rstrip('/'))
    title = os.path.basename(novel_dir)
    output_path = os.path.join(novel_dir, 'cover.jpg')

    # Tìm description từ chapter đầu (dùng nội dung chương 1 làm context)
    description = ""

    logger.info(f"  🎨 Tạo cover từ {len(chapters)} chương trong: {chapters_dir}")
    return generate_cover(
        title=title,
        description=description,
        genres_str=genres_str,
        chapters=chapters,
        output_path=output_path,
    )


def generate_cover_from_prompt(
    prompt: str,
    output_path: str,
) -> str | None:
    """
    Tạo cover từ prompt có sẵn (không cần AI phân tích).
    Hữu ích khi muốn test hoặc chạy thủ công.
    """
    try:
        from config import HF_API_TOKEN
    except ImportError:
        HF_API_TOKEN = ""

    if not HF_API_TOKEN:
        logger.warning("  ⚠️ HF_API_TOKEN chưa cấu hình")
        return None

    if not _is_safe(prompt):
        logger.warning("  Prompt không an toàn")
        return None

    img = _generate_flux_image(prompt, HF_API_TOKEN)
    if img is None:
        return None

    import os
    img_bytes = _compress_image(img, max_size_kb=200)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'wb') as f:
        f.write(img_bytes)

    logger.info(f"  ✅ Cover: {output_path} ({len(img_bytes) / 1024:.0f}KB)")
    return output_path
