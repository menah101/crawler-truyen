"""
Dịch văn bản Anh → Việt sử dụng cùng provider với rewriter.
Ưu tiên: Gemini → Anthropic → DeepSeek → Groq → Ollama → local (từ điển đơn giản).
"""

import time
import logging

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

TRANSLATE_PROMPT = """Bạn là dịch giả tiểu thuyết chuyên nghiệp Anh → Việt.
Hãy dịch đoạn văn dưới đây sang tiếng Việt theo các quy tắc:
1. Dịch tự nhiên, trôi chảy, giữ phong cách văn học gốc
2. Giữ nguyên tên riêng (tên người, địa danh) theo phiên âm phổ biến tiếng Việt hoặc giữ nguyên
3. ĐỊNH DẠNG: mỗi đoạn văn và mỗi câu thoại cách nhau bằng MỘT DÒNG TRỐNG (\\n\\n)
4. Không thêm giải thích, chú thích, tiêu đề
5. Không thêm số chương hoặc bất kỳ ký hiệu nào ngoài nội dung
CHỈ trả về bản dịch tiếng Việt, KHÔNG giải thích thêm."""

TRANSLATE_NOVEL_INFO_PROMPT = """Dịch thông tin tiểu thuyết sau sang tiếng Việt:
- Tiêu đề: {title}
- Tác giả: {author}
- Mô tả: {description}

Trả về JSON format:
{{
  "title": "tiêu đề tiếng Việt",
  "author": "tên tác giả giữ nguyên hoặc phiên âm",
  "description": "mô tả tiếng Việt"
}}
CHỈ trả về JSON, không giải thích."""


# ── Gemini ────────────────────────────────────────────────────────────────────

GEMINI_TRANSLATE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def _translate_gemini(text, api_key, model):
    import requests
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {"contents": [{"parts": [{"text": f"{TRANSLATE_PROMPT}\n\n---\n\n{text}"}]}]}
    r = requests.post(url, json=body, timeout=120)
    if r.status_code != 200:
        return None
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _translate_anthropic(text, api_key, model):
    import requests
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": f"{TRANSLATE_PROMPT}\n\n---\n\n{text}"}],
        },
        timeout=120,
    )
    if r.status_code != 200:
        return None
    try:
        return r.json()["content"][0]["text"].strip()
    except Exception:
        return None


# ── DeepSeek ──────────────────────────────────────────────────────────────────

def _translate_deepseek(text, api_key, model):
    import requests
    r = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 4096,
            "temperature": 0.6,
            "messages": [{"role": "user", "content": f"{TRANSLATE_PROMPT}\n\n---\n\n{text}"}],
        },
        timeout=120,
    )
    if r.status_code != 200:
        return None
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ── Groq ──────────────────────────────────────────────────────────────────────

def _translate_groq(text, api_key, fallback_models):
    import requests
    for model in fallback_models:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.6,
                "messages": [{"role": "user", "content": f"{TRANSLATE_PROMPT}\n\n---\n\n{text}"}],
            },
            timeout=120,
        )
        if r.status_code == 429:
            logger.warning(f"    ⚠️ Groq rate limit [{model}], thử model tiếp...")
            time.sleep(10)
            continue
        if r.status_code == 200:
            try:
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                return None
    return None


# ── Ollama ────────────────────────────────────────────────────────────────────

