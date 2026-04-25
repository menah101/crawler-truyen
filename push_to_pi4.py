"""push_to_pi4.py — Push novel từ local DB lên pi4 qua /api/admin/import.

Dùng khi crawler chạy IMPORT_MODE=local (ghi local trước) và muốn sync
truyện mới lên pi4 sau đó. Endpoint idempotent: novel đã tồn tại sẽ được
"resumed" (chỉ thêm chương mới).

Khác `wrapper_sync.py`:
- wrapper_sync → /api/admin/wrappers (chỉ update 6 cột editorial)
- push_to_pi4  → /api/admin/import (TẠO novel + chapter mới)

Dùng:
    # Push 1 truyện
    python push_to_pi4.py --slug "ten-truyen"

    # Push nhiều
    python push_to_pi4.py --slugs ten-truyen-1 ten-truyen-2 ...

    # Push tất cả novel mới crawl trong N giờ qua
    python push_to_pi4.py --since-hours 24

    # Push toàn bộ DB (cẩn thận — payload to)
    python push_to_pi4.py --all

    # Dry-run xem sẽ push gì
    python push_to_pi4.py --since-hours 24 --dry-run
"""

import argparse
import logging
import sys
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def _fetch_novel(conn, slug: str):
    """Lấy 1 novel + chapters từ local DB."""
    novel = conn.execute("""
        SELECT id, slug, title, author, description,
               coverImage, genres, tags, status, sourceUrl
        FROM Novel
        WHERE slug = ?
    """, (slug,)).fetchone()
    if not novel:
        return None, []

    chapters = conn.execute("""
        SELECT number, title, content
        FROM Chapter
        WHERE novelId = ? AND publishStatus = 'published'
        ORDER BY number ASC
    """, (novel['id'],)).fetchall()

    return dict(novel), [dict(c) for c in chapters]


def _build_payload(novel: dict) -> dict:
    """Build novel_data theo định dạng /api/admin/import yêu cầu."""
    return {
        'title':       novel['title'],
        'author':      novel.get('author', '') or 'Đang cập nhật',
        'description': novel.get('description', '') or '',
        'genres':      novel.get('genres', '') or 'ngon-tinh',
        'tags':        novel.get('tags', '') or '',
        'status':      novel.get('status', '') or 'completed',
        'source_url':  (novel.get('sourceUrl', '') or '').rstrip('/'),
        'cover_image': novel.get('coverImage', '') or '',
    }


def push_slugs(slugs: list, *, dry_run: bool = False, sleep_sec: float = 1.0) -> dict:
    """Push danh sách slug lên pi4. Trả stats."""
    from db_helper import get_connection
    from api_client import import_novel

    conn = get_connection()
    try:
        stats = {'ok': 0, 'failed': 0, 'skipped': 0,
                 'novels_inserted': 0, 'chapters_inserted': 0,
                 'novels_resumed': 0, 'details': []}

        total = len(slugs)
        for i, slug in enumerate(slugs, 1):
            novel, chapters = _fetch_novel(conn, slug)
            if not novel:
                logger.warning(f"[{i}/{total}] ⚠️  {slug}: không có trong local DB, skip")
                stats['skipped'] += 1
                continue

            n_chapters = len(chapters)
            logger.info(f"[{i}/{total}] 📤 {slug} ({n_chapters} chương)")

            if dry_run:
                logger.info(f"   🔍 DRY-RUN — không gọi API")
                stats['details'].append({'slug': slug, 'dry_run': True, 'chapters': n_chapters})
                continue

            try:
                payload = _build_payload(novel)
                result = import_novel(payload, chapters)
                inserted = result.get('inserted', 0)
                note = result.get('note', '')
                if note == 'novel_resumed':
                    logger.info(f"   📗 Resumed (novel đã có) — +{inserted} chương mới")
                    stats['novels_resumed'] += 1
                else:
                    logger.info(f"   ✨ Created — {inserted} chương")
                    stats['novels_inserted'] += 1
                stats['chapters_inserted'] += inserted
                stats['ok'] += 1
                stats['details'].append({'slug': slug, 'inserted': inserted, 'note': note})
            except Exception as e:
                logger.error(f"   ❌ Fail: {str(e)[:200]}")
                stats['failed'] += 1
                stats['details'].append({'slug': slug, 'error': str(e)[:200]})

            if sleep_sec and i < total:
                time.sleep(sleep_sec)

        return stats
    finally:
        conn.close()


def find_recent_slugs(hours: int) -> list:
    """Tìm novels có chapter được tạo trong N giờ qua."""
    from db_helper import get_connection
    conn = get_connection()
    try:
        cutoff_ms = int((time.time() - hours * 3600) * 1000)
        rows = conn.execute("""
            SELECT DISTINCT n.slug
            FROM Novel n
            JOIN Chapter c ON c.novelId = n.id
            WHERE c.createdAt > ?
            ORDER BY n.slug
        """, (cutoff_ms,)).fetchall()
        return [r['slug'] for r in rows]
    finally:
        conn.close()


def find_all_slugs() -> list:
    """Tất cả published novels."""
    from db_helper import get_connection
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT slug FROM Novel
            WHERE publishStatus = 'published'
            ORDER BY slug
        """).fetchall()
        return [r['slug'] for r in rows]
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Push novel local → pi4 qua /api/admin/import")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="1 slug")
    g.add_argument("--slugs", nargs='+', help="nhiều slug, cách nhau bằng space")
    g.add_argument("--since-hours", type=int, help="push novel có chapter mới trong N giờ qua")
    g.add_argument("--all", action="store_true", help="push toàn bộ published novels")

    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="delay giữa các request (giây, default 1.0)")
    args = ap.parse_args()

    if args.slug:
        slugs = [args.slug]
    elif args.slugs:
        slugs = args.slugs
    elif args.since_hours:
        slugs = find_recent_slugs(args.since_hours)
        logger.info(f"🔎 Tìm thấy {len(slugs)} novel có chapter mới trong {args.since_hours}h qua\n")
    else:
        slugs = find_all_slugs()
        logger.info(f"🔎 Tìm thấy {len(slugs)} published novels\n")

    if not slugs:
        logger.info("(không có gì để push)")
        sys.exit(0)

    stats = push_slugs(slugs, dry_run=args.dry_run, sleep_sec=args.sleep)
    logger.info(
        f"\n📊 Tổng kết: {stats['ok']} OK | {stats['skipped']} skip | "
        f"{stats['failed']} fail | "
        f"+{stats['chapters_inserted']} chương ({stats['novels_inserted']} mới, "
        f"{stats['novels_resumed']} resumed)"
    )
    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
