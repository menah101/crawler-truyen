"""
Rewriter — xào nấu nội dung bằng Gemini (miễn phí) hoặc local.
Gemini tự fallback: Flash → Flash-Lite → Pro → local.
"""

import re
import time
import random
import logging

logger = logging.getLogger(__name__)


def strip_foreign_chars(text: str) -> str:
    """
    Xóa ký tự tiếng Trung (CJK) và các từ tiếng Anh thuần (không phải tên riêng)
    sót lại sau khi AI rewrite.

    - CJK block: U+4E00–U+9FFF (Hán tự phổ thông) + mở rộng
    - Từ tiếng Anh: chuỗi toàn a-z/A-Z dài ≥ 3 ký tự, không phải tên (không có chữ hoa đầu)
      → chỉ xóa từ thường (lowercase) để tránh xóa tên nhân vật phiên âm
    """
    # 1. Xóa ký tự CJK đứng rời hoặc thành cụm
    text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f]+', '', text)

    # 2. Xóa từ tiếng Anh lowercase thuần (ví dụ: "the", "of", "and", "chapter", "said")
    #    Giữ lại nếu có chữ hoa đầu (tên riêng) hoặc xen kẽ trong từ tiếng Việt
    text = re.sub(r'\b[a-z]{3,}\b', '', text)

    # 3. Dọn dẹp khoảng trắng thừa sau khi xóa
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'^ +| +$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def split_paragraphs(text):
    """
    Tách đoạn văn bị dính lại không có xuống dòng.
    Ví dụ: ...nổ ra:"Phóng viên?..."Gương mặt... → mỗi câu/đối thoại thành đoạn riêng.
    """
    # Chuẩn hoá: bỏ \r, gộp nhiều dòng trống
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Chèn \n\n trước dấu " mở đầu đối thoại khi đứng sau ký tự kết câu hoặc :
    # Ví dụ: sao?!"Gương  →  sao?!"\nGương   (dòng mới sau "  kết thúc đối thoại)
    # Và:   nổ ra:"Phóng  →  nổ ra:\n"Phóng   (dòng mới trước " mở đầu)

    # 1. Sau dấu đóng đối thoại [.?!] + " + chữ thường/hoa → xuống dòng
    text = re.sub(r'([.?!…]["»])\s*([^\n"«])', r'\1\n\2', text)

    # 2. Trước dấu mở đối thoại: ký tự thường/dấu câu + : + " → xuống dòng trước "
    text = re.sub(r'([:：])\s*([""«])', r'\1\n\2', text)

    # 3. Sau đối thoại kết thúc bằng " (không có dấu câu rõ) + chữ hoa → xuống dòng
    text = re.sub(r'([""»])\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ])', r'\1\n\2', text)

    # 4. Gộp dòng đơn thành đoạn đôi để dễ đọc
    # Nếu dòng trước kết thúc bằng . ! ? " và dòng sau bắt đầu bằng chữ → \n\n
    text = re.sub(r'([.?!…"»])\n([^\n])', r'\1\n\n\2', text)

    # Dọn dẹp cuối cùng
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


