"""
Hook Generator — Chuyển truyện dài thành câu chuyện ngắn hook cho TikTok/YouTube Shorts.

Input:  Danh sách chương truyện (title, author, chapters)
Output: {
    "title":      "Tên truyện",
    "hook_story": "Nội dung đọc voice (400-600 chữ tiếng Việt)",
    "scenes": [
        {
            "scene":   1,
            "text":    "Câu cho scene này (1-2 câu)",
            "emotion": "shock / sadness / hope / ...",
        },
        ...  # 6-8 scenes
    ]
}
"""

import re
import logging

logger = logging.getLogger(__name__)


CJK_PUNCT_MAP = str.maketrans({
    '。': '.', '，': ',', '、': ',', '；': ';', '：': ':',
    '！': '!', '？': '?',
    '「': '"', '」': '"', '『': '"', '』': '"',
    '《': '"', '》': '"', '（': '(', '）': ')',
    '—': '—',
})

CJK_CHAR_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')


def _normalize_punctuation(text: str) -> str:
    """Đổi dấu câu Trung/Nhật sang Latin để LLM không bị drift sang CJK."""
    return text.translate(CJK_PUNCT_MAP)


def _has_cjk(text: str) -> bool:
    """True nếu text chứa chữ Hán/Hiragana/Katakana/Hangul."""
    return bool(CJK_CHAR_RE.search(text))


# ─────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────

HOOK_PROMPT_TEMPLATE = """Bạn là biên kịch chuyên làm video TikTok và YouTube Shorts cho kênh truyện audio tiếng Việt "Hồng Trần Truyện Audio".

⚠️ QUY TẮC NGÔN NGỮ TUYỆT ĐỐI (BẮT BUỘC):
- Toàn bộ output PHẢI 100% bằng tiếng Việt có dấu.
- KHÔNG được dùng BẤT KỲ ký tự Hán/Trung/Nhật/Hàn nào (漢字, 中文, かな, 한글).
- KHÔNG được dùng dấu câu Trung: 。 ， ； ： ！ ？ 「 」 『 』 《 》 — chỉ dùng `. , ; : ! ?` kiểu Latin.
- Nếu bạn thấy chữ Hán xuất hiện trong output của chính mình, DỪNG NGAY và viết lại bằng tiếng Việt.
- Tên nhân vật giữ nguyên âm Hán-Việt (VD: "Tô Tô", "Lục Chấp") — KHÔNG viết lại bằng chữ Hán.
- Chỉ các trường ACTION/SETTING/EMOTION/APPEARANCE được dùng tiếng Anh (đã quy định bên dưới).

Nhiệm vụ: Đọc nội dung truyện bên dưới và tạo ra một câu chuyện hook ngắn để làm video Shorts.

YÊU CẦU HOOK STORY:
- Độ dài: 400-600 từ tiếng Việt (tương đương 2-3 phút đọc)
- Bắt đầu NGAY VÀO CAO TRÀO — không giải thích bối cảnh dài dòng
- Dùng câu ngắn, giọng kể chuyện hấp dẫn, gây cảm xúc mạnh
- Tạo cliffhanger ở giữa và cuối để người xem muốn tìm hiểu thêm
- Kết thúc bằng câu kêu gọi nghe đầy đủ: "Nghe toàn bộ câu chuyện tại Hồng Trần Truyện Audio..."
- KHÔNG dùng tiêu đề chương, số chương

YÊU CẦU NHÂN VẬT & BỐI CẢNH:
Trước khi viết hook story, xác định:
1. Loại truyện (bắt buộc chọn 1):
   - CỔ TRANG: Trung Hoa phong kiến, nhân vật mặc hanfu, cung điện/vườn cổ
   - HIỆN ĐẠI: Đương đại (từ 2000 đến nay), quần áo hiện đại, thành phố/văn phòng/căn hộ
   - HIỆN ĐẠI THẬP NIÊN: Thập niên cụ thể (60s/70s/80s/90s/2000s), trang phục retro/vintage
2. Nhân vật chính và ngoại hình CHỦ XỨNG VỚI BỐI CẢNH

YÊU CẦU CHIA SCENE:
Sau hook story, chia thành 6-8 SCENES để ghép hình ảnh.
Mỗi scene gồm:
- TEXT: 1-2 câu ngắn (trích từ hook story, giữ nguyên chữ)
- EMOTION: 1 từ tiếng Anh mô tả cảm xúc chính (shock/sadness/anger/joy/fear/hope/betrayal/love)
- ACTION: Tư thế nhân vật trong ảnh (tiếng Anh, 5-10 từ)
  QUAN TRỌNG — Tránh pose lỗi anatomy (3 tay, thiếu tay):
  ✅ AN TOÀN: "standing by window back to camera", "seated side profile looking down",
              "close-up face portrait", "figure walking away", "kneeling on floor",
              "lying in bed eyes closed", "standing arms at sides"
  ❌ TRÁNH  : "reaching out hand", "pointing finger", "grabbing arm",
              "hands clasped together", "holding object in both hands"
- SETTING: Bối cảnh không gian (tiếng Anh, 3-5 từ)

FORMAT TRẢ VỀ (giữ ĐÚNG format này, không thêm gì khác):
===CHARACTER===
NAME: [Tên nhân vật chính]
ERA: [co-trang | hien-dai | thap-nien]
DECADE: [Chỉ điền khi ERA=thap-nien: 60s | 70s | 80s | 90s | 2000s]
APPEARANCE: [Mô tả bằng tiếng Anh, PHẢI PHÙ HỢP với ERA:
  - co-trang   → "young woman mid-20s, long black hair in traditional updo with gold hairpin, dark crimson hanfu with gold embroidery, delicate features"
  - hien-dai   → "young woman late-20s, straight black hair, white office blouse and dark trousers, minimal makeup, warm eyes"
  - thap-nien  → "young woman mid-20s, permed hair [80s style], retro floral blouse and high-waist pants, simple silver earrings"]

===HOOK_STORY===
[Nội dung hook story tiếng Việt ở đây]

===SCENES===
SCENE 1
TEXT: [1-2 câu]
EMOTION: [emotion]
ACTION: [action in English]
SETTING: [setting in English]

SCENE 2
TEXT: [1-2 câu]
EMOTION: [emotion]
ACTION: [action in English]
SETTING: [setting in English]

[... tiếp tục đến scene 6-8]

---
THÔNG TIN TRUYỆN:
Tên: {title}
Tác giả: {author}
Thể loại: {genres}

NỘI DUNG TRUYỆN (tóm tắt các chương chính):
{content_sample}
"""


