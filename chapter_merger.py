"""chapter_merger.py — Gộp chương ngắn vào chương kế trước/sau.

Đối ngược với `chapter_splitter.py`: thay vì tách 1 chương dài thành nhiều
mảnh, merger ghép chương quá ngắn (< MIN_WORDS) vào chương liền kề để qua
ngưỡng audit AdSense (mặc định 300 từ).

Dùng:
    # Merge thủ công 1 chương vào chương trước nó
    python chapter_merger.py --slug "ten-truyen" --merge-into-prev 5

    # Merge vào chương kế tiếp (dùng khi chương 1 quá ngắn)
    python chapter_merger.py --slug "ten-truyen" --merge-into-next 1

    # Auto: scan toàn DB, gộp mọi chương < 300 từ
    python chapter_merger.py --auto-merge-short

    # Đặt ngưỡng riêng + giới hạn 5 truyện đầu để test
    python chapter_merger.py --auto-merge-short --min-words 400 --max-novels 5

    # Preview không ghi DB
    python chapter_merger.py --auto-merge-short --dry-run

Hành vi:
    - Backup DB tự động trước khi modify (skip với --no-backup)
    - Mặc định: renumber các chương sau khi merge để không có gap.
      Vd: gộp ch.5 vào ch.4 → ch.6 đổi thành ch.5, ch.7 → ch.6, ...
      Skip với --no-renumber (giữ gap).
    - Title chương đích giữ nguyên — content chương nguồn được append.
    - Bookmark/Comment/Rating ở Novel level — không bị ảnh hưởng.
    - ReadingProgress.chapterNumber có thể trỏ chương đã renumber → user
      thấy progress chuyển sang chương khác (chấp nhận được).

KHÔNG dùng cho:
    - Merge nhiều chương cùng lúc (tự loop từng pair)
    - Merge chương đã có audio (sẽ mất audioUrl reference)
"""

import argparse
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

MIN_WORDS_DEFAULT = 300


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _backup_db() -> str:
    from db_helper import get_db_path

    src = get_db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"DB không tồn tại: {src}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{src}.merge-bak.{ts}"
    shutil.copy2(src, dst)
    logger.info(f"💾 Backup DB → {dst}")
    return dst


def _fetch_chapter(conn, novel_id: str, number: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, number, title, content, wordCount, audioUrl FROM Chapter "
        "WHERE novelId=? AND number=?",
        (novel_id, number),
    ).fetchone()
    return dict(row) if row else None


def _merge_pair(
    conn,
    novel_id: str,
    source_num: int,
    target_num: int,
    *,
    dry_run: bool = False,
) -> Optional[dict]:
    """Merge content của chapter source vào chapter target. Delete source.

    Args:
        source_num: số chương sẽ bị xoá sau khi merge.
        target_num: số chương được giữ lại với content gộp.

    Returns:
        dict {source: int, target: int, new_word_count: int} hoặc None nếu fail.
    """
    if source_num == target_num:
        logger.error(f"  ❌ source == target ({source_num})")
        return None

    src = _fetch_chapter(conn, novel_id, source_num)
    tgt = _fetch_chapter(conn, novel_id, target_num)

    if not src:
        logger.error(f"  ❌ Không tìm thấy chương {source_num}")
        return None
    if not tgt:
        logger.error(f"  ❌ Không tìm thấy chương {target_num}")
        return None

    # Source-trước-target: source content đi trước → tgt.content = src + tgt
    # Source-sau-target: source content đi sau → tgt.content = tgt + src
    if source_num < target_num:
        new_content = src["content"].rstrip() + "\n\n" + tgt["content"].lstrip()
    else:
        new_content = tgt["content"].rstrip() + "\n\n" + src["content"].lstrip()

    new_wc = _count_words(new_content)

    logger.info(
        f"    ⤴️  Merge ch.{source_num} ({src['wordCount']} từ) → "
        f"ch.{target_num} ({tgt['wordCount']} → {new_wc} từ)"
    )

    if src.get("audioUrl"):
        logger.warning(f"    ⚠️ ch.{source_num} có audio — link sẽ mất")

    if dry_run:
        return {"source": source_num, "target": target_num,
                "new_word_count": new_wc, "dry_run": True}

    now_ms = int(time.time() * 1000)
    conn.execute(
        "UPDATE Chapter SET content=?, wordCount=?, updatedAt=? WHERE id=?",
        (new_content, new_wc, now_ms, tgt["id"]),
    )
    conn.execute("DELETE FROM Chapter WHERE id=?", (src["id"],))
    conn.commit()

    return {"source": source_num, "target": target_num,
            "new_word_count": new_wc}