def _translate_ollama(text, base_url, model):
    import requests
    r = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": f"{TRANSLATE_PROMPT}\n\n---\n\n{text}",
            "stream": False,
            "options": {"temperature": 0.6},
        },
        timeout=300,
    )
    if r.status_code != 200:
        return None
    try:
        return r.json().get("response", "").strip()
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def translate_chapter(text: str, novel_title: str = "") -> str:
    """
    Dịch nội dung chương từ tiếng Anh sang tiếng Việt.
    Tự động chọn provider dựa theo TRANSLATE_PROVIDER trong config.
    """
    if not text or not text.strip():
        return text

    try:
        from config import (
            REWRITE_PROVIDER,
            GEMINI_API_KEY,
            ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
            DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
            GROQ_API_KEY, GROQ_FALLBACK_MODELS,
            OLLAMA_BASE_URL, OLLAMA_MODEL,
            REWRITE_CHUNK_SIZE, REWRITE_DELAY,
        )
    except ImportError:
        logger.warning("Không load được config — bỏ qua dịch")
        return text

    provider = REWRITE_PROVIDER
    chunks = _split_chunks(text, REWRITE_CHUNK_SIZE)
    parts = []

    for i, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            logger.info(f"    🌐 Dịch chunk {i}/{len(chunks)} ({len(chunk)} ký tự)…")

        result = None
        if provider == "gemini" and GEMINI_API_KEY:
            for model in GEMINI_TRANSLATE_MODELS:
                result = _translate_gemini(chunk, GEMINI_API_KEY, model)
                if result:
                    break
        elif provider == "anthropic" and ANTHROPIC_API_KEY:
            result = _translate_anthropic(chunk, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
        elif provider == "deepseek" and DEEPSEEK_API_KEY:
            result = _translate_deepseek(chunk, DEEPSEEK_API_KEY, DEEPSEEK_MODEL)
        elif provider == "groq" and GROQ_API_KEY:
            result = _translate_groq(chunk, GROQ_API_KEY, GROQ_FALLBACK_MODELS)
        elif provider == "ollama":
            result = _translate_ollama(chunk, OLLAMA_BASE_URL, OLLAMA_MODEL)

        if result:
            parts.append(result)
        else:
            logger.warning(f"    ⚠️ Dịch thất bại chunk {i} — giữ bản gốc tiếng Anh")
            parts.append(chunk)

        if i < len(chunks):
            time.sleep(REWRITE_DELAY)

    return "\n\n".join(parts)


def translate_novel_info(title: str, author: str, description: str) -> dict:
    """
    Dịch metadata truyện (tiêu đề, tác giả, mô tả) sang tiếng Việt.
    Trả về dict với keys: title, author, description.
    """
    import json

    fallback = {"title": title, "author": author, "description": description}

    if not description and not title:
        return fallback

    prompt = TRANSLATE_NOVEL_INFO_PROMPT.format(
        title=title, author=author, description=description[:1000]
    )

    try:
        from config import (
            REWRITE_PROVIDER,
            GEMINI_API_KEY,
            ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
            DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
            GROQ_API_KEY, GROQ_FALLBACK_MODELS,
            OLLAMA_BASE_URL, OLLAMA_MODEL,
        )
    except ImportError:
        return fallback

    provider = REWRITE_PROVIDER
    result_text = None

    if provider == "gemini" and GEMINI_API_KEY:
        for model in GEMINI_TRANSLATE_MODELS:
            result_text = _translate_gemini(prompt, GEMINI_API_KEY, model)
            if result_text:
                break
    elif provider == "anthropic" and ANTHROPIC_API_KEY:
        result_text = _translate_anthropic(prompt, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
    elif provider == "deepseek" and DEEPSEEK_API_KEY:
        result_text = _translate_deepseek(prompt, DEEPSEEK_API_KEY, DEEPSEEK_MODEL)
    elif provider == "groq" and GROQ_API_KEY:
        result_text = _translate_groq(prompt, GROQ_API_KEY, GROQ_FALLBACK_MODELS)
    elif provider == "ollama":
        result_text = _translate_ollama(prompt, OLLAMA_BASE_URL, OLLAMA_MODEL)

    if not result_text:
        return fallback

    # Extract JSON from response
    try:
        # Strip markdown code fences if any
        clean = result_text.strip().strip("```json").strip("```").strip()
        data = json.loads(clean)
        return {
            "title": data.get("title", title),
            "author": data.get("author", author),
            "description": data.get("description", description),
        }
    except Exception:
        return fallback


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_chunks(text: str, chunk_size: int) -> list[str]:
    """Tách text thành các chunk theo đoạn văn."""
    if len(text) <= chunk_size:
        return [text]
    paragraphs = text.split('\n\n')
    chunks, current = [], []
    size = 0
    for p in paragraphs:
        if size + len(p) > chunk_size and current:
            chunks.append('\n\n'.join(current))
            current, size = [], 0
        current.append(p)
        size += len(p)
    if current:
        chunks.append('\n\n'.join(current))
    return chunks
