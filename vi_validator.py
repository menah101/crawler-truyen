"""
Vietnamese syllable validator + auto-corrector.

Thay thế cách liệt kê tay trong _OCR_MAP bằng quy tắc âm vị học tiếng Việt.
Không cần dataset ngoài — validator tự suy luận tính hợp lệ của âm tiết dựa
trên tập ÂM ĐẦU (onsets) và VẦN (rhymes) chuẩn.

Workflow:
1. `is_valid_syllable(word)`: decompose → check onset + rhyme + ràng buộc.
2. `_is_suspicious(word)`: phát hiện dấu hiệu corruption do AI (ký tự lặp,
   cụm nguyên âm bất hợp lệ). Chỉ từ suspicious mới bị auto-correct để
   tránh động vào danh từ riêng / từ tiếng Anh.
3. `correct_syllable(word)`: sinh ứng viên sửa (collapse ký tự lặp, xóa 1
   ký tự, ...) rồi validate — trả âm tiết hợp lệ đầu tiên.
4. `process_text(text)`: quét toàn văn bản, sửa các âm tiết suspicious,
   trả `(corrected_text, ValidationStats)`.

Stats dùng để:
- Cho pipeline rewriter quyết định retry (tỷ lệ corruption > ngưỡng).
- Log báo cáo số từ được sửa tự động.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

# ─── Âm đầu (onsets) ──────────────────────────────────────────
# Sắp xếp theo độ dài giảm dần để match greedy chuẩn.
_ONSETS = sorted(
    [
        "", "b", "c", "ch", "d", "đ", "g", "gh", "gi", "h", "k", "kh",
        "l", "m", "n", "ng", "ngh", "nh", "p", "ph", "qu", "r", "s",
        "t", "th", "tr", "v", "x",
    ],
    key=len,
    reverse=True,
)

# ─── Vần (rhymes — không dấu) ─────────────────────────────────
# Bao gồm cả vần mở, vần đóng, diphthong, triphthong.
# Nguồn: cấu trúc âm vị học tiếng Việt chuẩn (~155 vần).
_RHYMES: frozenset[str] = frozenset(
    {
        # Nguyên âm đơn mở
        "a", "ă", "â", "e", "ê", "i", "o", "ô", "ơ", "u", "ư", "y",
        # Nguyên âm đôi/ba mở
        "ai", "ao", "au", "ay", "âu", "ây", "eo", "êu", "ia", "iu",
        "oa", "oe", "oi", "ôi", "ơi", "ua", "uê", "ui", "uơ", "uy",
        "ưa", "ưi", "ưu", "ya", "yê",
        "iêu", "oai", "oao", "oay", "oeo", "uây", "uôi", "uya", "uyu",
        "ươi", "ươu", "yêu",
        # Vần đóng với coda đơn giản
        "ac", "ach", "am", "an", "ang", "anh", "ap", "at",
        "ăc", "ăm", "ăn", "ăng", "ăp", "ăt",
        "âc", "âm", "ân", "âng", "âp", "ât",
        "ec", "em", "en", "eng", "ep", "et",
        "êch", "êm", "ên", "ênh", "êp", "êt",
        "ich", "im", "in", "inh", "ip", "it",
        "oc", "om", "on", "ong", "oong", "op", "ot",
        "ôc", "ôm", "ôn", "ông", "ôp", "ôt",
        "ơm", "ơn", "ơp", "ơt",
        "uc", "um", "un", "ung", "up", "ut",
        "ưc", "ưm", "ưn", "ưng", "ưp", "ưt",
        "ym", "yn", "yp", "yt",  # y-variants của i-rhymes (quýt, ...)
        # Diphthong + coda
        "iêc", "iêm", "iên", "iêng", "iêp", "iêt",
        "yêm", "yên", "yêng", "yêt",
        "uôc", "uôm", "uôn", "uông", "uôt",
        "ươc", "ươm", "ươn", "ương", "ươp", "ươt",
        "oac", "oach", "oam", "oan", "oang", "oanh", "oap", "oat",
        "oăc", "oăm", "oăn", "oăng", "oăp", "oăt",
        "oem", "oen", "oet",
        "uân", "uâng", "uât",
        "uêch", "uên", "uênh",
        "uych", "uyên", "uyêt", "uynh", "uyt", "uyp",
    }
)

# ─── Dấu thanh ────────────────────────────────────────────────
# Mỗi nguyên âm base → 6 biến thể dấu: [ngang, huyền, sắc, hỏi, ngã, nặng]
_TONE_TABLE = {
    "a": "aàáảãạ", "ă": "ăằắẳẵặ", "â": "âầấẩẫậ",
    "e": "eèéẻẽẹ", "ê": "êềếểễệ", "i": "iìíỉĩị",
    "o": "oòóỏõọ", "ô": "ôồốổỗộ", "ơ": "ơờớởỡợ",
    "u": "uùúủũụ", "ư": "ưừứửữự", "y": "yỳýỷỹỵ",
}

# Reverse: ký tự có dấu → (ký tự base, chỉ số dấu 0..5)
_TONED_TO_BASE: dict[str, tuple[str, int]] = {}
for _base, _chain in _TONE_TABLE.items():
    for _idx, _ch in enumerate(_chain):
        _TONED_TO_BASE[_ch] = (_base, _idx)
        _TONED_TO_BASE[_ch.upper()] = (_base.upper(), _idx)


def _strip_tones(word: str) -> tuple[str, int]:
    """Bóc toàn bộ dấu thanh. Trả (base, tone_index 0..5)."""
    tone_idx = 0
    out: list[str] = []
    for ch in word:
        entry = _TONED_TO_BASE.get(ch)
        if entry is not None:
            base, t = entry
            out.append(base)
            if t > 0:
                tone_idx = t
        else:
            out.append(ch)
    return "".join(out), tone_idx


def _onset_rhyme_compat(onset: str, rhyme: str) -> bool:
    """Ràng buộc chính tả giữa onset và rhyme."""
    if not rhyme:
        return False
    first = rhyme[0]
    # "Front vowel": e, ê, i (và mở rộng cho iê, ia)
    front = first in ("e", "ê", "i") or rhyme.startswith(("iê", "ia"))

    if onset in ("gh", "ngh"):
        return front
    if onset == "ng":
        return not front
    if onset == "g":
        # 'g' trước e/ê/i phải viết 'gh' → không hợp lệ
        return not front
    if onset == "c":
        # 'c' trước e/ê/i phải viết 'k' → không hợp lệ
        return not front
    if onset == "k":
        return front or first == "y"
    if onset == "qu":
        # 'qu' + 'u' → 'quu' không tồn tại
        return first != "u"
    return True


@lru_cache(maxsize=65536)
def is_valid_syllable(word: str) -> bool:
    """
    Trả True nếu `word` là âm tiết tiếng Việt hợp lệ (thuần âm vị học).
    Từ không phải alphabet (chứa số, ký hiệu) → trả True (bỏ qua).
    """
    if not word:
        return False
    if not word.isalpha():
        return True  # từ hỗn hợp (số, gạch nối) — không check
    word_lower = word.lower()
    base, _tone = _strip_tones(word_lower)
    if not base:
        return False

    for onset in _ONSETS:
        if not base.startswith(onset):
            continue
        rhyme = base[len(onset) :]
        if rhyme in _RHYMES and _onset_rhyme_compat(onset, rhyme):
            return True
        # Xử lý collapse 'gi + i-' → 'gi-':
        #   'giếng' logical = gi + iêng, written = gi + êng
        #   'giặt'  logical = gi + ặt    (no collapse)
        #   Khi onset là 'gi' và rhyme trực tiếp không hợp lệ,
        #   thử thêm 'i' vào đầu rhyme để phục hồi dạng logic.
        if onset == "gi" and rhyme:
            restored = "i" + rhyme
            if restored in _RHYMES:
                return True

    # Xử lý đặc biệt: 'gi' đứng một mình ('gì', 'gỉ', 'gí', ...)
    if base == "gi":
        return True

    return False


# ─── Phát hiện corruption ─────────────────────────────────────

# Cụm 2+ ký tự cùng base liên tiếp (ví dụ 'uu', 'ưư', 'ôô', 'ữữ') — dấu hiệu
# AI rewriter merge ký tự. 'oo' trong 'oong' hợp lệ nhưng hiếm — có thể xử lý
# đặc biệt nếu cần.
_VALID_DOUBLE_VOWEL = {"oong"}  # vần đặc biệt (loanword)


def _has_invalid_vowel_cluster(word: str) -> bool:
    """Phát hiện cụm nguyên âm lặp bất hợp lệ."""
    word_lower = word.lower()
    # Bỏ qua nếu chứa 'oong' (hợp lệ)
    if "oong" in word_lower:
        stripped = word_lower.replace("oong", "")
    else:
        stripped = word_lower

    # Ký tự lặp 2+ lần liên tiếp (base giống nhau)
    for i in range(len(stripped) - 1):
        a, b = stripped[i], stripped[i + 1]
        a_base = _TONED_TO_BASE.get(a, (a, 0))[0]
        b_base = _TONED_TO_BASE.get(b, (b, 0))[0]
        if a_base == b_base and a_base in _TONE_TABLE:
            return True
    return False


def _is_suspicious(word: str) -> bool:
    """
    Kiểm tra xem word có dấu hiệu bị AI rewriter làm hỏng không.
    Chỉ từ suspicious mới được auto-correct — tránh động vào danh từ riêng
    hoặc từ tiếng Anh không có trong từ điển âm tiết Việt.

    Heuristic: từ phải có ký tự đặc biệt tiếng Việt (dấu thanh hoặc ký tự
    `ăâđêôơư`). Nếu không → có thể là tiếng Anh/tên riêng → bỏ qua.
    Từ quá ngắn (< 2 chars) → không xét để tránh xử lý sai chữ cái đơn.
    """
    if len(word) < 2 or not word.isalpha():
        return False
    has_vi_diacritic = any(
        ch in _TONED_TO_BASE and _TONED_TO_BASE[ch][1] > 0 for ch in word
    )
    has_vi_char = any(ch.lower() in "ăâđêôơư" for ch in word)
    return has_vi_diacritic or has_vi_char


# ─── Rule-based corrector ─────────────────────────────────────


def _collapse_repeated(word: str) -> str:
    """Collapse ký tự lặp liền nhau: 'ưương' → 'ương', 'nhưưng' → 'nhưng'."""
    return re.sub(r"(.)\1+", r"\1", word)


def _collapse_repeated_block(word: str) -> str:
    """
    Collapse block 2-3 ký tự lặp liền nhau.
    Ví dụ: 'ươương' có block 'ươ' lặp → 'ương'; 'nhanhnanh' → 'nhanh' (ít gặp).
    """
    # Thử block size 2, rồi 3
    for size in (2, 3):
        word = re.sub(rf"(.{{{size}}})\1+", r"\1", word)
    return word


def _collapse_same_base(word: str) -> str:
    """
    Collapse các ký tự liền nhau có cùng base vowel (nhưng có thể khác dấu).
    Ví dụ: 'nhữững' (ữ + ữ) → 'những'; 'ngưười' (ư + ư) → 'người'.
    Khi gặp 2 ký tự cùng base, giữ ký tự có dấu (tone > 0), bỏ ký tự còn lại.
    """
    if len(word) < 2:
        return word
    out: list[str] = []
    i = 0
    while i < len(word):
        ch = word[i]
        cur_base, cur_tone = _TONED_TO_BASE.get(ch, (ch, 0))
        if i + 1 < len(word) and cur_base in _TONE_TABLE:
            next_ch = word[i + 1]
            nxt_base, nxt_tone = _TONED_TO_BASE.get(next_ch, (next_ch, 0))
            if nxt_base == cur_base:
                # Giữ ký tự có dấu (nếu cả 2 không dấu, giữ 1)
                keeper = ch if cur_tone >= nxt_tone else next_ch
                out.append(keeper)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _safe_candidates(word: str) -> list[str]:
    """
    Ứng viên sửa SAFE: chỉ dùng collapse rules (gộp ký tự lặp/cùng base).
    Các rule này luôn an toàn vì chỉ loại bỏ ký tự thừa — không tạo từ
    valid-but-wrong. Dùng cho auto-correction.
    """
    seen: set[str] = set()
    candidates: list[str] = []

    def add(cand: str) -> None:
        if cand and cand != word and cand not in seen:
            seen.add(cand)
            candidates.append(cand)

    add(_collapse_same_base(word))
    add(_collapse_repeated(word))
    add(_collapse_repeated_block(word))
    add(_collapse_repeated(_collapse_same_base(word)))
    add(_collapse_same_base(_collapse_repeated(word)))
    add(_collapse_repeated_block(_collapse_same_base(word)))
    add(_collapse_same_base(_collapse_repeated_block(word)))

    return candidates


def correct_syllable(word: str) -> str | None:
    """
    Thử sửa 1 âm tiết hỏng bằng SAFE rules (collapse-only).
    Trả âm tiết hợp lệ hoặc None nếu không sửa an toàn được.
    Bảo toàn hoa/thường ở ký tự đầu.

    Các lỗi không sửa được (thiếu/dư ký tự không phải lặp) sẽ được để
    nguyên cho pipeline retry hoặc user review tay. Điều này quan trọng
    vì brute-force deletion có thể tạo từ đúng-nhưng-sai-nghĩa
    (ví dụ: 'cườư' → 'cư', mất hoàn toàn ý 'cười').
    """
    if is_valid_syllable(word):
        return word

    was_upper = word[:1].isupper()
    lower = word.lower()

    for cand in _safe_candidates(lower):
        if is_valid_syllable(cand):
            if was_upper and cand:
                return cand[0].upper() + cand[1:]
            return cand
    return None


# ─── Text-level processing ────────────────────────────────────

# Regex tách "từ" (âm tiết) tiếng Việt. Chỉ bắt chữ cái (bao gồm dấu).
_WORD_RE = re.compile(r"[A-Za-zÀ-ỹĐđ]+", re.UNICODE)


@dataclass
class ValidationStats:
    total_words: int = 0
    invalid_words: int = 0  # suspicious + not valid (AI corruption)
    corrected: int = 0
    uncorrectable: list[str] = field(default_factory=list)

    @property
    def invalid_ratio(self) -> float:
        if self.total_words == 0:
            return 0.0
        return self.invalid_words / self.total_words

    def __repr__(self) -> str:
        return (
            f"ValidationStats(total={self.total_words}, "
            f"invalid={self.invalid_words}, "
            f"corrected={self.corrected}, "
            f"ratio={self.invalid_ratio:.2%})"
        )


def process_text(text: str) -> tuple[str, ValidationStats]:
    """
    Validate + auto-correct âm tiết hỏng trong text.
    Trả (corrected_text, stats).
    """
    stats = ValidationStats()

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        stats.total_words += 1

        # Chỉ can thiệp khi từ SUSPICIOUS (có dấu hiệu corruption)
        # → tránh động vào danh từ riêng, tên tiếng Anh
        if not _is_suspicious(word):
            return word

        if is_valid_syllable(word):
            return word

        stats.invalid_words += 1
        fixed = correct_syllable(word)
        if fixed and fixed != word:
            stats.corrected += 1
            return fixed
        stats.uncorrectable.append(word)
        return word

    corrected = _WORD_RE.sub(replace, text)
    return corrected, stats


def validate_text(text: str) -> ValidationStats:
    """Chỉ validate (không sửa). Trả stats để pipeline quyết định retry."""
    stats = ValidationStats()
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        stats.total_words += 1
        if _is_suspicious(word) and not is_valid_syllable(word):
            stats.invalid_words += 1
            stats.uncorrectable.append(word)
    return stats


# ─── Self-test ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Test cases: (input, expected_is_valid, expected_correction_or_None)
    valid_tests = [
        "người", "những", "được", "không", "một", "trong", "thương",
        "cười", "nước", "đường", "trước", "muốn", "chuyện", "truyện",
        "quả", "quyền", "khuya", "nghe", "nghĩ", "gì", "gỉ", "già",
        "tia", "mía", "bún", "ba", "má", "cậu", "hoa", "hoạ",
        "tôi", "sao", "sánh", "so", "vậy", "ấy", "sự",
    ]
    print("=== Valid syllables ===")
    for w in valid_tests:
        v = is_valid_syllable(w)
        mark = "✓" if v else "✗"
        print(f"  {mark} {w!r}")
        assert v, f"Expected valid: {w!r}"

    invalid_tests = [
        "ngưười", "nhữững", "đượều", "khôông", "nhưưng", "đưươc",
        "ngưươi", "ươương", "ưương", "đượợc", "chuuyện", "truuyện",
        "nưóc",  # OCR: 'nuoc' với dấu sai chỗ
    ]
    print("\n=== Invalid syllables (should be fixable) ===")
    passed = 0
    for w in invalid_tests:
        v = is_valid_syllable(w)
        fixed = correct_syllable(w)
        mark = "✓" if (not v and fixed and fixed != w) else "✗"
        print(f"  {mark} {w!r} → {fixed!r}")
        if not v and fixed:
            passed += 1
    print(f"\n{passed}/{len(invalid_tests)} corrupted syllables auto-corrected")

    # Proper nouns / English words — không nên bị đụng vào
    foreign_tests = ["Claude", "John", "Python", "API", "GPT", "Linux"]
    print("\n=== Foreign words (must pass through untouched) ===")
    for w in foreign_tests:
        _txt, _s = process_text(w)
        mark = "✓" if _txt == w else "✗"
        print(f"  {mark} {w!r} → {_txt!r}")

    # End-to-end text test
    sample = "Tôi nhìn nhữững ngưười đó và cảm thấy đượều kỳ lạ. Anh Claude cười."
    fixed_text, stats = process_text(sample)
    print(f"\n=== Text sample ===")
    print(f"IN : {sample}")
    print(f"OUT: {fixed_text}")
    print(f"    {stats}")

    sys.exit(0)