def _renumber_chapters(conn, novel_id: str, *, dry_run: bool = False) -> int:
    """Renumber chương 1..N để lấp gap. Trả số chương được đổi number."""
    rows = conn.execute(
        "SELECT id, number FROM Chapter WHERE novelId=? ORDER BY number ASC",
        (novel_id,),
    ).fetchall()

    changed = 0
    now_ms = int(time.time() * 1000)

    # Pass 1: tránh xung đột unique([novelId, number]) bằng cách offset tạm
    if not dry_run:
        for r in rows:
            conn.execute(
                "UPDATE Chapter SET number=? WHERE id=?",
                (r["number"] + 100000, r["id"]),
            )

    # Pass 2: đặt số mới 1..N
    for new_num, r in enumerate(rows, start=1):
        if r["number"] != new_num:
            changed += 1
            if not dry_run:
                conn.execute(
                    "UPDATE Chapter SET number=?, updatedAt=? WHERE id=?",
                    (new_num, now_ms, r["id"]),
                )
        elif not dry_run:
            # Đã đúng nhưng vẫn cần restore từ offset
            conn.execute(
                "UPDATE Chapter SET number=? WHERE id=?",
                (new_num, r["id"]),
            )

    if not dry_run:
        conn.commit()
    return changed


def merge_into_prev(
    slug_keyword: str, source_num: int,
    *, renumber: bool = True, dry_run: bool = False,
) -> dict:
    """Merge chương source_num vào chương source_num - 1."""
    if source_num <= 1:
        logger.error(f"❌ ch.{source_num} không có chương trước để merge")
        return {"ok": False, "error": "no_prev"}

    return _merge_to_neighbor(slug_keyword, source_num, source_num - 1,
                               renumber=renumber, dry_run=dry_run)


def merge_into_next(
    slug_keyword: str, source_num: int,
    *, renumber: bool = True, dry_run: bool = False,
) -> dict:
    """Merge chương source_num vào chương source_num + 1."""
    return _merge_to_neighbor(slug_keyword, source_num, source_num + 1,
                               renumber=renumber, dry_run=dry_run)


def _merge_to_neighbor(
    slug_keyword: str, source_num: int, target_num: int,
    *, renumber: bool = True, dry_run: bool = False,
) -> dict:
    from db_helper import get_connection, get_novel_with_chapters

    conn = get_connection()
    try:
        novel, _ = get_novel_with_chapters(conn, slug_keyword)
        if not novel:
            logger.error(f"❌ Không tìm thấy truyện: {slug_keyword}")
            return {"ok": False, "error": "not_found"}

        logger.info(f"📖 {novel['title']} ({novel['slug']})")
        result = _merge_pair(conn, novel["id"], source_num, target_num,
                              dry_run=dry_run)
        if not result:
            return {"ok": False}

        if renumber and not dry_run:
            n = _renumber_chapters(conn, novel["id"])
            logger.info(f"  🔢 Renumber: {n} chương được đổi number")

        return {"ok": True, **result}
    finally:
        conn.close()


