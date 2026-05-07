"""
Đo pipeline 4-tầng trên tập residual thực tế từ log crawler.

Usage: python tools/bench_fix_pipeline.py logs/crawl_20260417.log [--phobert]

Trích residual từ các dòng `vi_validator: ... không tự sửa được` rồi chạy
qua vi_fuzz_correct (+ optionally vi_phobert_correct), so sánh với fix mà
Gemini đã trả thực tế.

Output:
  - Tổng residual unique
  - vi_fuzz: số fix, % cover
  - vi_phobert: số fix bổ sung (nếu --phobert), % cover
  - Còn lại defer LLM: list
  - Mismatch giữa fuzz/phobert vs Gemini fix (Gemini có thể wrong)
"""

from __future__ import annotations

import ast
import re
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vi_validator import is_valid_syllable
from vi_fuzz_correct import correct_residuals_fuzz, _candidates_for, _load_dict_list


_RESIDUAL_RE = re.compile(
    r"vi_validator: \d+ âm tiết không tự sửa được \(ví dụ: (\[.*?\])\)"
)
_LLM_FIX_RE = re.compile(
    r"vi_llm: sửa thêm \d+ âm tiết bằng \S+ \(ví dụ: (\[.*?\])\)"
)


def parse_log(path: str) -> tuple[list[str], dict[str, list[str]]]:
    """Trả (all_residuals, gemini_fixes[bad] = [variants])."""
    residuals: list[str] = []
    fixes: dict[str, list[str]] = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _RESIDUAL_RE.search(line)
            if m:
                try:
                    residuals.extend(ast.literal_eval(m.group(1)))
                except Exception:
                    pass
                continue
            m = _LLM_FIX_RE.search(line)
            if m:
                try:
                    pairs = ast.literal_eval(m.group(1))
                    for bad, good in pairs:
                        fixes[bad].append(good)
                except Exception:
                    pass
    return residuals, fixes


def run_phobert(unique_residuals: list[str]) -> dict[str, str]:
    """Optional PhoBERT pass — needs sentence context. Ở đây thiếu context
    nên chỉ test khả năng top-1 candidate; fallback dùng candidate đầu tiên
    nếu PhoBERT gap đủ. Ít chính xác hơn full pipeline nhưng cho tín hiệu."""
    os.environ["VI_PHOBERT_FIX_ENABLED"] = "true"
    from vi_phobert_correct import correct_residuals_phobert

    # Tạo "câu giả" gồm các residual cách nhau bởi space — không lý tưởng
    # nhưng đủ kiểm tra: PhoBERT có pick được top candidate hay không
    fake_sentence = " ".join(unique_residuals)
    _, fixes = correct_residuals_phobert(fake_sentence, unique_residuals)
    return fixes


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: bench_fix_pipeline.py <log_path> [--phobert]")
        sys.exit(1)

    log_path = sys.argv[1]
    use_phobert = "--phobert" in sys.argv

    residuals, gemini_fixes = parse_log(log_path)
    unique = sorted(set(residuals))

    # Lọc các từ thực sự invalid (defensive)
    truly_bad = [w for w in unique if not is_valid_syllable(w)]

    print(f"📂 Log: {log_path}")
    print(f"📊 Tổng residual unique: {len(unique)}  (truly invalid: {len(truly_bad)})")
    print(f"📊 Gemini đã có fix cho: {len(gemini_fixes)} từ")
    print()

    # Tier 2: vi_fuzz
    fake_text = " ".join(truly_bad)
    _, fuzz_fixes = correct_residuals_fuzz(fake_text, truly_bad)
    print(f"=== Tier 2 (vi_fuzz) ===")
    print(f"  Fix được: {len(fuzz_fixes)}/{len(truly_bad)} ({len(fuzz_fixes)/max(1,len(truly_bad))*100:.0f}%)")
    if fuzz_fixes:
        sample = list(fuzz_fixes.items())[:10]
        print(f"  Ví dụ: {sample}")

    remain_after_fuzz = [w for w in truly_bad if w not in fuzz_fixes]

    # Tier 3: vi_phobert (optional)
    phobert_fixes: dict[str, str] = {}
    if use_phobert and remain_after_fuzz:
        print(f"\n=== Tier 3 (vi_phobert, no real context) ===")
        phobert_fixes = run_phobert(remain_after_fuzz)
        print(f"  Fix được: {len(phobert_fixes)}/{len(remain_after_fuzz)} ({len(phobert_fixes)/max(1,len(remain_after_fuzz))*100:.0f}%)")
        if phobert_fixes:
            sample = list(phobert_fixes.items())[:10]
            print(f"  Ví dụ: {sample}")

    remain_final = [w for w in remain_after_fuzz if w not in phobert_fixes]
    print(f"\n=== Defer LLM: {len(remain_final)}/{len(truly_bad)} ===")
    print(f"  Top 30: {remain_final[:30]}")

    # So sánh fuzz pick vs Gemini variants
    print(f"\n=== Sanity check: vi_fuzz pick vs Gemini variants ===")
    mismatches = []
    for bad, good in fuzz_fixes.items():
        gemini_picks = gemini_fixes.get(bad, [])
        if not gemini_picks:
            continue
        if good not in gemini_picks:
            mismatches.append((bad, good, gemini_picks))
    print(f"  Mismatch: {len(mismatches)}/{len(fuzz_fixes)} (fuzz pick KHÁC tất cả Gemini variants)")
    for bad, good, gemini in mismatches[:10]:
        print(f"    {bad!r}: fuzz={good!r}  vs  Gemini={gemini}")

    # Inconsistent Gemini fixes
    inconsistent = {b: vs for b, vs in gemini_fixes.items() if len(set(vs)) > 1}
    print(f"\n=== Gemini inconsistency: {len(inconsistent)} từ có ≥ 2 fix khác nhau ===")
    for bad, variants in list(inconsistent.items())[:10]:
        print(f"  {bad!r}: {set(variants)}")


if __name__ == "__main__":
    main()
