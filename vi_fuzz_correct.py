"""
Tầng giữa giữa vi_validator (rule-based) và vi_llm_correct (LLM).

Khi vi_validator để lại residuals (âm tiết hỏng không tự sửa được), thay vì
gọi thẳng LLM, ta thử match residual với dictionary ~4.7k âm tiết tiếng Việt
chuẩn bằng rapidfuzz. Triết lý:

  - AI rewriter thường chèn 1-2 ký tự thừa hoặc lộn dấu → edit distance ≤ 2
    so với âm tiết đúng.
  - Onset (phụ âm đầu) hiếm khi bị hỏng → giữ nguyên giúp loại nhiễu.
  - Chỉ áp dụng khi có **đúng 1** ứng viên thỏa mọi filter — tránh
    "valid-but-wrong" (vd: chọn sai âm tiết cùng onset nhưng khác nghĩa).

Kết quả: giảm số lần phải gọi Gemini/Anthropic xuống đáng kể, không phụ
thuộc network, deterministic và miễn phí.

Ứng viên ambiguous (≥ 2 dict-match thỏa) được giữ nguyên trong residual list
để vi_llm_correct xử lý tiếp với context.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process
    from rapidfuzz.distance import DamerauLevenshtein
    _RAPIDFUZZ_OK = True
except ImportError:
    _RAPIDFUZZ_OK = False

try:
    from vi_validator import is_valid_syllable, _strip_tones, _ONSETS  # type: ignore
except ImportError:
    from .vi_validator import is_valid_syllable, _strip_tones, _ONSETS  # type: ignore


# ─── Tham số tuning ────────────────────────────────────────────
# ED=1 ONLY: trên thực tế ED=2 generate quá nhiều false positive
# (vd 'chuyếàng'→'chuyến' nhưng đúng là 'chuyện', 'cửại'→'chửi' đúng là 'cửa').
# Nhường ED=2 cho PhoBERT/LLM có context.
_MAX_EDIT_DISTANCE = 1
_MIN_RATIO = 75            # rapidfuzz fuzz.ratio (0-100)
_TOP_K = 8                 # over-fetch trước khi lọc
_MIN_LEN_FOR_FUZZ = 3      # 1-2 ký tự dễ collision (vd "à" → mọi vowel)


_DICT_PATH = os.path.join(os.path.dirname(__file__), "data", "vi_syllables.txt")
_DICT_LIST: list[str] | None = None


def _load_dict_list() -> list[str]:
    """Load dictionary thành list (rapidfuzz cần list, không phải set)."""
    global _DICT_LIST
    if _DICT_LIST is not None:
        return _DICT_LIST
    if not os.path.exists(_DICT_PATH):
        _DICT_LIST = []
        return _DICT_LIST
    try:
        with open(_DICT_PATH, encoding="utf-8") as f:
            _DICT_LIST = [line.strip().lower() for line in f if line.strip()]
    except Exception as e:
        logger.warning("vi_fuzz: không load được dict: %s", e)
        _DICT_LIST = []
    return _DICT_LIST


def _extract_onset(word: str) -> str:
    """
    Trích ONSET đầy đủ ('b', 'ch', 'ngh', 'gi'...) sau khi strip dấu thanh.
    Quan trọng: phân biệt 'c' vs 'ch', 'n' vs 'ng' vs 'ngh', 't' vs 'th' vs 'tr'.

    Match theo độ dài giảm dần (giống vi_validator._is_valid_syllable):
    'ngh'  → 'ngh'
    'ng'   → 'ng'
    'nh'   → 'nh'
    'tr'   → 'tr'
    'th'   → 'th'
    'ch'   → 'ch'
    'kh'   → 'kh'
    'gh'   → 'gh'
    'gi'   → 'gi'
    'ph'   → 'ph'
    'qu'   → 'qu'
    'b/c/d/đ/g/h/k/l/m/n/p/r/s/t/v/x' → đơn
    Còn lại → ''
    """
    base, _ = _strip_tones(word)
    if not base:
        return ""
    for onset in _ONSETS:
        if onset and base.startswith(onset):
            return onset
    return ""


def _candidates_for(word: str, dictionary: list[str]) -> list[tuple[str, float, int]]:
    """
    Top-K ứng viên từ dict. Mỗi tuple = (candidate, fuzz_ratio, edit_distance).
    Đã filter:
      - ratio ≥ _MIN_RATIO
      - edit distance ≤ _MAX_EDIT_DISTANCE
      - cùng ONSET đầy đủ (b/ch/ngh/...) — phân biệt 'c' vs 'ch', 'n' vs 'ng'
    """
    word_onset = _extract_onset(word)
    # Cho phép word có onset rỗng (vần thuần như 'an', 'ơi', 'ôên')
    # nhưng candidates cũng phải onset rỗng — không match across onset class.

    raw = process.extract(
        word,
        dictionary,
        scorer=fuzz.ratio,
        limit=_TOP_K * 4,
        score_cutoff=_MIN_RATIO,
    )

    out: list[tuple[str, float, int]] = []
    for cand, score, _ in raw:
        ed = DamerauLevenshtein.distance(word, cand)
        if ed > _MAX_EDIT_DISTANCE:
            continue
        if _extract_onset(cand) != word_onset:
            continue
        out.append((cand, score, ed))

    # Ưu tiên ED nhỏ nhất, rồi score cao nhất
    out.sort(key=lambda t: (t[2], -t[1]))
    return out[:_TOP_K]


def _pick_unambiguous(candidates: list[tuple[str, float, int]]) -> str | None:
    """
    Chỉ trả ứng viên khi KHÔNG ambiguous. Quy tắc:
      - 0 ứng viên → None
      - 1 ứng viên → chọn nó
      - ≥ 2 ứng viên CÙNG min ED → ambiguous, defer LLM
      - ≥ 2 ứng viên với ED khác nhau → chọn ứng viên có ED nhỏ nhất
        (corruption thường chỉ chèn 1 char → ED=1 là chính xác)
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    min_ed = candidates[0][2]
    tied = [c for c in candidates if c[2] == min_ed]
    if len(tied) > 1:
        return None
    return tied[0][0]


