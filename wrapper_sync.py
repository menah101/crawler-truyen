"""Wrapper Sync — đẩy editorial wrappers từ DB local lên pi4 qua HTTP.

Cho phép chạy crawler + LLM wrappers ở máy local, rồi đồng bộ kết quả lên DB
production (pi4) qua endpoint `/api/admin/wrappers` mà không cần SSH hay rsync.

Chỉ đụng 6 cột — an toàn với bookmark/comment/rating của user.

Dùng:
    # Đẩy tất cả wrapper hiện có trong DB local
    python wrapper_sync.py --all

    # Đẩy 1 truyện
    python wrapper_sync.py --slug "ten truyen"

    # Chỉ đẩy novel (bỏ chapter)
    python wrapper_sync.py --all --novels-only

    # Dry-run — in payload mà không gọi API
    python wrapper_sync.py --all --dry-run

    # Batch size (default 100)
    python wrapper_sync.py --all --batch 50

Env:
    API_BASE_URL    — URL pi4, ví dụ http://192.168.1.50:3000
    IMPORT_SECRET   — trùng với IMPORT_SECRET trong .env.local pi4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_helper import get_connection

logger = logging.getLogger(__name__)


def _chunk(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def collect_novels(slug_filter: str | None = None) -> list[dict]:
    """Lấy novels từ DB local mà có ít nhất 1 field wrapper."""
    conn = get_connection()
    cur  = conn.cursor()
    sql  = """
        SELECT slug, editorialReview, characterAnalysis, faq
        FROM Novel
        WHERE ((editorialReview IS NOT NULL AND editorialReview != '')
            OR (characterAnalysis IS NOT NULL AND characterAnalysis != '')
            OR (faq IS NOT NULL AND faq != ''))
    """
    if slug_filter:
        sql += " AND slug LIKE ?"
        rows = cur.execute(sql, (f"%{slug_filter}%",)).fetchall()
    else:
        rows = cur.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def collect_chapters(slug_filter: str | None = None) -> list[dict]:
    """Lấy chapters có ít nhất 1 field wrapper. Kèm novelSlug để match."""
    conn = get_connection()
    cur  = conn.cursor()
    sql  = """
        SELECT n.slug AS novelSlug, c.number, c.summary, c.highlight, c.nextPreview
        FROM Chapter c
        JOIN Novel n ON n.id = c.novelId
        WHERE ((c.summary IS NOT NULL AND c.summary != '')
            OR (c.highlight IS NOT NULL AND c.highlight != '')
            OR (c.nextPreview IS NOT NULL AND c.nextPreview != ''))
    """
    if slug_filter:
        sql += " AND n.slug LIKE ?"
        rows = cur.execute(sql, (f"%{slug_filter}%",)).fetchall()
    else:
        rows = cur.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def push_batch(novels: list[dict], chapters: list[dict], *,
               dry_run: bool = False) -> dict:
    """POST 1 batch tới /api/admin/wrappers. Trả về response JSON của pi4."""
    from config import API_BASE_URL, API_SECRET

    if not API_BASE_URL:
        raise RuntimeError("❌ API_BASE_URL chưa được set trong env")
    if not API_SECRET:
        raise RuntimeError("❌ IMPORT_SECRET chưa được set trong env")

    endpoint = f"{API_BASE_URL.rstrip('/')}/api/admin/wrappers"
    payload  = {"novels": novels, "chapters": chapters}

    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
        return {"dryRun": True, "novels": len(novels), "chapters": len(chapters)}

    try:
        import requests
    except ImportError:
        raise RuntimeError("❌ Thiếu 'requests'. Chạy: pip install requests")

    resp = requests.post(
        endpoint,
        json=payload,
        headers={
            "Content-Type":    "application/json",
            "X-Import-Secret": API_SECRET,
        },
        timeout=120,
    )
    if resp.status_code == 401:
        raise RuntimeError(
            "❌ Sai IMPORT_SECRET — kiểm tra .env local và .env.local trên pi4"
        )
    if not resp.ok:
        raise RuntimeError(f"❌ {resp.status_code} {resp.text[:300]}")
    return resp.json()


def sync(*, slug: str | None, novels_only: bool, chapters_only: bool,
         batch_size: int, dry_run: bool) -> dict:
    novels   = [] if chapters_only else collect_novels(slug)
    chapters = [] if novels_only   else collect_chapters(slug)

    print(f"📦 Local có {len(novels)} novel + {len(chapters)} chapter wrapper")
    if slug: print(f"   (filter slug LIKE '%{slug}%')")
    if not novels and not chapters:
        print("Không có gì để sync."); return {}

    totals = {"novels": 0, "chapters": 0,
              "novelsNotFound": [], "chaptersNotFound": []}

    # Push novels 1 batch (thường ít), rồi chia chapters theo batch
    if novels:
        print(f"→ Push {len(novels)} novel…")
        r = push_batch(novels, [], dry_run=dry_run)
        if not dry_run:
            totals["novels"]         += r.get("novels", {}).get("updated", 0)
            totals["novelsNotFound"] += r.get("novels", {}).get("notFound", [])

    for i, batch in enumerate(_chunk(chapters, batch_size), 1):
        print(f"→ Push chapter batch {i} ({len(batch)} chương)…")
        r = push_batch([], batch, dry_run=dry_run)
        if not dry_run:
            totals["chapters"]         += r.get("chapters", {}).get("updated", 0)
            totals["chaptersNotFound"] += r.get("chapters", {}).get("notFound", [])

    print("\n✅ Kết quả sync:")
    print(f"   Novel updated:   {totals['novels']}")
    print(f"   Chapter updated: {totals['chapters']}")
    if totals["novelsNotFound"]:
        print(f"   ⚠️  Novel không tìm thấy trên pi4: {totals['novelsNotFound']}")
    if totals["chaptersNotFound"]:
        print(f"   ⚠️  Chapter không tìm thấy: {len(totals['chaptersNotFound'])} mục")
        for x in totals["chaptersNotFound"][:10]:
            print(f"       - {x}")
    return totals


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Sync wrappers local → pi4 via HTTP")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all",  action="store_true",  help="Sync mọi wrapper có trong local DB")
    grp.add_argument("--slug", type=str, help="Chỉ sync novel (+ chapter) có slug match LIKE")

    ap.add_argument("--novels-only",   action="store_true", help="Bỏ qua chapter wrappers")
    ap.add_argument("--chapters-only", action="store_true", help="Bỏ qua novel wrappers")
    ap.add_argument("--batch", type=int, default=100, help="Chapter batch size (default 100)")
    ap.add_argument("--dry-run", action="store_true", help="In payload, không gọi API")
    args = ap.parse_args()

    if args.novels_only and args.chapters_only:
        ap.error("--novels-only và --chapters-only không thể dùng cùng lúc")

    sync(
        slug=args.slug,
        novels_only=args.novels_only,
        chapters_only=args.chapters_only,
        batch_size=args.batch,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
