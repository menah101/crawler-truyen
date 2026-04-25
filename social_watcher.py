#!/usr/bin/env python3
"""Social watcher — tự động đăng MXH khi có truyện mới publish.

Quét DB định kỳ tìm truyện có `publishStatus='published'` mới nổi chưa
đăng đầy đủ MXH (theo social_log.json), rồi gọi publish_to_all.

CLI:
    # Chạy 1 lần (suitable cho cron)
    python social_watcher.py --once

    # Daemon poll liên tục
    python social_watcher.py --interval 300

    # Force đăng lại 1 truyện (bỏ qua log)
    python social_watcher.py --force --slug ten-truyen

    # Giới hạn platform
    python social_watcher.py --once --only telegram,discord
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DOCX_OUTPUT_DIR  # noqa: E402
from social_publisher import (  # noqa: E402
    ADAPTERS,
    payload_from_db,
    payload_from_novel_dir,
    publish_to_all,
)
import social_log  # noqa: E402

logger = logging.getLogger(__name__)


def _find_novel_dir_by_slug(slug: str) -> str:
    """Tìm thư mục truyện đã crawl (docx_output/YYYY-MM-DD/<slug>)."""
    base = DOCX_OUTPUT_DIR
    if not os.path.isdir(base):
        return ''
    # Check flat (cũ): base/<slug>
    flat = os.path.join(base, slug)
    if os.path.isdir(flat):
        return flat
    # Check dated dirs: base/YYYY-MM-DD/<slug> (scan ngược từ mới nhất)
    for date_dir in sorted(os.listdir(base), reverse=True):
        p = os.path.join(base, date_dir, slug)
        if os.path.isdir(p):
            return p
    return ''


def _query_recent_novels(hours: int = 48) -> list[dict]:
    """Lấy truyện published trong N giờ qua."""
    from db_helper import get_connection

    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT slug, title, createdAt FROM Novel '
            "WHERE publishStatus = 'published' AND createdAt >= ? "
            'ORDER BY createdAt DESC',
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _configured_platforms() -> set[str]:
    """Các adapter đã có đủ env — sẽ thực sự đăng."""
    return {cls().name for cls in ADAPTERS if cls().is_configured()}


def process_slug(
    slug: str,
    *,
    only: Optional[list[str]] = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Đăng 1 truyện. Skip platform đã đăng OK trừ khi `force`."""
    novel_dir = _find_novel_dir_by_slug(slug)

    # Ưu tiên seo.txt nếu có; fallback DB
    payload = None
    if novel_dir and os.path.exists(os.path.join(novel_dir, 'seo.txt')):
        payload = payload_from_novel_dir(novel_dir)
    if payload is None or not payload.title:
        payload = payload_from_db(slug, novel_dir=novel_dir)

    if payload is None:
        logger.error(f'❌ {slug}: không build được payload (không có DB row + không có seo.txt)')
        return {'slug': slug, 'error': 'no payload'}

    # Lọc platform: bỏ các platform đã đăng OK trừ khi force
    configured = _configured_platforms()
    if only:
        configured &= set(only)

    if not force:
        already = social_log.posted_platforms(slug)
        todo = sorted(configured - already)
    else:
        todo = sorted(configured)

    if not todo:
        logger.info(f'⏭️  {slug}: đã đăng đủ tất cả platform đã cấu hình')
        return {'slug': slug, 'skipped': True}

    logger.info(f'📣 {slug}: đăng lên {todo}')
    results = publish_to_all(payload, only=todo, dry_run=dry_run)

    # Log kết quả (kể cả dry_run không ghi)
    if not dry_run:
        for platform, result in results.items():
            social_log.mark(slug, platform, result)

    return {'slug': slug, 'results': results}


def watch_once(
    *,
    hours: int = 48,
    only: Optional[list[str]] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Quét 1 lần, đăng các truyện chưa đăng đủ."""
    novels = _query_recent_novels(hours=hours)
    if not novels:
        logger.info(f'🔍 Không có truyện published trong {hours}h qua')
        return []

    logger.info(f'🔍 Tìm thấy {len(novels)} truyện published trong {hours}h qua')
    out = []
    for novel in novels:
        slug = novel['slug']
        try:
            out.append(process_slug(slug, only=only, dry_run=dry_run))
        except Exception as e:
            logger.exception(f'❌ {slug}: lỗi không xử lý được — {e}')
            out.append({'slug': slug, 'error': str(e)})
    return out


def watch_forever(
    *,
    interval: int = 300,
    hours: int = 48,
    only: Optional[list[str]] = None,
) -> None:
    """Daemon: poll mỗi `interval` giây."""
    logger.info(f'🔁 Watcher start: poll mỗi {interval}s, quét truyện trong {hours}h qua')
    while True:
        try:
            watch_once(hours=hours, only=only)
        except Exception as e:
            logger.exception(f'❌ Vòng poll lỗi: {e}')
        time.sleep(interval)


def _cli():
    ap = argparse.ArgumentParser(description='Auto-đăng MXH khi có truyện mới')
    ap.add_argument('--once', action='store_true', help='Chạy 1 lần rồi thoát (cho cron)')
    ap.add_argument('--interval', type=int, default=300,
                    help='Giây giữa các lần poll (mặc định: 300 = 5 phút)')
    ap.add_argument('--hours', type=int, default=48,
                    help='Chỉ xét truyện published trong N giờ qua (mặc định: 48)')
    ap.add_argument('--slug', type=str, default='',
                    help='Đăng 1 truyện cụ thể (bỏ qua query DB)')
    ap.add_argument('--force', action='store_true',
                    help='Bỏ qua social_log.json, đăng lại kể cả đã đăng')
    ap.add_argument('--only', type=str, default='',
                    help='Giới hạn platform (VD: --only telegram,discord)')
    ap.add_argument('--dry-run', action='store_true', help='Không đăng thật')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )

    only = [x.strip() for x in args.only.split(',') if x.strip()] or None

    if args.slug:
        r = process_slug(args.slug, only=only, force=args.force, dry_run=args.dry_run)
        print(r)
        return

    if args.once:
        watch_once(hours=args.hours, only=only, dry_run=args.dry_run)
        return

    watch_forever(interval=args.interval, hours=args.hours, only=only)


if __name__ == '__main__':
    _cli()
