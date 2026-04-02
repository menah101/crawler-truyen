#!/usr/bin/env python3
"""
Chuẩn hóa description của truyện trong DB.

Dùng cùng logic sanitize_description() từ crawler/rewriter.py.

Usage:
    python crawler/normalize_descriptions.py --dry-run    # Xem trước thay đổi
    python crawler/normalize_descriptions.py --apply       # Ghi vào DB (cần confirm)
"""

import sys
import os
import re
import sqlite3
from pathlib import Path

# --- Thêm crawler vào path để import ---
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'crawler'))

DB_PATH = ROOT / 'prisma' / 'dev.db'

# --- Import sanitize logic từ crawler ---
# Tái tạo lại các pattern ở đây để script chạy độc lập (không phụ thuộc config)

_SENSITIVE_PATTERNS = [
    r'vòng\s*[123]\b',
    r'\b\d{2,3}\s*[-–]\s*\d{2,3}\s*[-–]\s*\d{2,3}\b',
    r'bộ ngực\s*(nảy nở|căng tròn|đầy đặn|to|khủng|gợi cảm)',
    r'(ngực|vòng 1)\s*(căng|nảy|đầy|trắng|hồng|mềm|tròn)',
    r'đùi\s*(trắng|thon|mềm|nõn|nuột)',
    r'mông\s*(tròn|đầy|căng|nảy)',
    r'eo\s*(thon|nhỏ|con kiến)\s*(gợi cảm|quyến rũ)',
    r'cơ thể\s*(gợi cảm|bốc lửa|khêu gợi|nóng bỏng|hoàn hảo)',
    r'thân hình\s*(gợi cảm|bốc lửa|khêu gợi|nóng bỏng|hoàn hảo)',
    r'nội\s*y\b',
    r'khỏa\s*thân|nude|18\s*\+|người lớn',
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

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.?!…])\s+|\n+')

_AUDIO_CTA_START_RE = re.compile(
    r'^(Hãy\s+nghe|Lắng\s+nghe|Nghe\s+tiếp|Nghe\s+truyện|Nghe\s+")',
    re.IGNORECASE,
)
_AUDIO_CTA_END_RE = re.compile(
    r'(để\s+biết\s+(thêm|chuyện\s+gì|câu\s+trả\s+lời|quyết\s+định|câu\s+chuyện)'
    r'|để\s+hiểu\s+rằng'
    r'|để\s+biết\b)[^.?!…]*[!.?…]*\s*$',
    re.IGNORECASE,
)
_AUDIO_CTA_FULL_RE = re.compile(
    r'^.{0,20}(Nghe|Lắng nghe|Hãy nghe)\s+".+?"\s+để\s+biết\b',
    re.IGNORECASE,
)

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f900-\U0001f9FF"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U0000200B-\U0000200F"
    "]+",
    re.UNICODE,
)

DESC_MAX_LEN = 200


def _is_audio_cta(sentence: str) -> bool:
    return bool(
        _AUDIO_CTA_START_RE.search(sentence)
        or _AUDIO_CTA_FULL_RE.search(sentence)
        or _AUDIO_CTA_END_RE.search(sentence)
    )


def _truncate_at_sentence(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    for sep in ['. ', '.\n', '.', '? ', '?', '! ', '!', '… ', '…']:
        pos = truncated.rfind(sep)
        if pos > max_len * 0.3:
            return truncated[:pos + len(sep)].rstrip()
    pos = truncated.rfind(' ')
    if pos > max_len * 0.3:
        return truncated[:pos].rstrip() + '…'
    return truncated.rstrip() + '…'


def sanitize_description(text: str) -> str:
    if not text:
        return text

    sentences = _SENTENCE_SPLIT_RE.split(text)
    clean = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if _SENSITIVE_RE.search(s):
            continue
        if _is_audio_cta(s):
            continue
        clean.append(s)

    result = ' '.join(clean)
    result = _EMOJI_RE.sub('', result)
    result = re.sub(r'\s+', ' ', result).strip()
    result = _truncate_at_sentence(result, DESC_MAX_LEN)
    return result


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('--dry-run', '--apply'):
        print("Usage:")
        print("  python scripts/normalize_descriptions.py --dry-run")
        print("  python scripts/normalize_descriptions.py --apply")
        sys.exit(1)

    mode = sys.argv[1]
    dry_run = mode == '--dry-run'

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT id, title, description FROM Novel ORDER BY title").fetchall()
    print(f"Tổng: {len(rows)} truyện\n")

    changes = []
    for row in rows:
        old_desc = row['description'] or ''
        new_desc = sanitize_description(old_desc)

        if old_desc != new_desc:
            changes.append({
                'id': row['id'],
                'title': row['title'],
                'old': old_desc,
                'new': new_desc,
            })

    if not changes:
        print("Không có thay đổi nào.")
        conn.close()
        return

    # In kết quả
    print(f"{'='*80}")
    print(f"  {len(changes)} truyện sẽ được cập nhật")
    print(f"{'='*80}\n")

    for i, c in enumerate(changes, 1):
        print(f"[{i}] {c['title']}")
        print(f"    ID:  {c['id']}")
        print(f"    CŨ:  {c['old'][:120]}{'...' if len(c['old']) > 120 else ''}")
        print(f"         ({len(c['old'])} ký tự)")
        print(f"    MỚI: {c['new'][:120]}{'...' if len(c['new']) > 120 else ''}")
        print(f"         ({len(c['new'])} ký tự)")
        print()

    print(f"{'='*80}")
    print(f"  Tổng: {len(changes)}/{len(rows)} truyện sẽ thay đổi")
    print(f"{'='*80}")

    if dry_run:
        print("\n  [DRY RUN] Không có gì được ghi vào DB.")
        print("  Chạy với --apply để cập nhật.\n")
        conn.close()
        return

    # --- Apply mode ---
    confirm = input("\n  Gõ 'confirm' để cập nhật DB: ").strip()
    if confirm != 'confirm':
        print("  Hủy. Không có gì thay đổi.")
        conn.close()
        return

    log_path = Path(__file__).resolve().parent / 'changes_log.txt'
    with open(log_path, 'w', encoding='utf-8') as log:
        log.write(f"normalize_descriptions — {len(changes)} changes\n")
        log.write(f"{'='*80}\n\n")

        for c in changes:
            conn.execute(
                "UPDATE Novel SET description = ? WHERE id = ?",
                (c['new'], c['id']),
            )
            log.write(f"ID: {c['id']}\n")
            log.write(f"Title: {c['title']}\n")
            log.write(f"OLD: {c['old']}\n")
            log.write(f"NEW: {c['new']}\n")
            log.write(f"{'-'*60}\n\n")

        conn.commit()

    print(f"\n  Đã cập nhật {len(changes)} truyện.")
    print(f"  Log: {log_path}")
    conn.close()


if __name__ == '__main__':
    main()
