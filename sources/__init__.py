"""
Registry nguồn crawl truyện.

Mỗi source được đăng ký bằng decorator @registry.register('domain1', 'domain2', ...)
Khi domain đổi TLD chỉ cần thêm domain mới vào decorator — không sửa logic.
"""

from .registry import registry  # noqa: F401 — expose for external use
from .yeungontinh import YeunGoNTinh
from .truyenfull import TruyenFull
from .metruyencv import MeTruyenCV
from .monkeyd import MonkeyD
from .vivutruyen import VivuTruyen
from .saytruyen import SayTruyen
from .truyenfullvision import TruyenFullVision
from .tvtruyen import TvTruyen
from .hongtruyenhot import HongTruyenHot

# Kept to satisfy linters — classes are used via registry
__all__ = [
    'registry', 'SOURCES', 'get_source', 'get_source_for_url',
    'YeunGoNTinh', 'TruyenFull', 'MeTruyenCV', 'TvTruyen',
    'MonkeyD', 'VivuTruyen', 'SayTruyen', 'TruyenFullVision',
    'HongTruyenHot',
]

# Build SOURCES dict từ registry (không trùng lặp, theo name)
SOURCES = registry.all_sources()


def get_source(name):
    """Lấy scraper instance theo tên."""
    src = SOURCES.get(name)
    if not src:
        raise ValueError(
            f"Nguồn không hợp lệ: '{name}'. "
            f"Chọn: {list(SOURCES.keys())}"
        )
    return src


def get_source_for_url(url):
    """Tự động chọn scraper dựa vào domain của URL."""
    src = registry.get_by_url(url)
    if not src:
        raise ValueError(
            f"Không có scraper nào hỗ trợ URL: {url}\n"
            f"Các domain đã đăng ký: {list(registry._scrapers.keys())}"
        )
    return src
