"""
Database helper — đọc/ghi SQLite trực tiếp.
"""

import sqlite3
import os
import re
import random
import string
import time
from datetime import datetime


def get_db_path():
    from config import DB_PATH
    path = os.path.abspath(DB_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Database không tìm thấy: {path}\nChạy 'pnpm db:push' trước.")
    return path


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def generate_cuid():
    chars = string.ascii_lowercase + string.digits
    return f"c{hex(int(time.time() * 1000))[2:]}{''.join(random.choices(chars, k=12))}"


def slugify(text):
    import unicodedata
    text = unicodedata.normalize('NFD', text)
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = text.lower().replace('đ', 'd').replace('Đ', 'D')
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')


def clean_text(text):
    if not text:
        return text
    text = text.replace('\x00', '')
    try:
        if any(c in text for c in ['Ä', 'á»', 'áº', 'Ã']):
            fixed = text.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
            if fixed and len(fixed) > len(text) * 0.3:
                return fixed
    except Exception:
        pass
    return text


def novel_exists(conn, slug=None, title=None, source_url=None):
    if source_url:
        row = conn.execute("SELECT id FROM Novel WHERE sourceUrl = ?", (source_url.rstrip('/'),)).fetchone()
        if row: return row['id']
    if slug:
        row = conn.execute("SELECT id FROM Novel WHERE slug = ?", (slug,)).fetchone()
        if row: return row['id']
    if title:
        row = conn.execute("SELECT id FROM Novel WHERE title = ?", (title,)).fetchone()
        if row: return row['id']
    return None


def chapter_exists(conn, novel_id, chapter_number):
    row = conn.execute("SELECT id FROM Chapter WHERE novelId = ? AND number = ?", (novel_id, chapter_number)).fetchone()
    return row['id'] if row else None


def get_novel_with_chapters(conn, keyword: str):
    """
    Tìm truyện theo tên, slug hoặc id (khớp một phần).
    Trả về (novel_dict, chapters_list) hoặc (None, []) nếu không tìm thấy.
    chapters_list đã sort theo số chương.
    """
    kw = keyword.strip()
    novel = conn.execute("""
        SELECT id, title, author, slug FROM Novel
        WHERE id = ? OR slug = ? OR title LIKE ?
        LIMIT 1
    """, (kw, kw, f'%{kw}%')).fetchone()

    if not novel:
        return None, []

    chapters = conn.execute("""
        SELECT number, title, content FROM Chapter
        WHERE novelId = ?
        ORDER BY number ASC
    """, (novel['id'],)).fetchall()

    return dict(novel), [dict(c) for c in chapters]


def get_all_novel_slugs(conn):
    return {row['slug'] for row in conn.execute("SELECT slug FROM Novel").fetchall()}


def get_all_novel_titles(conn):
    return {row['title'] for row in conn.execute("SELECT title FROM Novel").fetchall()}


def _fake_novel_views():
    from config import FAKE_VIEWS_ENABLED, NOVEL_VIEWS_MIN, NOVEL_VIEWS_MAX
    if not FAKE_VIEWS_ENABLED:
        return 0
    return random.randint(NOVEL_VIEWS_MIN, NOVEL_VIEWS_MAX)


def _fake_novel_rating(view_count: int):
    """
    Trả về (rating, ratingCount) giả thực tế:
    - rating: 3.5 – 4.9 sao (làm tròn 1 chữ số)
    - ratingCount: 0.5%–2.0% của viewCount
    """
    from config import FAKE_VIEWS_ENABLED, NOVEL_RATING_MIN, NOVEL_RATING_MAX, NOVEL_RATING_RATE_MIN, NOVEL_RATING_RATE_MAX
    if not FAKE_VIEWS_ENABLED or view_count == 0:
        return 0.0, 0
    rating = round(random.uniform(NOVEL_RATING_MIN, NOVEL_RATING_MAX), 1)
    rate   = random.uniform(NOVEL_RATING_RATE_MIN, NOVEL_RATING_RATE_MAX)
    rating_count = max(1, int(view_count * rate))
    return rating, rating_count


def _fake_chapter_views(novel_views, chapter_index, total_chapters):
    """Chương đầu ≈ novel_views/total, giảm dần theo hình cong đến ~15% ở chương cuối."""
    from config import FAKE_VIEWS_ENABLED, CHAPTER_VIEWS_TAIL_RATIO
    if not FAKE_VIEWS_ENABLED or total_chapters == 0:
        return 0
    base = novel_views / max(total_chapters, 1)
    # ratio: 1.0 ở chương đầu → CHAPTER_VIEWS_TAIL_RATIO ở chương cuối
    t = chapter_index / max(total_chapters - 1, 1)
    ratio = 1.0 - (1.0 - CHAPTER_VIEWS_TAIL_RATIO) * t
    views = int(base * ratio * random.uniform(0.85, 1.15))
    return max(views, 1)


def insert_novel(conn, title, author, description, genres, tags="", status="completed", cover_image="", publish_status="pending", source_url=""):
    title = clean_text(title)
    author = clean_text(author)
    description = clean_text(description)
    slug = slugify(title)

    # Đảm bảo slug unique (loop cho đến khi không trùng)
    while conn.execute("SELECT id FROM Novel WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug}-{generate_cuid()[:6]}"

    novel_id = generate_cuid()
    now = datetime.utcnow().isoformat() + "Z"
    view_count   = _fake_novel_views()
    rating, rating_count = _fake_novel_rating(view_count)

    conn.execute("""
        INSERT INTO Novel (id, slug, title, author, description, coverImage, genres, tags, status, publishStatus, sourceUrl, viewCount, rating, ratingCount, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (novel_id, slug, title, author, description, cover_image or "/images/covers/default.jpg", genres, tags, status, publish_status, source_url.rstrip('/'), view_count, rating, rating_count, now, now))
    conn.commit()
    return novel_id, slug


def insert_chapter(conn, novel_id, number, title, content, chapter_index=0, total_chapters=1):
    content = clean_text(content)
    title = clean_text(title)
    chapter_id = generate_cuid()
    now = datetime.utcnow().isoformat() + "Z"

    novel_views = conn.execute("SELECT viewCount FROM Novel WHERE id = ?", (novel_id,)).fetchone()
    novel_views = novel_views['viewCount'] if novel_views else 0
    view_count = _fake_chapter_views(novel_views, chapter_index, total_chapters)

    conn.execute("""
        INSERT INTO Chapter (id, number, title, content, wordCount, novelId, viewCount, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (chapter_id, number, title, content, len(content.split()), novel_id, view_count, now, now))

    conn.execute("UPDATE Novel SET updatedAt = ? WHERE id = ?", (now, novel_id))
    conn.commit()
    return chapter_id


def get_stats(conn):
    novels = conn.execute("SELECT COUNT(*) as c FROM Novel").fetchone()['c']
    chapters = conn.execute("SELECT COUNT(*) as c FROM Chapter").fetchone()['c']
    return {"novels": novels, "chapters": chapters}


def get_all_novels(conn):
    """Trả về danh sách tất cả truyện kèm số chương."""
    rows = conn.execute("""
        SELECT n.id, n.slug, n.title, n.author, n.genres, n.status, n.publishStatus,
               n.viewCount, n.createdAt,
               COUNT(c.id) AS chapterCount
        FROM Novel n
        LEFT JOIN Chapter c ON c.novelId = n.id
        GROUP BY n.id
        ORDER BY n.createdAt DESC
    """).fetchall()
    return [dict(r) for r in rows]


def find_novel(conn, keyword: str):
    """
    Tìm truyện theo slug, id, hoặc tên (có thể khớp một phần).
    Trả về list các row khớp.
    """
    kw = keyword.strip()
    rows = conn.execute("""
        SELECT n.id, n.slug, n.title, n.author,
               COUNT(c.id) AS chapterCount
        FROM Novel n
        LEFT JOIN Chapter c ON c.novelId = n.id
        WHERE n.id = ? OR n.slug = ? OR n.title LIKE ?
        GROUP BY n.id
    """, (kw, kw, f'%{kw}%')).fetchall()
    return [dict(r) for r in rows]


def delete_novel(conn, novel_id: str):
    """Xóa 1 truyện và toàn bộ chương của nó theo id."""
    conn.execute("DELETE FROM Chapter WHERE novelId = ?", (novel_id,))
    conn.execute("DELETE FROM Novel WHERE id = ?", (novel_id,))
    conn.commit()


def delete_all_novels(conn):
    """Xóa toàn bộ truyện và chương trong database."""
    conn.execute("DELETE FROM Chapter")
    conn.execute("DELETE FROM Novel")
    conn.commit()
