#!/usr/bin/env python3
"""Rewrite lại nội dung từng chương từ thư mục chapters/*.json đã có.

Đọc file JSON dạng `{"number": N, "title": "...", "content": "..."}`,
gọi `rewrite_chapter()` rồi ghi lại. Trước khi ghi đè, toàn bộ thư mục gốc
được sao lưu sang `chapters_backup_<timestamp>/`.

CLI:
    python chapter_rewriter.py <chapters_dir> [--chapter N ...] [--no-backup]
    python chapter_rewriter.py <novel_dir>    # tự thêm /chapters
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rewriter import rewrite_chapter, split_paragraphs  # noqa: E402

logger = logging.getLogger(__name__)


def _resolve_chapters_dir(path: str) -> str:
    path = os.path.abspath(path)
    if os.path.basename(path.rstrip('/')) != 'chapters':
        candidate = os.path.join(path, 'chapters')
        if os.path.isdir(candidate):
            return candidate
    return path


def _load_novel_title(chapters_dir: str) -> str:
    novel_dir = os.path.dirname(chapters_dir)
    seo_path = os.path.join(novel_dir, 'seo.txt')
    if os.path.exists(seo_path):
        try:
            with open(seo_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('=') and not line.startswith('#'):
                        return line
        except Exception:
            pass
    return os.path.basename(novel_dir).replace('-', ' ').title()


def _backup(chapters_dir: str) -> str:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    parent = os.path.dirname(chapters_dir)
    backup_dir = os.path.join(parent, f'chapters_backup_{ts}')
    shutil.copytree(chapters_dir, backup_dir)
    return backup_dir


def rewrite_chapters_dir(
    chapters_dir: str,
    *,
    only_numbers: set[int] | None = None,
    backup: bool = True,
    novel_title: str = '',
) -> dict:
    """Rewrite toàn bộ (hoặc tập con) file JSON trong chapters_dir.

    Trả về dict thống kê: {total, rewritten, skipped, failed, backup_dir}.
    """
    chapters_dir = _resolve_chapters_dir(chapters_dir)
    if not os.path.isdir(chapters_dir):
        raise FileNotFoundError(f'Không tìm thấy thư mục chapters: {chapters_dir}')

    files = sorted(glob.glob(os.path.join(chapters_dir, '*.json')))
    if not files:
        raise FileNotFoundError(f'Không có file JSON nào trong {chapters_dir}')

    if not novel_title:
        novel_title = _load_novel_title(chapters_dir)

    backup_dir = _backup(chapters_dir) if backup else ''
    if backup_dir:
        logger.info(f'💾 Backup: {backup_dir}')

    stats = {
        'total': len(files),
        'rewritten': 0,
        'skipped': 0,
        'failed': 0,
        'backup_dir': backup_dir,
    }

    for path in files:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f'❌ {os.path.basename(path)}: lỗi đọc JSON ({e})')
            stats['failed'] += 1
            continue

        number = data.get('number')
        if only_numbers is not None and number not in only_numbers:
            stats['skipped'] += 1
            continue

        content = data.get('content', '')
        if not content or len(content) < 100:
            logger.warning(f'⚠️  Chương {number}: content quá ngắn, bỏ qua')
            stats['skipped'] += 1
            continue

        title = data.get('title', f'Chương {number}')
        logger.info(f'✍️  Chương {number} — {title} ({len(content)} ký tự)')

        try:
            new_content = rewrite_chapter(content, novel_title=novel_title)
        except Exception as e:
            logger.error(f'❌ Chương {number}: rewrite lỗi ({e}) — fallback split_paragraphs')
            try:
                new_content = split_paragraphs(content)
            except Exception:
                new_content = content
            stats['failed'] += 1

        data['content'] = new_content
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        stats['rewritten'] += 1

    return stats


def _cli():
    ap = argparse.ArgumentParser(description='Rewrite chapters/*.json tại chỗ')
    ap.add_argument('chapters_dir', help='Thư mục chapters/ (hoặc thư mục truyện chứa chapters/)')
    ap.add_argument('--chapter', type=int, nargs='+', metavar='N',
                    help='Chỉ rewrite các số chương cụ thể (VD: --chapter 1 3)')
    ap.add_argument('--no-backup', action='store_true', help='Bỏ qua bước backup')
    ap.add_argument('--title', type=str, default='', help='Tên truyện (override seo.txt)')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )

    only = set(args.chapter) if args.chapter else None
    stats = rewrite_chapters_dir(
        args.chapters_dir,
        only_numbers=only,
        backup=not args.no_backup,
        novel_title=args.title,
    )

    print()
    print(f"📊 Tổng kết:")
    print(f"   Tổng số file : {stats['total']}")
    print(f"   Đã rewrite   : {stats['rewritten']}")
    print(f"   Bỏ qua       : {stats['skipped']}")
    print(f"   Lỗi          : {stats['failed']}")
    if stats['backup_dir']:
        print(f"   Backup       : {stats['backup_dir']}")


if __name__ == '__main__':
    _cli()