def _restore_case(original: str, replacement: str) -> str:
    """Bảo toàn capitalization của ký tự đầu."""
    if not replacement:
        return replacement
    if original[:1].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def correct_residuals_fuzz(
    text: str, residuals: list[str]
) -> Tuple[str, dict[str, str]]:
    """
    Sửa residuals bằng rapidfuzz vs dictionary âm tiết tiếng Việt.

    Trả (corrected_text, {bad: fixed}). Fail-safe: rapidfuzz/dict không có →
    trả (text, {}) — pipeline sẽ tự rơi xuống vi_llm_correct như cũ.

    Chỉ apply fix khi:
      - residual không phải âm tiết hợp lệ (defensive double-check)
      - chỉ có 1 ứng viên với ED tối thiểu trong dict
      - ứng viên đó vẫn pass `is_valid_syllable` (sanity)
    """
    if not residuals or not _RAPIDFUZZ_OK:
        return text, {}

    # Cho phép tắt qua config (matching pattern của vi_llm_correct).
    # Khi config không import được — chạy standalone — mặc định bật.
    try:
        from config import VI_FUZZ_FIX_ENABLED  # type: ignore
        if not VI_FUZZ_FIX_ENABLED:
            return text, {}
    except ImportError:
        pass

    dictionary = _load_dict_list()
    if not dictionary:
        logger.debug("vi_fuzz: dict rỗng, skip")
        return text, {}

    fixes: dict[str, str] = {}
    seen: set[str] = set()
    for bad in residuals:
        if bad in seen:
            continue
        seen.add(bad)
        if len(bad) < _MIN_LEN_FOR_FUZZ:
            continue
        if is_valid_syllable(bad):
            continue

        cands = _candidates_for(bad.lower(), dictionary)
        pick = _pick_unambiguous(cands)
        if not pick or not is_valid_syllable(pick):
            continue
        if pick == bad.lower():
            continue
        fixes[bad] = _restore_case(bad, pick)

    if not fixes:
        return text, {}

    corrected = text
    applied: dict[str, str] = {}
    for bad, good in fixes.items():
        # Khớp word-boundary tiếng Việt (đồng bộ với vi_llm_correct)
        pattern = re.compile(
            r"(?<![A-Za-zÀ-ỹĐđ])" + re.escape(bad) + r"(?![A-Za-zÀ-ỹĐđ])",
            re.UNICODE,
        )
        new_text, n = pattern.subn(good, corrected)
        if n > 0:
            corrected = new_text
            applied[bad] = good

    return corrected, applied


# ─── Self-test ────────────────────────────────────────────────

if __name__ == "__main__":
    if not _RAPIDFUZZ_OK:
        print("⚠ rapidfuzz chưa được cài: pip install rapidfuzz")
        raise SystemExit(1)

    # Sample corruptions từ AI rewriter (đã thấy trong log thực tế)
    test_residuals = [
        "lỏửa",      # → lửa
        "nhưột",     # → nhột
        "ngưười",    # → người
        "nhữững",    # → những
        "ththật",    # → thật (lặp onset)
        "gngười",    # → người (chèn onset thừa)
        "Đêắng",     # → Đắng (giữ hoa)
        "khôông",    # → không
        "đượợc",     # → được
        "trườờng",   # → trường
    ]
    sample = " ".join(test_residuals) + " và 1 từ thường: hôm nay."
    fixed, applied = correct_residuals_fuzz(sample, test_residuals)
    print("=== rapidfuzz residual fix ===")
    print(f"IN : {sample}")
    print(f"OUT: {fixed}")
    print(f"Fixes ({len(applied)}):")
    for bad, good in applied.items():
        print(f"  {bad!r} → {good!r}")

    # Ambiguous case — không nên sửa
    ambig = ["mộọng", "tôài"]   # cả 2 đều có ≥ 2 dict match (mọng/mộng, tài/tôi)
    print("\n=== Ambiguous (must NOT fix) ===")
    for w in ambig:
        cands = _candidates_for(w.lower(), _load_dict_list())
        pick = _pick_unambiguous(cands)
        print(f"  {w!r}: candidates={[(c, ed) for c, _, ed in cands[:3]]} pick={pick}")
