"""
LLM narrow-pass: sửa các âm tiết rule-based validator không tự quyết được.

Đây là lớp cuối cùng sau `vi_validator.process_text`. Chỉ can thiệp vào các
âm tiết đã được đánh dấu là "uncorrectable" — KHÔNG chạm các phần khác của
văn bản.

Chiến lược:
1. Gom unique residuals từ `ValidationStats.uncorrectable`.
2. Với mỗi residual, trích context là câu chứa nó (cắt ~150 ký tự 2 phía).
3. Gửi Gemini 1 prompt duy nhất chứa cả danh sách residual + context.
4. LLM trả JSON `{wrong: fixed}`. Parse, validate qua `is_valid_syllable`,
   rồi replace trong text.
5. Nếu LLM không chắc → trả lại nguyên âm tiết → giữ nguyên.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Tuple

import requests

# Gemini overload / rate-limit là tạm thời → retry với backoff trước khi bỏ.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAYS = [10, 30, 60]   # giây

try:
    from vi_validator import is_valid_syllable
except ImportError:
    from .vi_validator import is_valid_syllable  # type: ignore

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """Bạn là chuyên gia chính tả tiếng Việt. Văn bản dưới có các ÂM TIẾT HỎNG do lỗi OCR/AI (chèn ký tự thừa, lộn dấu). Dựa vào NGỮ CẢNH, hãy sửa MỖI âm tiết hỏng về âm tiết tiếng Việt đúng và có nghĩa trong ngữ cảnh đó.

Âm tiết hỏng cần sửa:
{residuals_block}

Quy tắc NGHIÊM NGẶT:
- CHỈ sửa đúng các âm tiết liệt kê ở trên. KHÔNG sửa chỗ khác.
- Output phải là âm tiết tiếng Việt có nghĩa, hợp quy tắc chính tả.
- Giữ đúng hoa/thường của ký tự đầu (vd "Đêắng" → "Đắng" giữ hoa).
- Nếu không chắc chắn → giá trị output = giá trị input (để nguyên).
- Trả về MỘT JSON object thuần, không markdown, không giải thích gì thêm.

Format output (ví dụ):
{{"lỏửa": "lửa", "mộọng": "mọng", "cáủa": "của"}}

Văn bản có ngữ cảnh:
---
{context_text}
---

JSON:"""


def _extract_contexts(text: str, residuals: list[str], window: int = 150) -> str:
    """
    Trích câu/đoạn chứa mỗi residual (cắt window char 2 phía).
    Gộp thành 1 block text ngắn gọn để LLM không phải đọc cả chương.
    """
    snippets: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    for bad in set(residuals):
        idx = text.find(bad)
        if idx < 0:
            continue
        start = max(0, idx - window)
        end = min(len(text), idx + len(bad) + window)
        # Tránh snippet trùng (nhiều residuals gần nhau)
        merged = False
        for s, e in list(seen_spans):
            if start <= e and end >= s:
                seen_spans.discard((s, e))
                seen_spans.add((min(s, start), max(e, end)))
                merged = True
                break
        if not merged:
            seen_spans.add((start, end))
    for s, e in sorted(seen_spans):
        snippets.append(text[s:e])
    return "\n…\n".join(snippets)


def correct_residuals_llm(
    text: str,
    residuals: list[str],
) -> Tuple[str, dict[str, str]]:
    """
    Gọi Gemini sửa residuals. Trả (corrected_text, {wrong: fixed}).
    Fail-safe: lỗi API/parse → trả (text, {}) — không làm hỏng pipeline.
    """
    if not residuals:
        return text, {}

    try:
        from config import (
            GEMINI_API_KEY,
            VI_LLM_FIX_ENABLED,
            VI_LLM_FIX_MODEL,
            VI_LLM_FIX_MAX_CHARS,
        )
    except ImportError:
        return text, {}

    if not VI_LLM_FIX_ENABLED or not GEMINI_API_KEY:
        return text, {}

    uniq = sorted(set(residuals))
    context_text = _extract_contexts(text, uniq)
    if len(context_text) > VI_LLM_FIX_MAX_CHARS:
        context_text = context_text[:VI_LLM_FIX_MAX_CHARS]

    prompt = _PROMPT_TEMPLATE.format(
        residuals_block="\n".join(f"- {r}" for r in uniq),
        context_text=context_text or "(không lấy được context)",
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{VI_LLM_FIX_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }

    resp = None
    attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
        except Exception as e:
            logger.warning("vi_llm: network error: %s", e)
            if attempt < attempts - 1:
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            return text, {}

        if resp.status_code == 200:
            break

        if resp.status_code in _RETRY_STATUS and attempt < attempts - 1:
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "vi_llm: Gemini HTTP %d — retry sau %ds (%d/%d)",
                resp.status_code, delay, attempt + 1, attempts - 1,
            )
            time.sleep(delay)
            continue

        logger.warning("vi_llm: Gemini HTTP %d — %s", resp.status_code, resp.text[:200])
        return text, {}

    if resp is None or resp.status_code != 200:
        return text, {}

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("vi_llm: parse response: %s", e)
        return text, {}

    cleaned = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        fixes_raw = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("vi_llm: invalid JSON: %s — raw=%s", e, cleaned[:200])
        return text, {}

    if not isinstance(fixes_raw, dict):
        return text, {}

    # Validate + apply fixes
    applied: dict[str, str] = {}
    corrected = text
    uniq_set = set(uniq)
    for bad, good in fixes_raw.items():
        if not isinstance(good, str) or not good:
            continue
        if bad not in uniq_set:
            continue
        if good == bad:
            continue
        if not is_valid_syllable(good):
            logger.debug("vi_llm: bỏ fix %r → %r (không hợp lệ)", bad, good)
            continue
        # Replace mọi occurrence của bad trong text bằng good.
        # Dùng regex với boundary \b nhưng tiếng Việt có ký tự unicode — dùng
        # lookaround với chữ cái rộng hơn.
        pattern = re.compile(
            r"(?<![A-Za-zÀ-ỹĐđ])" + re.escape(bad) + r"(?![A-Za-zÀ-ỹĐđ])",
            re.UNICODE,
        )
        new_text, n = pattern.subn(good, corrected)
        if n > 0:
            corrected = new_text
            applied[bad] = good

    return corrected, applied
