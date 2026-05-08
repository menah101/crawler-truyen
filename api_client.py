"""
API client — POST truyện + chương lên RPi thay vì ghi trực tiếp SQLite.

Dùng khi IMPORT_MODE = "api" trong config.py.
"""

import json
import logging

logger = logging.getLogger(__name__)


def import_novel(novel_data: dict, chapters: list, *, replace_chapters: bool = False) -> dict:
    """
    POST novel + chapters tới /api/admin/import.

    Args:
        novel_data: dict với các key: title, author, description, genres, tags, status, cover_image
        chapters:   list of dict với các key: number, title, content
        replace_chapters: True → DELETE all chapters của novel trước khi INSERT
                          (dùng sau khi split/merge ở local). False → resume mode (skip
                          chapter trùng number, chỉ thêm chapter mới).

    Returns:
        dict: { success, novel_id, slug, inserted, skipped, deleted, note? }

    Raises:
        RuntimeError: nếu xác thực thất bại hoặc lỗi mạng/server
    """
    try:
        import requests
    except ImportError:
        raise RuntimeError(
            "❌ Thiếu thư viện 'requests'. Chạy: pip install requests"
        )

    from config import API_BASE_URL, API_SECRET
    from _http_utils import make_session, warn_if_insecure_url

    if not API_BASE_URL:
        raise RuntimeError("❌ API_BASE_URL chưa được cấu hình trong config.py")
    if not API_SECRET:
        raise RuntimeError("❌ API_SECRET chưa được cấu hình trong config.py")

    warning = warn_if_insecure_url(API_BASE_URL, secret_present=True)
    if warning:
        logger.warning(warning)

    endpoint = f"{API_BASE_URL.rstrip('/')}/api/admin/import"
    payload  = {
        "novel": novel_data,
        "chapters": chapters,
        "replace_chapters": replace_chapters,
    }

    logger.debug(f"   → POST {endpoint}  ({len(chapters)} chương)")

    session = make_session()
    try:
        resp = session.post(
            endpoint,
            json=payload,
            headers={
                "Content-Type":   "application/json",
                "X-Import-Secret": API_SECRET,
            },
            timeout=120,
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"❌ Không kết nối được tới {endpoint} (đã retry)\n   {type(exc).__name__}"
        ) from exc
    except requests.exceptions.Timeout:
        raise RuntimeError(f"❌ Timeout kết nối tới {endpoint} (>120s, đã retry)")

    if resp.status_code == 401:
        raise RuntimeError(
            "❌ Xác thực thất bại (401) — kiểm tra IMPORT_SECRET trong config.py "
            "và IMPORT_SECRET trong .env.local trên RPi"
        )
    if resp.status_code == 400:
        raise RuntimeError(f"❌ Dữ liệu không hợp lệ (400): {resp.text[:300]}")
    if not resp.ok:
        raise RuntimeError(
            f"❌ Lỗi server {resp.status_code}: {resp.text[:300]}"
        )

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"❌ Server trả về JSON không hợp lệ: {resp.text[:200]}")


def upload_chapter_audio(slug: str, chapter_number: int, mp3_path) -> dict:
    """
    POST file MP3 lên /api/admin/upload-audio (auth bằng X-Import-Secret).
    Pi4 sẽ upload S3 + update Chapter.audioUrl/audioDuration.

    Args:
        slug:           novel slug
        chapter_number: số chương (int dương)
        mp3_path:       path tới file .mp3

    Returns:
        dict: { success, chapterId, slug, chapterNumber, url, duration }

    Raises:
        FileNotFoundError: file MP3 không tồn tại
        RuntimeError:      auth/network/server lỗi
    """
    try:
        import requests
    except ImportError:
        raise RuntimeError("❌ Thiếu thư viện 'requests'. Chạy: pip install requests")

    from pathlib import Path
    from config import API_BASE_URL, API_SECRET
    from _http_utils import make_session, warn_if_insecure_url

    if not API_BASE_URL:
        raise RuntimeError("❌ API_BASE_URL chưa được cấu hình")
    if not API_SECRET:
        raise RuntimeError("❌ API_SECRET chưa được cấu hình")

    warning = warn_if_insecure_url(API_BASE_URL, secret_present=True)
    if warning:
        logger.warning(warning)

    p = Path(mp3_path)
    if not p.is_file():
        raise FileNotFoundError(f"Không tìm thấy MP3: {p}")

    # Cảnh báo file lớn — Cloudflare default 100MB body limit.
    size_mb = p.stat().st_size / 1024 / 1024
    if size_mb > 100:
        raise RuntimeError(f"❌ MP3 quá lớn ({size_mb:.1f}MB) — Cloudflare giới hạn ~100MB")
    if size_mb > 50:
        logger.warning(f"⚠️ MP3 lớn ({size_mb:.1f}MB) — upload có thể chậm")

    endpoint = f"{API_BASE_URL.rstrip('/')}/api/admin/upload-audio"

    session = make_session()
    with p.open("rb") as f:
        files = {"file": (p.name, f, "audio/mpeg")}
        data  = {"slug": slug, "chapterNumber": str(chapter_number)}
        try:
            resp = session.post(
                endpoint, files=files, data=data,
                headers={"X-Import-Secret": API_SECRET},
                timeout=180,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"❌ Không kết nối được tới {endpoint} (đã retry)\n   {type(exc).__name__}") from exc
        except requests.exceptions.Timeout:
            raise RuntimeError(f"❌ Timeout upload {p.name} (>180s, đã retry)")

    if resp.status_code == 401:
        raise RuntimeError("❌ 401 — kiểm tra IMPORT_SECRET ở local + .env trên pi4")
    if resp.status_code == 404:
        raise RuntimeError(f"❌ 404 — {resp.text[:200]}")
    if resp.status_code in (400, 413, 415):
        raise RuntimeError(f"❌ {resp.status_code} — {resp.text[:200]}")
    if not resp.ok:
        raise RuntimeError(f"❌ Lỗi {resp.status_code}: {resp.text[:300]}")

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"❌ JSON không hợp lệ: {resp.text[:200]}")
