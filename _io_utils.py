"""Shared I/O helpers — atomic writes to avoid corrupt files on crash.

Resume logic ở các pipeline (cover, scenes, srt, tts) dựa vào
`os.path.exists(path)`. Nếu process crash giữa write thì file half-written
nhưng `exists()` trả True → resume bỏ qua mãi. Pattern atomic: write tmp
cùng thư mục, rồi `os.replace` để rename atomic.
"""
from __future__ import annotations

import os
import tempfile
from typing import Union


def atomic_write_bytes(path: Union[str, os.PathLike], data: bytes) -> None:
    path = os.fspath(path)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def atomic_write_text(path: Union[str, os.PathLike], text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_save_pil(image, path: Union[str, os.PathLike], **save_kwargs) -> None:
    """Save PIL Image atomically. Tự suy format từ extension nếu không truyền."""
    path = os.fspath(path)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    suffix = os.path.splitext(path)[1] or ".tmp"
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=suffix, dir=d)
    os.close(fd)
    try:
        image.save(tmp, **save_kwargs)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise
