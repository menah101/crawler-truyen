"""
watchlist.py — Theo dõi nguồn truyện, phát hiện chương mới.

Cấu trúc watchlist.json:
{
  "novels": [
    {
      "url": "https://...",
      "title": "Tên truyện",
      "source": "truyenfull",
      "known_chapters": 150,       // số chương đã biết (để so sánh)
      "last_chapter_num": 150,     // số chương cao nhất đã biết
      "last_checked": "2026-03-20T10:00:00",
      "added_at": "2026-03-01T08:00:00",
      "new_chapters": []           // chương mới phát hiện, chưa download
    }
  ]
}
"""

import json
import os
import re
from datetime import datetime

WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watchlist.json')


def _load() -> dict:
    if os.path.exists(WATCHLIST_PATH):
        with open(WATCHLIST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'novels': []}


def _save(data: dict):
    with open(WATCHLIST_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def _find(data: dict, url: str) -> int:
    """Trả về index của novel trong list, hoặc -1 nếu không tìm thấy."""
    url = url.rstrip('/')
    for i, n in enumerate(data['novels']):
        if n['url'].rstrip('/') == url:
            return i
    return -1


def _extract_chapter_numbers(chapter_urls: list) -> list[int]:
    """Trích xuất số chương từ danh sách URL."""
    nums = []
    for i, url in enumerate(chapter_urls):
        m = re.search(r'chuong[- ]?(\d+)', url) or re.search(r'chapter[- ]?(\d+)', url)
        nums.append(int(m.group(1)) if m else i + 1)
    return nums


# ──────────────────────────────────────────
# Public API
# ──────────────────────────────────────────

def watch_add(url: str, source_name: str) -> dict:
    """
    Thêm một truyện vào watchlist.
    Fetch info + danh sách chương hiện tại để ghi baseline.
    Trả về entry đã lưu.
    """
    from sources import get_source, get_source_for_url

    url = url.rstrip('/')
    data = _load()

    if _find(data, url) >= 0:
        raise ValueError(f"Truyện đã có trong watchlist: {url}")

    # Auto-detect source
    try:
        src = get_source_for_url(url)
        source_name = src.name
    except ValueError:
        src = get_source(source_name)

    print(f"⏳ Đang lấy thông tin truyện từ {src.label}...")
    info = src.get_novel_info(url)
    title = info.get('title', url) if info else url

    print(f"⏳ Đang lấy danh sách chương...")
    chapter_urls = src.get_chapter_urls(url) or []
    chapter_nums = _extract_chapter_numbers(chapter_urls)
    known = len(chapter_nums)
    last_num = max(chapter_nums) if chapter_nums else 0

    entry = {
        'url': url,
        'title': title,
        'source': source_name,
        'known_chapters': known,
        'last_chapter_num': last_num,
        'last_checked': _now(),
        'added_at': _now(),
        'new_chapters': [],
    }
    data['novels'].append(entry)
    _save(data)
    print(f"✅ Đã thêm: {title} ({known} chương, chương cuối: {last_num})")
    return entry


def watch_remove(url: str):
    """Xóa truyện khỏi watchlist theo URL."""
    data = _load()
    idx = _find(data, url.rstrip('/'))
    if idx < 0:
        raise ValueError(f"Không tìm thấy trong watchlist: {url}")
    removed = data['novels'].pop(idx)
    _save(data)
    print(f"🗑️  Đã xóa: {removed['title']}")


def watch_list() -> list:
    """In và trả về danh sách truyện đang theo dõi."""
    data = _load()
    novels = data['novels']
    if not novels:
        print("📭 Watchlist trống.")
        return []

    print(f"\n{'─'*60}")
    print(f"{'#':<4} {'Tiêu đề':<30} {'Nguồn':<14} {'Chương':<8} {'Mới':<5} {'Check lần cuối'}")
    print(f"{'─'*60}")
    for i, n in enumerate(novels, 1):
        new_count = len(n.get('new_chapters', []))
        new_label = f"🆕{new_count}" if new_count else '—'
        checked = n.get('last_checked', '')[:16].replace('T', ' ')
        print(f"{i:<4} {n['title'][:29]:<30} {n['source']:<14} {n['known_chapters']:<8} {new_label:<5} {checked}")
    print(f"{'─'*60}")
    print(f"Tổng: {len(novels)} truyện\n")
    return novels


def watch_check(verbose=True) -> list:
    """
    Kiểm tra tất cả truyện trong watchlist.
    Trả về list các entry có chương mới.
    """
    from sources import get_source, get_source_for_url

    data = _load()
    if not data['novels']:
        print("📭 Watchlist trống.")
        return []

    updated = []
    print(f"\n🔍 Đang kiểm tra {len(data['novels'])} truyện...\n")

    for i, entry in enumerate(data['novels']):
        url    = entry['url']
        title  = entry['title']
        source = entry['source']

        print(f"  [{i+1}/{len(data['novels'])}] {title}", end=' ... ', flush=True)

        try:
            try:
                src = get_source_for_url(url)
            except ValueError:
                src = get_source(source)

            chapter_urls = src.get_chapter_urls(url) or []
            chapter_nums = _extract_chapter_numbers(chapter_urls)

            # Chương mới = số chương có số lớn hơn last_chapter_num
            last_known = entry.get('last_chapter_num', entry.get('known_chapters', 0))
            new_nums = sorted(n for n in chapter_nums if n > last_known)

            entry['last_checked'] = _now()

            if new_nums:
                entry['new_chapters'] = new_nums
                entry['known_chapters'] = len(chapter_nums)
                print(f"🆕 {len(new_nums)} chương mới: {new_nums[:5]}{'...' if len(new_nums) > 5 else ''}")
                updated.append(entry)
            else:
                entry['new_chapters'] = []
                entry['known_chapters'] = len(chapter_nums)
                print(f"✓ Đã cập nhật ({len(chapter_nums)} chương)")

        except Exception as e:
            print(f"❌ Lỗi: {e}")

    _save(data)
    print(f"\n{'─'*40}")
    if updated:
        print(f"🆕 {len(updated)} truyện có chương mới:")
        for n in updated:
            print(f"   • {n['title']} — {len(n['new_chapters'])} chương: {n['new_chapters'][:5]}")
    else:
        print("✅ Không có chương mới.")
    print(f"{'─'*40}\n")

    return updated


def watch_download(url_filter: str = None) -> list:
    """
    Download chương mới cho tất cả (hoặc 1 URL cụ thể) trong watchlist.
    Sau khi download, xóa new_chapters và cập nhật last_chapter_num.
    Trả về list chapter_filter đã dùng.
    """
    data = _load()
    novels = data['novels']

    if url_filter:
        idx = _find(data, url_filter.rstrip('/'))
        if idx < 0:
            raise ValueError(f"Không tìm thấy trong watchlist: {url_filter}")
        novels = [data['novels'][idx]]

    targets = [n for n in novels if n.get('new_chapters')]
    if not targets:
        print("✅ Không có chương mới cần download.")
        return []

    print(f"\n📥 Sẽ download chương mới cho {len(targets)} truyện:\n")
    for n in targets:
        print(f"  • {n['title']}: chương {n['new_chapters']}")

    confirm = input("\nXác nhận download? [Y/n] ").strip().lower()
    if confirm == 'n':
        print("❌ Hủy.")
        return []

    return targets


def mark_downloaded(url: str, downloaded_chapters: list[int]):
    """
    Gọi sau khi download xong để cập nhật last_chapter_num và xóa new_chapters.
    """
    data = _load()
    idx = _find(data, url.rstrip('/'))
    if idx < 0:
        return
    entry = data['novels'][idx]
    all_known = sorted(set(downloaded_chapters))
    if all_known:
        entry['last_chapter_num'] = max(all_known)
    entry['new_chapters'] = []
    _save(data)
