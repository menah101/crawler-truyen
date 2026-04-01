"""
ScraperRegistry — đăng ký scraper theo domain.
Hỗ trợ một scraper → nhiều domain (thay đổi TLD thoải mái).
"""

from urllib.parse import urlparse


class ScraperRegistry:
    _scrapers: dict[str, type] = {}   # domain → class
    _instances: dict[str, object] = {}  # name → instance (cache)

    @classmethod
    def register(cls, *domains):
        """
        Decorator đăng ký một class vào một hoặc nhiều domain.

        @registry.register('saytruyen.vn', 'saytruyen.com', 'saytruyen.com.vn')
        class SayTruyen(BaseSource): ...
        """
        def decorator(scraper_class):
            for domain in domains:
                cls._scrapers[domain.lower()] = scraper_class
            return scraper_class
        return decorator

    @classmethod
    def get_by_url(cls, url):
        """Trả về instance scraper phù hợp với URL, hoặc None."""
        domain = urlparse(url).netloc.lower().lstrip('www.')
        for registered, klass in cls._scrapers.items():
            if registered in domain or domain in registered:
                return klass()
        return None

    @classmethod
    def get_by_name(cls, name):
        """Trả về instance scraper theo tên (name attribute của class)."""
        for klass in set(cls._scrapers.values()):
            if getattr(klass, 'name', '') == name:
                return klass()
        return None

    @classmethod
    def all_sources(cls):
        """Trả về dict {name: instance} cho tất cả scraper đã đăng ký (không trùng)."""
        seen, result = set(), {}
        for klass in cls._scrapers.values():
            name = getattr(klass, 'name', '')
            if name and name not in seen:
                seen.add(name)
                result[name] = klass()
        return result

    @classmethod
    def domains_for(cls, name):
        """Trả về danh sách domain đã đăng ký cho một scraper."""
        return [d for d, k in cls._scrapers.items() if getattr(k, 'name', '') == name]


registry = ScraperRegistry()