REWRITE_PROMPT = """Bạn là một nhà văn sáng tạo chuyên viết lại truyện cổ trang/ngôn tình với mức độ độc đáo cao.

MỤC TIÊU: Tạo ra bản văn ĐỘC LẬP đến mức vượt qua 80–90% unique khi kiểm tra bằng Copyscape hoặc các tool phát hiện đạo văn. Không phải "diễn đạt lại" mà là "kể lại theo cách của mình".

PHƯƠNG PHÁP — áp dụng TẤT CẢ những kỹ thuật sau:

① THAY ĐỔI NGÔI KỂ VÀ GÓC NHÌN
   - Nếu gốc kể ngôi thứ ba → chuyển sang ngôi thứ nhất (nhân vật "tôi"), hoặc ngược lại
   - Hoặc: giữ ngôi kể nhưng dịch chuyển điểm nhìn sang nhân vật phụ trong cùng cảnh

② ĐẢO TRÌNH TỰ SỰ KIỆN
   - Bắt đầu từ giữa hoặc cuối cảnh, sau đó kể lùi về điểm khởi đầu (in medias res)
   - Hoặc: xen kẽ hành động và hồi tưởng để phá vỡ chuỗi thời gian tuyến tính

③ THÊM TÂM LÝ NỘI TÂM DO CHÍNH BẠN VIẾT
   - Sau mỗi hành động hoặc lời thoại quan trọng, thêm 2–4 câu phân tích cảm xúc/suy nghĩ sâu của nhân vật
   - Không sao chép — tự suy luận từ ngữ cảnh rồi diễn đạt bằng ngôn ngữ của bạn

④ THAY THẾ CHI TIẾT PHỤ VÀ BỐI CẢNH
   - Đổi tên đồ vật, màu sắc, mùi hương, âm thanh, thời tiết sang chi tiết tương đương nhưng khác
   - Thêm một chi tiết giác quan mới (xúc giác, khứu giác, thính giác) mà bản gốc không có

⑤ TÁI CẤU TRÚC ĐỐI THOẠI
   - Giữ nguyên nội dung và ý nghĩa của lời thoại, nhưng đổi cách dẫn thoại và hành động kèm theo
   - Biến câu thoại trực tiếp thành tường thuật gián tiếp (hoặc ngược lại) ở một số chỗ

⑥ MỞ RỘNG ĐỘ DÀI HỢP LÝ
   - Viết dài hơn bản gốc từ 20–40% bằng cách phát triển tâm lý và chi tiết — không nhồi thông tin thừa

RÀNG BUỘC CỨNG:
- Giữ nguyên: tên nhân vật, cốt truyện chính, kết quả của mỗi cảnh, thứ tự nhân quả
- NGÔN NGỮ: 100% tiếng Việt — dịch ngay bất kỳ chữ Hán nào còn sót trong bản gốc
- ĐỊNH DẠNG: mỗi đoạn văn và câu thoại phải cách nhau bằng MỘT DÒNG TRỐNG (\\n\\n)
- KHÔNG thêm tiêu đề, số chương, ghi chú, hay bất kỳ lời giải thích nào

CHỈ trả về nội dung đã viết lại, KHÔNG giải thích."""

# Prompt rút gọn dành riêng cho Ollama local model (7B–13B).
# Model nhỏ follow instruction tốt hơn khi prompt ngắn, directive, 1 nhiệm vụ rõ ràng mỗi lần.
REWRITE_PROMPT_OLLAMA = """Bạn là nhà văn chuyên viết truyện tiếng Việt.

Nhiệm vụ: Viết lại đoạn văn dưới đây bằng tiếng Việt.

Quy tắc:
1. Đổi ngôi kể: nếu gốc dùng "cô ấy/anh ấy/nàng/hắn" → chuyển sang "tôi", hoặc ngược lại
2. Sau mỗi hành động quan trọng, thêm 1–2 câu tâm lý của nhân vật
3. Giữ nguyên tên nhân vật, cốt truyện, kết quả cảnh
4. Viết dài hơn 20–30% so với bản gốc
5. TUYỆT ĐỐI không dùng chữ Hán/Trung Quốc — nếu gặp chữ Hán thì dịch sang tiếng Việt ngay
6. TUYỆT ĐỐI không dùng tiếng Anh — nếu gặp từ Anh thì dịch hoặc bỏ
7. Mỗi đoạn văn cách nhau một dòng trống
8. CHỈ trả về nội dung đã viết lại, không giải thích, không tiêu đề"""

try:
    from config import GROQ_FALLBACK_MODELS as _GROQ_FALLBACK_MODELS
except ImportError:
    _GROQ_FALLBACK_MODELS = []

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]


def _call_gemini(text, api_key, model):
    import requests
    return requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": f"{REWRITE_PROMPT}\n\n---\n\n{text}"}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 4096},
        },
        timeout=120,
    )


