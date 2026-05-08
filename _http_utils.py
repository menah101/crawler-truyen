"""HTTP utilities — Session với retry/backoff cho 429/5xx.

Thay vì `requests.post(...)` thuần, các push module nên dùng `make_session()`
để mọi POST/GET đều tự retry trên transient failure (5xx, 429, ConnectionError).
"""
from __future__ import annotations

from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def make_session(
    *,
    total: int = 3,
    backoff_factor: float = 1.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Session:
    """Tạo Session với HTTPAdapter retry/backoff.

    backoff: 1.5 → wait 0s, 1.5s, 3s, 6s giữa các retry (theo `Retry`).
    """
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "HEAD"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def warn_if_insecure_url(url: str, secret_present: bool) -> Optional[str]:
    """Trả về cảnh báo (str) nếu URL là HTTP và có secret — secret sẽ đi plaintext."""
    if secret_present and url.startswith("http://"):
        return f"⚠️  URL không phải HTTPS ({url}) — secret sẽ đi plaintext, dễ bị MITM."
    return None