def auto_merge_short(
    *, min_words: int = MIN_WORDS_DEFAULT, max_novels: int = 0,
    renumber: bool = True, dry_run: bool = False,
) -> dict:
    """Scan toàn DB, gộp mọi chương < min_words với chương kế trước
    (hoặc kế sau nếu là chương đầu)."""
    from db_helper import get_connection

    conn = get_connection()
    try:
        # Tìm các (novel, chapter_number) ngắn
        rows = conn.execute("""
            SELECT n.id AS novel_id, n.slug, c.number, c.wordCount
            FROM Chapter c
            JOIN Novel n ON n.id = c.novelId
            WHERE c.publishStatus = 'published'
              AND n.publishStatus = 'published'
              AND c.wordCount < ?
            ORDER BY n.slug, c.number ASC
        """, (min_words,)).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.info(f"✅ Không có chương nào < {min_words} từ")
        return {"total": 0, "ok": 0, "failed": 0}

    # Group theo novel
    by_novel = {}
    for r in rows:
        by_novel.setdefault(r["slug"], []).append(dict(r))

    novels = list(by_novel.items())
    if max_novels > 0:
        novels = novels[:max_novels]

    logger.info(
        f"🔎 Tìm thấy {len(rows)} chương < {min_words} từ trong {len(by_novel)} truyện. "
        f"Xử lý {len(novels)} truyện.\n"
    )

    stats = {"total": 0, "ok": 0, "failed": 0, "details": []}

    conn = get_connection()
    try:
        for slug, shorts in novels:
            logger.info(f"━━━ {slug} ({len(shorts)} chương ngắn) ━━━")

            # Sort giảm dần để merge từ cuối lên (tránh đổi number trong vòng lặp)
            shorts_sorted = sorted(shorts, key=lambda x: -x["number"])

            for sh in shorts_sorted:
                novel_id = sh["novel_id"]
                source_num = sh["number"]

                # Quyết định merge prev hay next:
                # - Nếu là chương 1 → merge vào next
                # - Còn lại → merge vào prev
                target_num = source_num + 1 if source_num == 1 else source_num - 1

                # Verify target tồn tại (có thể đã bị merge ở vòng trước)
                tgt = conn.execute(
                    "SELECT 1 FROM Chapter WHERE novelId=? AND number=?",
                    (novel_id, target_num),
                ).fetchone()
                if not tgt:
                    logger.warning(
                        f"  ⚠️ ch.{source_num}: target ch.{target_num} không tồn tại, skip"
                    )
                    stats["failed"] += 1
                    continue

                stats["total"] += 1
                result = _merge_pair(conn, novel_id, source_num, target_num,
                                      dry_run=dry_run)
                if result:
                    stats["ok"] += 1
                    stats["details"].append({"slug": slug, **result})
                else:
                    stats["failed"] += 1

            if renumber and not dry_run:
                n = _renumber_chapters(conn, novel_id)
                if n:
                    logger.info(f"  🔢 Renumber: {n} chương")
    finally:
        conn.close()

    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Merge chương ngắn vào chương kế trước/sau."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--merge-into-prev", type=int, metavar="N",
                   help="Merge ch.N vào ch.N-1 (cần --slug)")
    g.add_argument("--merge-into-next", type=int, metavar="N",
                   help="Merge ch.N vào ch.N+1 (cần --slug)")
    g.add_argument("--auto-merge-short", action="store_true",
                   help="Scan DB, gộp mọi chương < min-words")

    ap.add_argument("--slug", help="Slug/title (cần với --merge-into-prev/next)")
    ap.add_argument("--min-words", type=int, default=MIN_WORDS_DEFAULT,
                    help=f"Ngưỡng chương ngắn (default {MIN_WORDS_DEFAULT})")
    ap.add_argument("--max-novels", type=int, default=0,
                    help="Giới hạn số truyện khi --auto-merge-short")
    ap.add_argument("--no-renumber", action="store_true",
                    help="Giữ gap số chương thay vì renumber 1..N")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")

    args = ap.parse_args()

    if (args.merge_into_prev or args.merge_into_next) and not args.slug:
        ap.error("--merge-into-prev/next cần --slug")

    if not args.dry_run and not args.no_backup:
        _backup_db()

    renumber = not args.no_renumber

    if args.merge_into_prev:
        result = merge_into_prev(args.slug, args.merge_into_prev,
                                  renumber=renumber, dry_run=args.dry_run)
        sys.exit(0 if result.get("ok") else 1)
    elif args.merge_into_next:
        result = merge_into_next(args.slug, args.merge_into_next,
                                  renumber=renumber, dry_run=args.dry_run)
        sys.exit(0 if result.get("ok") else 1)
    else:
        stats = auto_merge_short(
            min_words=args.min_words, max_novels=args.max_novels,
            renumber=renumber, dry_run=args.dry_run,
        )
        logger.info(
            f"\n📊 Tổng kết: {stats['ok']}/{stats['total']} OK, {stats['failed']} fail"
        )
        sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