def rewrite_gemini(text, api_key, model):
    """Gemini rewrite — tự fallback qua 3 model khi 429."""
    models = [model] + [m for m in GEMINI_MODELS if m != model]

    for m in models:
        try:
            resp = _call_gemini(text, api_key, m)
        except Exception as e:
            logger.error(f"    ❌ Gemini {m} error: {e}")
            continue

        if resp.status_code == 429:
            logger.warning(f"    ⚠️ {m}: hết quota (429), thử model khác...")
            time.sleep(2)
            continue

        if resp.status_code != 200:
            logger.error(f"    ❌ Gemini {m}: {resp.status_code}")
            return None

        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            result = parts[0]["text"].strip()
            if result:
                if m != model:
                    logger.info(f"    🔄 Dùng {m} thay {model}")
                return result
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    logger.warning(f"    ⚠️ Tất cả Gemini model hết quota")
    return None


# ============================================================
# ANTHROPIC (CLAUDE)
# ============================================================

def rewrite_anthropic(text, api_key, model):
    """Viết lại bằng Claude API."""
    import requests
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": f"{REWRITE_PROMPT}\n\n---\n\n{text}"}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        logger.error(f"    ❌ Anthropic error {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        return resp.json()["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, ValueError):
        return None


# ============================================================
# DEEPSEEK
# ============================================================

def rewrite_deepseek(text, api_key, model):
    """Viết lại bằng DeepSeek API (OpenAI-compatible)."""
    import requests
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "temperature": 0.8,
            "messages": [{"role": "user", "content": f"{REWRITE_PROMPT}\n\n---\n\n{text}"}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        logger.error(f"    ❌ DeepSeek error {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ============================================================
# OLLAMA (local)
# ============================================================

def rewrite_ollama(text, base_url, model):
    """Viết lại bằng Ollama chạy local (OpenAI-compatible endpoint)."""
    import requests
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.8,
                "messages": [{"role": "user", "content": f"{REWRITE_PROMPT_OLLAMA}\n\n---\n\n{text}"}],
            },
            timeout=300,  # local model có thể chậm hơn
        )
    except requests.exceptions.ConnectionError:
        logger.error(f"    ❌ Ollama: không kết nối được tới {base_url} — đảm bảo Ollama đang chạy")
        return None
    except Exception as e:
        logger.error(f"    ❌ Ollama error: {e}")
        return None

    if resp.status_code != 200:
        logger.error(f"    ❌ Ollama {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ============================================================
# HUGGINGFACE INFERENCE API
# ============================================================

def rewrite_huggingface(text, api_token, model):
    """Viết lại bằng HuggingFace Serverless Inference API — tự fallback qua các model."""
    import requests
    try:
        from config import HF_REWRITE_FALLBACK_MODELS
    except ImportError:
        HF_REWRITE_FALLBACK_MODELS = []

    models = [model] + [m for m in HF_REWRITE_FALLBACK_MODELS if m != model]

    for m in models:
        url = f"https://router.huggingface.co/together/v1/chat/completions"
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": m,
                    "max_tokens": 4096,
                    "temperature": 0.8,
                    "messages": [{"role": "user", "content": f"{REWRITE_PROMPT}\n\n---\n\n{text}"}],
                },
                timeout=180,  # cold start có thể chậm
            )
        except Exception as e:
            logger.error(f"    ❌ HuggingFace {m} error: {e}")
            continue

        if resp.status_code == 503:
            logger.warning(f"    ⚠️ HF {m}: model đang tải (503), thử model khác...")
            time.sleep(3)
            continue

        if resp.status_code == 429:
            logger.warning(f"    ⚠️ HF {m}: rate limit (429), thử model khác...")
            time.sleep(5)
            continue

        if resp.status_code != 200:
            logger.error(f"    ❌ HF {m}: {resp.status_code} — {resp.text[:200]}")
            continue

        try:
            result = resp.json()["choices"][0]["message"]["content"].strip()
            if result:
                if m != model:
                    logger.info(f"    🔄 HF fallback: dùng {m}")
                return result
        except (KeyError, IndexError, TypeError, ValueError):
            continue

    logger.warning("    ⚠️ Tất cả HuggingFace model thất bại")
    return None


# ============================================================
# GROQ
# ============================================================

def rewrite_groq(text, api_key, model):
    """Viết lại bằng Groq API — tự fallback khi bị rate limit (429)."""
    import requests

    models = [model] + [m for m in _GROQ_FALLBACK_MODELS if m != model]

    for m in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": m,
                    "max_tokens": 4096,
                    "temperature": 0.8,
                    "messages": [{"role": "user", "content": f"{REWRITE_PROMPT}\n\n---\n\n{text}"}],
                },
                timeout=120,
            )
        except Exception as e:
            logger.error(f"    ❌ Groq {m} error: {e}")
            continue

        if resp.status_code == 429:
            logger.warning(f"    ⚠️ Groq {m}: rate limit (429), thử model khác...")
            time.sleep(3)
            continue

        if resp.status_code != 200:
            logger.error(f"    ❌ Groq {m}: {resp.status_code} — {resp.text[:200]}")
            return None

        try:
            result = resp.json()["choices"][0]["message"]["content"].strip()
            if result:
                if m != model:
                    logger.info(f"    🔄 Groq fallback: dùng {m}")
                return result
        except Exception:
            return None

    logger.warning("    ⚠️ Tất cả Groq model bị rate limit — dùng local")
    return None


