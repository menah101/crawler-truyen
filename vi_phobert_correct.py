"""
Tầng 3 — PhoBERT MLM re-ranker, chèn giữa vi_fuzz_correct (Tầng 2) và
vi_llm_correct (Tầng 4).

Workflow:
  1. Tầng 2 (rapidfuzz) chỉ fix khi CÓ DUY NHẤT 1 ứng viên với min ED.
     Khi có ≥ 2 ứng viên cùng ED (vd: `tôài` → `tài` hoặc `tôi`), nó
     defer cho tầng sau.
  2. Tầng 3 (PhoBERT) regenerate top-K candidates bằng rapidfuzz, mask
     vị trí âm tiết hỏng trong câu, score từng ứng viên bằng MLM
     log-prob tại mask position. Pick winner nếu gap > threshold.
  3. Còn dư → tầng 4 (Gemini/Anthropic LLM).

Tradeoffs:
  - PhoBERT-base-v2 ~540MB model, ~600MB RAM, lần đầu tải ~30s.
  - Inference CPU ~50-200ms/residual, MPS (Apple Silicon) ~10-50ms.
  - Pretrained trên news+wiki tiếng Việt → mạnh hơn n-gram, yếu hơn
    Gemini cho văn phong fiction đặc biệt (cổ trang).
  - Singleton: model load 1 lần, giữ trong process → amortize cost.

Thữ nghiệm thành công → enable qua VI_PHOBERT_FIX_ENABLED=true. Mặc định
OFF để tránh người dùng không biết bị tải model.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForMaskedLM
    _ML_OK = True
except ImportError:
    _ML_OK = False

try:
    from vi_validator import is_valid_syllable  # type: ignore
    from vi_fuzz_correct import _candidates_for, _load_dict_list, _restore_case  # type: ignore
except ImportError:
    from .vi_validator import is_valid_syllable  # type: ignore
    from .vi_fuzz_correct import _candidates_for, _load_dict_list, _restore_case  # type: ignore


_MODEL_NAME = os.environ.get("VI_PHOBERT_MODEL", "vinai/phobert-base-v2")
_CONTEXT_WINDOW = 80         # chars 2 phía bị mask
_MIN_LOGPROB_GAP = 1.5       # nat. e^1.5 ≈ 4.5x ưu thế → confident pick
_MAX_TOKENS = 256            # truncate context để tốc độ ổn định
_MIN_LEN = 3                 # giống vi_fuzz: < 3 chữ dễ collision


class _PhoBert:
    """Singleton MLM scorer. Lazy-load để import-time rẻ."""

    _instance: "_PhoBert | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._loaded = False
                    cls._instance = obj
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        logger.info("vi_phobert: loading %s (lần đầu sẽ tải ~540MB)...", _MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
        self.model = AutoModelForMaskedLM.from_pretrained(_MODEL_NAME)
        self.model.eval()
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")
        self.model.to(self.device)
        self.mask_token = self.tokenizer.mask_token
        self.mask_id = self.tokenizer.mask_token_id
        self._loaded = True
        logger.info("vi_phobert: ready (device=%s)", self.device)

    def score_candidates(
        self, masked_sentence: str, candidates: list[str]
    ) -> dict[str, float]:
        """
        Trả {candidate: log_prob} tại vị trí mask. Chỉ chạy model 1 lần
        cho cả batch — mỗi candidate chỉ lookup logit ở id token đầu.

        Khi candidate là multi-token (BPE split), dùng log-prob của token
        đầu tiên — xấp xỉ nhưng đủ để RANK candidates tương đối.
        """
        self._ensure_loaded()
        if not candidates:
            return {}

        inputs = self.tokenizer(
            masked_sentence,
            return_tensors="pt",
            truncation=True,
            max_length=_MAX_TOKENS,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = self.model(**inputs).logits[0]   # [seq_len, vocab]

        mask_positions = (inputs["input_ids"][0] == self.mask_id).nonzero(as_tuple=True)[0]
        if mask_positions.numel() == 0:
            return {}
        pos = int(mask_positions[0].item())
        log_probs = torch.log_softmax(logits[pos], dim=-1)

        scores: dict[str, float] = {}
        for cand in candidates:
            cand_ids = self.tokenizer(cand, add_special_tokens=False).input_ids
            if not cand_ids:
                continue
            scores[cand] = float(log_probs[cand_ids[0]].item())
        return scores


def _build_masked_sentence(text: str, bad: str, mask_token: str) -> tuple[str, int] | None:
    """Cắt window xung quanh `bad` và thay `bad` bằng mask_token."""
    idx = text.find(bad)
    if idx < 0:
        return None
    s = max(0, idx - _CONTEXT_WINDOW)
    e = min(len(text), idx + len(bad) + _CONTEXT_WINDOW)
    masked = text[s:idx] + mask_token + text[idx + len(bad) : e]
    return masked, idx


def correct_residuals_phobert(
    text: str, residuals: list[str]
) -> Tuple[str, dict[str, str]]:
    """
    Re-rank fuzzy candidates bằng PhoBERT MLM context.
    Trả (corrected_text, {bad: fixed}). Fail-safe: lỗi ML/mô hình → ({},{})

    Chỉ cố gắng sửa residual có ≥ 2 fuzz candidate ED nhỏ nhất — đó
    là nhóm vi_fuzz_correct đã defer. Residual có 0 candidate (vd onset
    hỏng `gngười`) tiếp tục defer LLM.
    """
    if not residuals or not _ML_OK:
        return text, {}

    try:
        from config import VI_PHOBERT_FIX_ENABLED  # type: ignore
        if not VI_PHOBERT_FIX_ENABLED:
            return text, {}
    except ImportError:
        return text, {}

    dictionary = _load_dict_list()
    if not dictionary:
        return text, {}

    try:
        bert = _PhoBert()
        bert._ensure_loaded()
    except Exception as e:
        logger.warning("vi_phobert: load model fail: %s — skip", e)
        return text, {}

    fixes: dict[str, str] = {}
    seen: set[str] = set()
    for bad in residuals:
        if bad in seen:
            continue
        seen.add(bad)
        if len(bad) < _MIN_LEN or is_valid_syllable(bad):
            continue

        cands = _candidates_for(bad.lower(), dictionary)
        if len(cands) < 2:
            continue   # 0 → onset hỏng / out-of-dict ; 1 → fuzz đã fix
        # Chỉ giữ những candidate ở mức ED tối thiểu (cùng hạng ambiguous)
        min_ed = cands[0][2]
        cand_strs = [c for c, _, ed in cands if ed == min_ed]
        if len(cand_strs) < 2:
            continue

        built = _build_masked_sentence(text, bad, bert.mask_token)
        if built is None:
            continue
        masked_sentence, _ = built

        try:
            scored = bert.score_candidates(masked_sentence, cand_strs)
        except Exception as e:
            logger.warning("vi_phobert: score fail (%s) bad=%r — defer LLM", e, bad)
            continue
        if len(scored) < 2:
            continue

        ranked = sorted(scored.items(), key=lambda kv: -kv[1])
        top, runner = ranked[0], ranked[1]
        gap = top[1] - runner[1]
        if gap < _MIN_LOGPROB_GAP:
            logger.debug(
                "vi_phobert: %r ambiguous (gap=%.2f < %.2f) — defer LLM. Top: %s",
                bad, gap, _MIN_LOGPROB_GAP, ranked[:3],
            )
            continue
        if not is_valid_syllable(top[0]):
            continue
        fixes[bad] = _restore_case(bad, top[0])

    if not fixes:
        return text, {}

    corrected = text
    applied: dict[str, str] = {}
    for bad, good in fixes.items():
        pattern = re.compile(
            r"(?<![A-Za-zÀ-ỹĐđ])" + re.escape(bad) + r"(?![A-Za-zÀ-ỹĐđ])",
            re.UNICODE,
        )
        new_text, n = pattern.subn(good, corrected)
        if n > 0:
            corrected = new_text
            applied[bad] = good

    return corrected, applied


# ─── Self-test ──────────────────────────────────────

if __name__ == "__main__":
    import sys
    if not _ML_OK:
        print("⚠ transformers/torch chưa cài: pip install torch transformers")
        sys.exit(1)

    # Bypass config flag cho self-test
    os.environ.setdefault("VI_PHOBERT_FIX_ENABLED", "true")
    import importlib
    import config  # type: ignore
    config.VI_PHOBERT_FIX_ENABLED = True   # type: ignore

    # Ambiguous cases mà vi_fuzz defer (≥2 candidate ED min)
    cases = [
        # (sentence với residual, residual, expected fix)
        ("Cô ấy cầm một bóng hồng tôài đẹp lắ màu sắc.", "tôài", None),  # màu tôi / bóng tài
        ("Anh ấy nhìn bóng hình của mộng tình, mộọng với nuối tiếc.", "mộọng", None),
        ("Trời hôm nay nhằnh chóng chuyển mây đen đổ mưa.", "nhằnh", "nhanh"),
    ]
    print("=== PhoBERT re-ranking ===")
    for sent, bad, expected in cases:
        text, fixes = correct_residuals_phobert(sent, [bad])
        got = fixes.get(bad)
        mark = "?" if expected is None else ("✓" if got == expected else "✗")
        print(f"  {mark} {bad!r} → {got!r} (expected {expected!r})")
        print(f"    OUT: {text}")
