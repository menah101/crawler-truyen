"""JSON log tracking truyện đã đăng MXH — tránh đăng trùng.

File: crawler/social_log.json
Schema:
  {
    "ten-truyen-slug": {
      "telegram": {"status": "ok", "posted_at": "2026-04-19T10:20:00", "post_id": "42"},
      "discord":  {"status": "ok", "posted_at": "..."},
      "twitter":  {"status": "failed", "posted_at": "...", "error": "..."}
    }
  }
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from threading import Lock

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'social_log.json')
_lock = Lock()


def _load() -> dict:
    if not os.path.exists(LOG_PATH):
        return {}
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    tmp = LOG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LOG_PATH)


def has_posted(slug: str, platform: str) -> bool:
    """True nếu truyện đã đăng thành công lên platform này."""
    with _lock:
        data = _load()
    entry = data.get(slug, {}).get(platform)
    return bool(entry and entry.get('status') == 'ok')


def mark(slug: str, platform: str, result: dict) -> None:
    """Ghi kết quả 1 lần đăng vào log."""
    status = 'ok' if result.get('ok') else ('skipped' if result.get('skipped') else 'failed')
    record = {
        'status': status,
        'posted_at': datetime.now().isoformat(timespec='seconds'),
    }
    for k in ('message_id', 'post_id', 'tweet_id', 'media_id', 'pin_id'):
        if k in result:
            record[k] = result[k]
    if result.get('error'):
        record['error'] = result['error'][:300]
    if result.get('reason'):
        record['reason'] = result['reason']

    with _lock:
        data = _load()
        data.setdefault(slug, {})[platform] = record
        _save(data)


def posted_platforms(slug: str) -> set[str]:
    """Các platform đã đăng OK cho slug này."""
    with _lock:
        data = _load()
    return {p for p, e in data.get(slug, {}).items() if e.get('status') == 'ok'}


def reset_slug(slug: str) -> None:
    """Xoá log của 1 truyện (để đăng lại)."""
    with _lock:
        data = _load()
        data.pop(slug, None)
        _save(data)