# === Local rewrite (từ đồng nghĩa) ===

SYNONYMS = {
    'xinh đẹp': ['tuyệt sắc', 'diễm lệ', 'kiều diễm', 'mỹ lệ'],
    'nói': ['thốt', 'cất lời', 'lên tiếng', 'đáp'],
    'nhìn': ['ngắm', 'dõi theo', 'đưa mắt', 'liếc'],
    'đi': ['bước', 'rảo bước', 'tiến bước', 'cất bước'],
    'rất': ['vô cùng', 'hết sức', 'cực kỳ', 'vạn phần'],
    'buồn': ['u sầu', 'sầu muộn', 'ưu thương', 'bi thương'],
    'vui': ['hoan hỷ', 'phấn khởi', 'hân hoan'],
    'giận': ['phẫn nộ', 'tức giận', 'nổi giận'],
    'sợ': ['kinh hãi', 'hoảng sợ', 'lo lắng'],
    'yêu': ['thương', 'si mê', 'quyến luyến'],
    'chàng': ['hắn', 'công tử', 'lang quân'],
    'nàng': ['nàng ấy', 'cô nương', 'nương tử'],
    'nhanh chóng': ['lập tức', 'tức khắc', 'thoáng chốc'],
    'nhưng': ['song', 'tuy nhiên', 'thế nhưng'],
    'liền': ['bèn', 'lập tức', 'vội'],
    'lạnh lùng': ['băng lãnh', 'lạnh nhạt', 'hờ hững'],
    'dịu dàng': ['ôn nhu', 'nhẹ nhàng', 'hiền hòa'],
    'bất ngờ': ['đột nhiên', 'chợt', 'thình lình', 'bỗng nhiên'],
    'cuối cùng': ['rốt cuộc', 'sau cùng', 'kết cục'],
}


def rewrite_local(text):
    result = text
    for word, syns in SYNONYMS.items():
        if word in result:
            # Use word boundaries to avoid replacing inside longer words
            pattern = r'(?<!\w)' + re.escape(word) + r'(?!\w)'
            def _replacer(_):
                return random.choice(syns) if random.random() < 0.5 else word
            result = re.sub(pattern, _replacer, result)
    return result


# ============================================================
# PREFLIGHT CHECK
# ============================================================