# ─────────────────────────────────────────────────────────────────
# Lấy mẫu nội dung từ các chương quan trọng
# ─────────────────────────────────────────────────────────────────

def _sample_chapters(chapters, max_chars=6000):
    """
    Chọn chương đầu, giữa, cuối để AI hiểu arc của truyện.
    Giới hạn tổng ký tự để không vượt context window.
    """
    if not chapters:
        return ""

    n = len(chapters)
    # Chọn chương đại diện: đầu, 1/3, 2/3, cuối
    indices = sorted({0, n // 3, 2 * n // 3, n - 1})
    selected = [chapters[i] for i in indices if i < n]

    parts = []
    per_chapter = max_chars // max(len(selected), 1)

    for ch in selected:
        content = _normalize_punctuation(ch.get('content', '').strip())
        if not content:
            continue
        # Cắt bớt nếu quá dài
        snippet = content[:per_chapter]
        # Cắt ở cuối câu để không bị cụt giữa chừng
        last_dot = max(snippet.rfind('.'), snippet.rfind('!'), snippet.rfind('?'))
        if last_dot > per_chapter * 0.7:
            snippet = snippet[:last_dot + 1]
        parts.append(f"[Chương {ch.get('number', '?')}]\n{snippet}")

    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────
# Parse output từ LLM
# ─────────────────────────────────────────────────────────────────

def _parse_output(raw: str) -> dict:
    """Parse FORMAT từ LLM output."""

    hook_story = ""
    scenes = []
    character = {"name": "", "era": "co-trang", "decade": "", "appearance": ""}

    # Tách CHARACTER block
    char_match = re.search(r'===CHARACTER===\s*(.*?)\s*===HOOK_STORY===', raw, re.DOTALL)
    if char_match:
        char_block = char_match.group(1)
        name_m   = re.search(r'NAME:\s*(.+)',       char_block, re.IGNORECASE)
        era_m    = re.search(r'ERA:\s*(\S+)',        char_block, re.IGNORECASE)
        decade_m = re.search(r'DECADE:\s*(\S+)',     char_block, re.IGNORECASE)
        app_m    = re.search(r'APPEARANCE:\s*(.+)',  char_block, re.IGNORECASE | re.DOTALL)

        if name_m:   character["name"]       = name_m.group(1).strip()
        if era_m:
            era_raw = era_m.group(1).strip().lower()
            # Normalize các giá trị có thể của LLM
            if "hien" in era_raw and "thap" not in era_raw:
                character["era"] = "hien-dai"
            elif "thap" in era_raw or "retro" in era_raw or "vintage" in era_raw:
                character["era"] = "thap-nien"
            else:
                character["era"] = "co-trang"
        if decade_m: character["decade"]     = decade_m.group(1).strip().lower()
        if app_m:
            # Lấy dòng đầu tiên của APPEARANCE (loại bỏ ví dụ dạng indent)
            app_lines = [ln.strip() for ln in app_m.group(1).strip().splitlines() if ln.strip()]
            character["appearance"] = app_lines[0] if app_lines else ""

    # Tách hook story
    hook_match = re.search(r'===HOOK_STORY===\s*(.*?)\s*===SCENES===', raw, re.DOTALL)
    if hook_match:
        hook_story = hook_match.group(1).strip()

    # Tách scenes
    scenes_block = ""
    scenes_match = re.search(r'===SCENES===\s*(.*)', raw, re.DOTALL)
    if scenes_match:
        scenes_block = scenes_match.group(1).strip()

    # Parse từng scene
    scene_blocks = re.split(r'SCENE\s+\d+', scenes_block, flags=re.IGNORECASE)
    scene_num = 1
    for block in scene_blocks:
        block = block.strip()
        if not block:
            continue

        text_m    = re.search(r'TEXT:\s*(.+?)(?=EMOTION:|ACTION:|SETTING:|$)', block, re.DOTALL | re.IGNORECASE)
        emotion_m = re.search(r'EMOTION:\s*(\w+)', block, re.IGNORECASE)
        action_m  = re.search(r'ACTION:\s*(.+?)(?=SETTING:|SCENE|$)', block, re.DOTALL | re.IGNORECASE)
        setting_m = re.search(r'SETTING:\s*(.+?)(?=SCENE|$)', block, re.DOTALL | re.IGNORECASE)

        text    = text_m.group(1).strip()    if text_m    else ""
        emotion = emotion_m.group(1).strip() if emotion_m else "neutral"
        action  = action_m.group(1).strip()  if action_m  else ""
        setting = setting_m.group(1).strip() if setting_m else ""

        if text:
            scenes.append({
                "scene":   scene_num,
                "text":    text,
                "emotion": emotion.lower(),
                "action":  action,
                "setting": setting,
            })
            scene_num += 1

    # Fallback: nếu parse thất bại, chia hook_story thành scenes tự động
    if not scenes and hook_story:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', hook_story) if len(s.strip()) > 20]
        if not sentences:
            sentences = [hook_story.strip()]
        step = max(1, len(sentences) // 7)
        # Emotion theo vị trí để image generator chọn shot type phù hợp
        _FALLBACK_EMOTIONS = ["shock", "sadness", "dramatic", "fear", "hope", "anger", "sadness"]
        chunks = [" ".join(sentences[i:i+step]) for i in range(0, len(sentences), step)]
        for idx, chunk in enumerate(chunks):
            emotion = _FALLBACK_EMOTIONS[idx % len(_FALLBACK_EMOTIONS)]
            scenes.append({
                "scene":   len(scenes) + 1,
                "text":    chunk,
                "emotion": emotion,
                "action":  "",
                "setting": "",
            })

    return {"hook_story": hook_story, "scenes": scenes, "character": character}


# ─────────────────────────────────────────────────────────────────
# LLM providers (dùng lại config từ crawler)
# ─────────────────────────────────────────────────────────────────

def _call_gemini(prompt_text, api_key, model="gemini-2.5-flash"):
    import requests
    try:
        from config import GEMINI_FALLBACK_MODELS
    except ImportError:
        GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    models = [model] + [m for m in GEMINI_FALLBACK_MODELS if m != model]

    for m in models:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt_text}]}],
                    "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2048},
                },
                timeout=120,
            )
            if resp.status_code == 429:
                logger.warning(f"  Gemini {m}: rate limit, thử model khác...")
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning(f"  Gemini {m} lỗi: {e}")
    return None


