#!/usr/bin/env python3
"""
organize.py — Sắp xếp lại docx_output theo ngày tải về.

Trước:
  docx_output/
    ten-truyen-a/
    ten-truyen-b/
    ten-truyen-c/

Sau:
  docx_output/
    2026-03-24/
      ten-truyen-a/
      ten-truyen-b/
    2026-03-25/
      ten-truyen-c/

Cách dùng:
  python organize.py             # Preview — không di chuyển gì
  python organize.py --apply     # Thực sự di chuyển
  python organize.py --list      # Liệt kê theo ngày hiện tại
"""

import os
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DOCX_OUTPUT_DIR


def _is_date_dir(name: str) -> bool:
    """Kiểm tra thư mục có dạng YYYY-MM-DD không."""
    if len(name) != 10 or name[4] != '-' or name[7] != '-':
        return False
    try:
        datetime.strptime(name, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def _get_folder_date(folder_path: str) -> str:
    """Lấy ngày tạo/sửa của folder để sắp xếp."""
    stat = os.stat(folder_path)
    # Dùng mtime (ngày sửa cuối) — gần nhất với ngày crawl
    ts = stat.st_mtime
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')


def scan(output_dir: str) -> dict[str, list[str]]:
    """
    Quét tất cả folder truyện flat (không phải YYYY-MM-DD).
    Trả về dict {ngày: [slug1, slug2, ...]} đã sắp xếp.
    """
    if not os.path.isdir(output_dir):
        print(f"❌ Thư mục không tồn tại: {output_dir}")
        return {}

    by_date: dict[str, list[str]] = {}

    for entry in sorted(os.listdir(output_dir)):
        full = os.path.join(output_dir, entry)
        if not os.path.isdir(full):
            continue
        if _is_date_dir(entry):
            continue  # Bỏ qua thư mục đã có ngày

        date = _get_folder_date(full)
        by_date.setdefault(date, []).append(entry)

    return dict(sorted(by_date.items()))


def preview(output_dir: str):
    """Hiển thị kế hoạch sắp xếp mà không làm gì."""
    by_date = scan(output_dir)

    if not by_date:
        print("✅ Không có thư mục flat nào cần sắp xếp.")
        return

    total = sum(len(v) for v in by_date.values())
    print(f"\n📂 Sẽ sắp xếp {total} thư mục trong {output_dir}:\n")

    for date, slugs in by_date.items():
        print(f"  📅 {date}/  ({len(slugs)} truyện)")
        for slug in slugs:
            print(f"       {slug}/")
        print()

    print("👉 Chạy với --apply để thực hiện di chuyển.")


def apply(output_dir: str):
    """Thực sự di chuyển các folder vào thư mục ngày."""
    by_date = scan(output_dir)

    if not by_date:
        print("✅ Không có thư mục flat nào cần sắp xếp.")
        return

    moved = 0
    errors = 0

    for date, slugs in by_date.items():
        date_dir = os.path.join(output_dir, date)
        os.makedirs(date_dir, exist_ok=True)

        for slug in slugs:
            src = os.path.join(output_dir, slug)
            dst = os.path.join(date_dir, slug)

            if os.path.exists(dst):
                print(f"  ⚠️  {date}/{slug}/ đã tồn tại — bỏ qua")
                continue

            try:
                shutil.move(src, dst)
                print(f"  ✅  {slug}/ → {date}/{slug}/")
                moved += 1
            except Exception as e:
                print(f"  ❌  {slug}/: {e}")
                errors += 1

    print(f"\n{'='*50}")
    print(f"✅ Đã di chuyển: {moved} thư mục")
    if errors:
        print(f"❌ Lỗi: {errors} thư mục")


def list_by_date(output_dir: str):
    """Liệt kê toàn bộ cấu trúc hiện tại (cả flat + theo ngày)."""
    if not os.path.isdir(output_dir):
        print(f"❌ Thư mục không tồn tại: {output_dir}")
        return

    flat = []
    dated: dict[str, list[str]] = {}

    for entry in sorted(os.listdir(output_dir)):
        full = os.path.join(output_dir, entry)
        if not os.path.isdir(full):
            continue
        if _is_date_dir(entry):
            subs = sorted(os.listdir(full))
            dated[entry] = [s for s in subs if os.path.isdir(os.path.join(full, s))]
        else:
            flat.append(entry)

    print(f"\n📂 {output_dir}\n")

    if dated:
        for date in sorted(dated.keys(), reverse=True):
            slugs = dated[date]
            print(f"  📅 {date}/  ({len(slugs)} truyện)")
            for slug in slugs:
                print(f"       └─ {slug}/")
            print()

    if flat:
        print(f"  📁 Chưa sắp xếp ({len(flat)} thư mục):")
        for slug in flat:
            date = _get_folder_date(os.path.join(output_dir, slug))
            print(f"     {slug}/  [{date}]")

    total_novels = sum(len(v) for v in dated.values()) + len(flat)
    print(f"\n📊 Tổng: {total_novels} truyện trong {len(dated)} ngày")


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='Sắp xếp docx_output theo ngày tải về')
    p.add_argument('--apply',  action='store_true', help='Thực hiện di chuyển (mặc định: chỉ preview)')
    p.add_argument('--list',   action='store_true', help='Liệt kê cấu trúc hiện tại')
    p.add_argument('--dir',    default=DOCX_OUTPUT_DIR, help=f'Thư mục (mặc định: {DOCX_OUTPUT_DIR})')
    args = p.parse_args()

    if args.list:
        list_by_date(args.dir)
    elif args.apply:
        print(f"📂 Sắp xếp: {args.dir}\n")
        apply(args.dir)
        print()
        list_by_date(args.dir)
    else:
        preview(args.dir)