def check_rewriter():
    """
    Kiểm tra nhanh rewriter trước khi crawl.
    Gửi 1 câu ngắn (~10 token) để xác nhận API hoạt động.
    Trả về (ok: bool, message: str).
    """
    from config import (
        REWRITE_ENABLED, REWRITE_PROVIDER,
        GEMINI_API_KEY, GEMINI_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
        DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
        GROQ_API_KEY, GROQ_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
    )
    import requests

    if not REWRITE_ENABLED:
        return True, "Rewriter tắt (REWRITE_ENABLED=False) — bỏ qua kiểm tra"

    provider = REWRITE_PROVIDER.lower()
    ping = "Trả lời 'ok'."   # ~5 token, đủ để test kết nối

    if provider == "local":
        return True, "Rewriter local — không cần API"

    # ── Gemini ──
    if provider == "gemini":
        if not GEMINI_API_KEY:
            return False, "GEMINI_API_KEY chưa set"
        try:
            resp = _call_gemini(ping, GEMINI_API_KEY, GEMINI_MODEL)
            if resp.status_code == 200:
                return True, f"Gemini OK ({GEMINI_MODEL})"
            if resp.status_code == 429:
                return False, f"Gemini: hết quota (429) — {GEMINI_MODEL}"
            return False, f"Gemini: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Gemini: lỗi kết nối — {e}"

    # ── Anthropic ──
    if provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            return False, "ANTHROPIC_API_KEY chưa set"
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": ANTHROPIC_MODEL, "max_tokens": 10,
                      "messages": [{"role": "user", "content": ping}]},
                timeout=15,
            )
            if resp.status_code == 200:
                return True, f"Anthropic OK ({ANTHROPIC_MODEL})"
            if resp.status_code == 401:
                return False, "Anthropic: API key không hợp lệ (401)"
            if resp.status_code == 529:
                return False, "Anthropic: quá tải (529)"
            return False, f"Anthropic: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Anthropic: lỗi kết nối — {e}"

    # ── DeepSeek ──
    if provider == "deepseek":
        if not DEEPSEEK_API_KEY:
            return False, "DEEPSEEK_API_KEY chưa set"
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL, "max_tokens": 10,
                      "messages": [{"role": "user", "content": ping}]},
                timeout=15,
            )
            if resp.status_code == 200:
                return True, f"DeepSeek OK ({DEEPSEEK_MODEL})"
            if resp.status_code == 401:
                return False, "DeepSeek: API key không hợp lệ (401)"
            return False, f"DeepSeek: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"DeepSeek: lỗi kết nối — {e}"

    # ── Groq ──
    if provider == "groq":
        if not GROQ_API_KEY:
            return False, "GROQ_API_KEY chưa set"
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "max_tokens": 10,
                      "messages": [{"role": "user", "content": ping}]},
                timeout=15,
            )
            if resp.status_code == 200:
                return True, f"Groq OK ({GROQ_MODEL})"
            if resp.status_code == 401:
                return False, "Groq: API key không hợp lệ (401)"
            if resp.status_code == 429:
                return False, f"Groq: rate limit (429) — {GROQ_MODEL}"
            return False, f"Groq: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Groq: lỗi kết nối — {e}"

    # ── Ollama ──
    if provider == "ollama":
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False, f"Ollama: server phản hồi HTTP {resp.status_code}"
            models = [m["name"] for m in resp.json().get("models", [])]
            # Tên model có thể có tag, ví dụ "qwen2.5:7b"
            base = OLLAMA_MODEL.split(":")[0]
            if not any(base in m for m in models):
                return False, f"Ollama: model '{OLLAMA_MODEL}' chưa pull — có: {models or '(trống)'}"
            return True, f"Ollama OK ({OLLAMA_MODEL} @ {OLLAMA_BASE_URL})"
        except requests.exceptions.ConnectionError:
            return False, f"Ollama: không kết nối được tới {OLLAMA_BASE_URL} — đảm bảo Ollama đang chạy"
        except Exception as e:
            return False, f"Ollama: lỗi — {e}"

    # ── HuggingFace ──
    if provider == "huggingface":
        from config import HF_API_TOKEN, HF_REWRITE_MODEL
        token = HF_API_TOKEN
        if not token:
            return False, "HF_API_TOKEN chưa set"
        try:
            resp = requests.post(
                "https://router.huggingface.co/together/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"model": HF_REWRITE_MODEL, "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Trả lời 'ok'."}]},
                timeout=30,
            )
            if resp.status_code == 200:
                return True, f"HuggingFace OK ({HF_REWRITE_MODEL})"
            if resp.status_code == 401:
                return False, "HuggingFace: API token không hợp lệ (401)"
            if resp.status_code == 503:
                return True, f"HuggingFace: model đang tải (503) — sẽ OK sau vài giây ({HF_REWRITE_MODEL})"
            return False, f"HuggingFace: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"HuggingFace: lỗi kết nối — {e}"

    return False, f"Provider không rõ: '{REWRITE_PROVIDER}'"


