"""Tra slug Novel.sourceUrl từ DB an toàn (parameter binding).

Dùng từ shell scripts để tránh interpolate URL trực tiếp vào sqlite3 SQL —
URL chứa dấu nháy đơn / `;` có thể inject SQL hoặc command.

Usage:
    python3 tools/slug_from_url.py "https://example.com/truyen/abc/"

In ra slug (1 dòng) hoặc rỗng nếu không tìm thấy. Exit 0 cả 2 trường hợp;
exit != 0 chỉ khi DB lỗi.
"""
from __future__ import annotations

import os
import sqlite3
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: slug_from_url.py <url>", file=sys.stderr)
        return 2
    url = sys.argv[1].rstrip("/")

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.environ.get("DB_PATH") or os.path.join(here, "..", "prisma", "dev.db")
    if not os.path.exists(db_path):
        print(f"DB không tồn tại: {db_path}", file=sys.stderr)
        return 3

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT slug FROM Novel WHERE sourceUrl = ? LIMIT 1",
            (url,),
        ).fetchone()
        if row:
            print(row[0])
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