def _call_anthropic(prompt_text, api_key, model="claude-haiku-4-5-20251001"):
    import requests
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      model,
            "max_tokens": 2048,
            "messages":   [{"role": "user", "content": prompt_text}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_ollama(prompt_text, _base_url, model):
    import ollama as _ollama
    response = _ollama.generate(
        model=model,
        prompt=prompt_text,
        options={"temperature": 0.85, "num_predict": 2048},
    )
    return response["response"]


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def generate_hook_story(title: str, author: str, genres_str: str, chapters: list) -> dict:
    """
    Chuyển danh sách chương truyện → hook story + scene breakdown.

    Returns:
        {
            "title":      str,
            "hook_story": str,    # 400-600 từ tiếng Việt cho TTS
            "scenes":     list,   # [{scene, text, emotion}, ...]
        }
    """
    from config import (
        REWRITE_PROVIDER,
        GEMINI_API_KEY, GEMINI_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
    )

    content_sample = _sample_chapters(chapters)

    def _call_llm(prompt_text: str) -> str | None:
        if REWRITE_PROVIDER == "gemini" and GEMINI_API_KEY:
            logger.info("  🤖 Hook generator: Gemini")
            return _call_gemini(prompt_text, GEMINI_API_KEY, GEMINI_MODEL)
        if REWRITE_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
            logger.info("  🤖 Hook generator: Anthropic Claude")
            return _call_anthropic(prompt_text, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
        logger.info("  🤖 Hook generator: Ollama")
        return _call_ollama(prompt_text, OLLAMA_BASE_URL, OLLAMA_MODEL)

    prompt_text = HOOK_PROMPT_TEMPLATE.format(
        title=title,
        author=author,
        genres=genres_str or "Ngôn tình / Cổ trang",
        content_sample=content_sample,
    )
    raw = _call_llm(prompt_text)

    if not raw:
        logger.error("  ❌ Hook generator thất bại — không nhận được kết quả từ LLM")
        return {"title": title, "hook_story": "", "scenes": []}

    # Retry 1 lần nếu LLM drift sang tiếng Trung/Nhật/Hàn
    if _has_cjk(raw):
        logger.warning("  ⚠️  Output có ký tự CJK — retry với cảnh báo mạnh hơn")
        retry_prompt = (
            "LẦN TRƯỚC BẠN ĐÃ VIẾT LẪN CHỮ HÁN VÀO OUTPUT — ĐIỀU NÀY HOÀN TOÀN KHÔNG "
            "ĐƯỢC CHẤP NHẬN. Hãy viết lại từ đầu, 100% bằng tiếng Việt có dấu, "
            "không một ký tự Hán/Nhật/Hàn nào, không dấu câu 。，！？.\n\n"
            + prompt_text
        )
        retry_raw = _call_llm(retry_prompt)
        if retry_raw and not _has_cjk(retry_raw):
            raw = retry_raw
        elif retry_raw:
            logger.warning("  ⚠️  Retry vẫn có CJK — strip ký tự Hán khỏi output")
            raw = CJK_CHAR_RE.sub('', retry_raw).translate(CJK_PUNCT_MAP)
        else:
            logger.warning("  ⚠️  Retry fail — strip CJK khỏi output gốc")
            raw = CJK_CHAR_RE.sub('', raw).translate(CJK_PUNCT_MAP)

    parsed = _parse_output(raw)
    parsed["title"] = title

    char = parsed.get("character", {})
    logger.info(f"  ✅ Hook story: {len(parsed['hook_story'])} ký tự, {len(parsed['scenes'])} scenes")
    if char.get("name"):
        era_label = {"co-trang": "CỔ TRANG", "hien-dai": "HIỆN ĐẠI", "thap-nien": "THẬP NIÊN"}.get(char.get("era", ""), char.get("era", ""))
        decade_str = f" ({char['decade'].upper()})" if char.get("decade") else ""
        logger.info(f"  👤 [{era_label}{decade_str}] {char['name']}: {char.get('appearance', '')[:70]}")
    return parsed