# === Description sanitizer ===

# Các cụm từ/pattern nhạy cảm thường xuất hiện trong mô tả truyện nguồn.
# Regex match case-insensitive, xóa câu chứa pattern hoặc thay bằng cụm trung tính.
_SENSITIVE_PATTERNS = [
    # Vòng đo / số đo cơ thể
    r'vòng\s*[123]\b',
    r'\b\d{2,3}\s*[-–]\s*\d{2,3}\s*[-–]\s*\d{2,3}\b',   # VD: 90-60-90
    # Cơ thể phụ nữ dùng ngôn từ gợi cảm/gợi dục
    r'bộ ngực\s*(nảy nở|căng tròn|đầy đặn|to|khủng|gợi cảm)',
    r'(ngực|vòng 1)\s*(căng|nảy|đầy|trắng|hồng|mềm|tròn)',
    r'đùi\s*(trắng|thon|mềm|nõn|nuột)',
    r'mông\s*(tròn|đầy|căng|nảy)',
    r'eo\s*(thon|nhỏ|con kiến)\s*(gợi cảm|quyến rũ)',
    r'cơ thể\s*(gợi cảm|bốc lửa|khêu gợi|nóng bỏng|hoàn hảo)',
    r'thân hình\s*(gợi cảm|bốc lửa|khêu gợi|nóng bỏng|hoàn hảo)',
    r'nội\s*y\b',
    r'khỏa\s*thân|nude|18\s*\+|người lớn',
    # Hành động/cảnh nhạy cảm
    r'lên\s*giường|lên\s*bed|ân\s*ái|quan\s*hệ\s*(tình\s*dục|thể\s*xác)',
    r'(cởi|lột)\s*(quần|áo|đồ)',
    r'hôn\s*(lên|vào)\s*(ngực|đùi|cổ|bụng)',
    r'(sờ|vuốt|chạm)\s*(ngực|người|thân thể)',
    r'dục\s*vọng|ham\s*muốn\s*xác\s*thịt|thèm\s*khát\s*(thân\s*thể|cơ\s*thể)',
    r'tình\s*dục|sex\b|erotic',
]

_SENSITIVE_RE = re.compile(
    '|'.join(f'(?:{p})' for p in _SENSITIVE_PATTERNS),
    re.IGNORECASE,
)

# Pattern tách câu: kết thúc bằng . ? ! … hoặc \n
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.?!…])\s+|\n+')


def sanitize_description(text: str) -> str:
    """
    Xóa các câu chứa nội dung nhạy cảm (cơ thể gợi dục, 18+) khỏi mô tả truyện.
    Giữ nguyên các câu còn lại, join lại thành đoạn văn liền mạch.
    """
    if not text:
        return text

    sentences = _SENTENCE_SPLIT_RE.split(text)
    clean = []
    removed = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if _SENSITIVE_RE.search(s):
            removed += 1
            logger.debug(f"  🚫 Xóa câu nhạy cảm: {s[:80]}...")
        else:
            clean.append(s)

    if removed:
        logger.info(f"  🧹 sanitize_description: xóa {removed} câu nhạy cảm")

    return ' '.join(clean)


