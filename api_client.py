"""
API client — POST truyện + chương lên RPi thay vì ghi trực tiếp SQLite.

Dùng khi IMPORT_MODE = "api" trong config.py.
"""

import json
import logging

logger = logging.getLogger(__name__)


def import_novel(novel_data: dict, chapters: list) -> dict:
    """
    POST novel + chapters tới /api/admin/import.

    Args:
        novel_data: dict với các key: title, author, description, genres, tags, status, cover_image
        chapters:   list of dict với các key: number, title, content

    Returns:
        dict: { success, novel_id, slug, inserted, skipped, note? }

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

    if not API_BASE_URL:
        raise RuntimeError("❌ API_BASE_URL chưa được cấu hình trong config.py")
    if not API_SECRET:
        raise RuntimeError("❌ API_SECRET chưa được cấu hình trong config.py")

    endpoint = f"{API_BASE_URL.rstrip('/')}/api/admin/import"
    payload  = {"novel": novel_data, "chapters": chapters}

    logger.debug(f"   → POST {endpoint}  ({len(chapters)} chương)")

    try:
        resp = requests.post(
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
            f"❌ Không kết nối được tới {endpoint}\n   {exc}"
        ) from exc
    except requests.exceptions.Timeout:
        raise RuntimeError(f"❌ Timeout kết nối tới {endpoint} (>120s)")

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
