"""
Build Vietnamese syllable dictionary từ corpus crawled (docx_output/*.json).

Mục đích: cung cấp cho `vi_validator` một set các âm tiết THỰC SỰ dùng trong
văn bản crawl, để bước auto-correct có thể loại các ứng viên "phonotactic
valid nhưng không phải từ thật" (VD: `cáủ` hợp lệ âm vị học nhưng không
xuất hiện → không chấp nhận).

Chạy:
    python crawler/tools/build_syllable_dict.py

Output:
    crawler/data/vi_syllables.txt  (1 âm tiết / dòng, lowercase)

Chiến lược:
1. Đọc content từ mọi *.json trong docx_output/*/chapters/*.json
2. Tokenize bằng _WORD_RE của vi_validator
3. Đếm tần suất từng âm tiết lowercase
4. Giữ âm tiết có:
   - count >= MIN_COUNT (mặc định 3) → lọc noise/OCR
   - is_valid_syllable(word) → loại OCR corruption đã lọt vào corpus
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWLER_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, CRAWLER_DIR)

from vi_validator import _WORD_RE, is_valid_syllable  # noqa: E402

CORPUS_DIR = os.path.join(CRAWLER_DIR, "docx_output")
DATA_DIR = os.path.join(CRAWLER_DIR, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "vi_syllables.txt")

MIN_COUNT = 2  # âm tiết xuất hiện < 2 lần coi như nhiễu/OCR


def collect_syllables(corpus_dir: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    n_files = 0
    for root, _dirs, files in os.walk(corpus_dir):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"  ⚠️ Skip {path}: {e}", file=sys.stderr)
                continue
            n_files += 1
            content = data.get("content") or data.get("text") or ""
            title = data.get("title") or ""
            for text in (title, content):
                if not text:
                    continue
                for match in _WORD_RE.finditer(text):
                    counter[match.group(0).lower()] += 1
    print(f"Quét {n_files} chapter JSON.")
    return counter


def filter_syllables(counter: Counter[str]) -> list[str]:
    kept: list[str] = []
    for word, count in counter.items():
        if count < MIN_COUNT:
            continue
        if not is_valid_syllable(word):
            continue
        kept.append(word)
    kept.sort()
    return kept


def main() -> int:
    if not os.path.isdir(CORPUS_DIR):
        print(f"❌ Không tìm thấy corpus: {CORPUS_DIR}", file=sys.stderr)
        return 1

    print(f"Đọc corpus từ: {CORPUS_DIR}")
    counter = collect_syllables(CORPUS_DIR)
    print(f"Tổng unique âm tiết (lowercase): {len(counter):,}")

    syllables = filter_syllables(counter)
    print(f"Giữ lại (count >= {MIN_COUNT} + phonotactic valid): {len(syllables):,}")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for w in syllables:
            f.write(w + "\n")
    print(f"✓ Đã ghi: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
