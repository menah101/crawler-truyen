"""Base class cho tất cả source adapters."""

import requests
from bs4 import BeautifulSoup


class BaseSource:
    name = ''
    base_url = ''
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.5',
    }
    timeout = 15

    def _get(self, url):
        try:
            r = requests.get(url, headers={**self.headers, 'Referer': self.base_url + '/'},
                             timeout=self.timeout)
            r.raise_for_status()
            r.encoding = 'utf-8'
            return r
        except requests.exceptions.RequestException as e:
            print(f"  ❌ [{self.name}] Request error: {e}")
            return None

    def _soup(self, url):
        r = self._get(url)
        return BeautifulSoup(r.text, 'html.parser') if r else None

    # ── Subclasses must implement ──────────────────────────────────────────────

    def get_novel_urls(self, max_count=80):
        """Return list of (url, title)."""
        raise NotImplementedError

    def get_novel_info(self, url):
        """Return dict: title, author, description, status, cover_image."""
        raise NotImplementedError

    def get_chapter_urls(self, url):
        """Return list of chapter URLs."""
        raise NotImplementedError

    def get_chapter_content(self, url):
        """Return plain text content of a chapter."""
        raise NotImplementedError