# === Novel meta rewrite ===

REWRITE_META_PROMPT = """Bạn là biên tập viên truyện chuyên nghiệp. Hãy viết lại tiêu đề và mô tả truyện dưới đây.

Yêu cầu:
- Giữ nguyên tên nhân vật, bối cảnh, thể loại
- Diễn đạt lại bằng ngôn từ khác, hấp dẫn hơn
- Giữ nguyên ngôn ngữ (tiếng Việt)
- Mô tả giữ nguyên độ dài (±20%)
- KHÔNG thêm nội dung mới ngoài thông tin đã có
- NỘI DUNG NHẠY CẢM: Nếu mô tả có chi tiết cơ thể gợi dục, cảnh nóng, hay ngôn từ 18+, hãy xóa hoặc viết lại theo hướng lãng mạn nhẹ nhàng phù hợp mọi lứa tuổi — giữ cốt truyện nhưng bỏ yếu tố khiêu dâm

Trả về đúng định dạng JSON sau (không giải thích, không markdown):
{"title": "...", "description": "..."}"""


def rewrite_novel_meta(title: str, description: str) -> tuple[str, str]:
    """
    Viết lại title và description của truyện bằng AI.
    Trả về (new_title, new_description). Nếu thất bại, giữ nguyên bản gốc.
    """
    import json as _json
    from config import (
        REWRITE_ENABLED, REWRITE_PROVIDER,
        GEMINI_API_KEY, GEMINI_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
        DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
        GROQ_API_KEY, GROQ_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
        HF_API_TOKEN, HF_REWRITE_MODEL,
    )

    if not REWRITE_ENABLED:
        return title, description

    provider = REWRITE_PROVIDER.lower()
    payload = f'Tiêu đề: {title}\n\nMô tả:\n{description}'
    prompt = f"{REWRITE_META_PROMPT}\n\n---\n\n{payload}"

    logger.info(f"  ✍️ Rewrite meta ({provider})...")

    raw = None
    try:
        if provider == "anthropic" and ANTHROPIC_API_KEY:
            raw = rewrite_anthropic(prompt, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
        elif provider == "gemini" and GEMINI_API_KEY:
            raw = rewrite_gemini(prompt, GEMINI_API_KEY, GEMINI_MODEL)
        elif provider == "deepseek" and DEEPSEEK_API_KEY:
            raw = rewrite_deepseek(prompt, DEEPSEEK_API_KEY, DEEPSEEK_MODEL)
        elif provider == "groq" and GROQ_API_KEY:
            raw = rewrite_groq(prompt, GROQ_API_KEY, GROQ_MODEL)
        elif provider == "huggingface" and HF_API_TOKEN:
            raw = rewrite_huggingface(prompt, HF_API_TOKEN, HF_REWRITE_MODEL)
        elif provider == "ollama":
            raw = rewrite_ollama(prompt, OLLAMA_BASE_URL, OLLAMA_MODEL)
    except Exception as e:
        logger.warning(f"  ⚠️ Rewrite meta error: {e}")
        return title, description

    if not raw:
        logger.warning("  ⚠️ Rewrite meta: không có kết quả — giữ nguyên bản gốc")
        return title, description

    # Parse JSON từ response (AI đôi khi bọc trong ```json ```)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean).strip()
        data = _json.loads(clean)
        new_title = data.get("title", "").strip() or title
        new_desc  = data.get("description", "").strip() or description
        logger.info(f"  ✅ Meta rewritten: '{new_title[:40]}...'")
        return new_title, new_desc
    except Exception as e:
        logger.warning(f"  ⚠️ Rewrite meta: lỗi parse JSON ({e}) — giữ nguyên bản gốc")
        return title, description


# === Main ===

def rewrite_chapter(content, novel_title=""):  # noqa: ARG001
    from config import (
        REWRITE_ENABLED, REWRITE_PROVIDER,
        GEMINI_API_KEY, GEMINI_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
        DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
        GROQ_API_KEY, GROQ_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
        HF_API_TOKEN, HF_REWRITE_MODEL,
        REWRITE_CHUNK_SIZE, REWRITE_DELAY,
    )
    from config import REWRITE_CHUNK_SIZE_OLLAMA

    if not REWRITE_ENABLED or not content or len(content) < 100:
        return split_paragraphs(content)

    provider = REWRITE_PROVIDER.lower()
    logger.info(f"    ✍️ Rewrite ({provider})...")

    if provider == "local":
        return split_paragraphs(rewrite_local(content))

    if provider == "gemini" and not GEMINI_API_KEY:
        logger.warning("    ⚠️ GEMINI_API_KEY chưa set — dùng local")
        return rewrite_local(content)

    if provider == "anthropic" and not ANTHROPIC_API_KEY:
        logger.warning("    ⚠️ ANTHROPIC_API_KEY chưa set — dùng local")
        return rewrite_local(content)

    if provider == "deepseek" and not DEEPSEEK_API_KEY:
        logger.warning("    ⚠️ DEEPSEEK_API_KEY chưa set — dùng local")
        return rewrite_local(content)

    if provider == "groq" and not GROQ_API_KEY:
        logger.warning("    ⚠️ GROQ_API_KEY chưa set — dùng local")
        return rewrite_local(content)

    if provider == "huggingface" and not HF_API_TOKEN:
        logger.warning("    ⚠️ HF_API_TOKEN chưa set — dùng local")
        return rewrite_local(content)

    if provider == "ollama":
        logger.info(f"    🦙 Ollama: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")

    # Tiền xử lý: tách đoạn văn bị dính
    content = split_paragraphs(content)

    # Ollama dùng chunk nhỏ hơn để model 7B follow instruction tốt hơn
    chunk_size = REWRITE_CHUNK_SIZE_OLLAMA if provider == "ollama" else REWRITE_CHUNK_SIZE

    # Chia chunk
    paragraphs = content.split('\n\n')
    chunks, current, current_len = [], [], 0
    for p in paragraphs:
        if current_len + len(p) > chunk_size and current:
            chunks.append('\n\n'.join(current))
            current, current_len = [p], len(p)
        else:
            current.append(p)
            current_len += len(p)
    if current:
        chunks.append('\n\n'.join(current))

    rewritten = []
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            logger.info(f"    ✍️ Đoạn {i+1}/{len(chunks)}...")

        result = None
        try:
            if provider == "anthropic":
                result = rewrite_anthropic(chunk, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
            elif provider == "gemini":
                result = rewrite_gemini(chunk, GEMINI_API_KEY, GEMINI_MODEL)
            elif provider == "deepseek":
                result = rewrite_deepseek(chunk, DEEPSEEK_API_KEY, DEEPSEEK_MODEL)
            elif provider == "groq":
                result = rewrite_groq(chunk, GROQ_API_KEY, GROQ_MODEL)
            elif provider == "huggingface":
                result = rewrite_huggingface(chunk, HF_API_TOKEN, HF_REWRITE_MODEL)
            elif provider == "ollama":
                result = rewrite_ollama(chunk, OLLAMA_BASE_URL, OLLAMA_MODEL)
        except Exception as e:
            logger.error(f"    ❌ Rewrite error: {e}")

        if result and len(result) > len(chunk) * 0.3:
            rewritten.append(split_paragraphs(strip_foreign_chars(result)))
        else:
            rewritten.append(split_paragraphs(rewrite_local(chunk)))

        if i < len(chunks) - 1:
            time.sleep(REWRITE_DELAY)

    final = '\n\n'.join(rewritten)
    logger.info(f"    ✅ Rewrite: {len(content)} → {len(final)} ký tự")
    return final
