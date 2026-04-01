"""
Adapter cho www.webnovel.com (tiếng Anh → tự động dịch sang tiếng Việt).

webnovel.com dùng Next.js — toàn bộ data nằm trong thẻ
  <script id="__NEXT_DATA__" type="application/json">
Không dùng apiajax (404 từ 2024).

Cấu trúc URL:
  Novel  : https://www.webnovel.com/book/{bookId}_{slug}
  Chapter: https://www.webnovel.com/book/{bookId}_{slug}/{chapterId}_{chapterSlug}
"""

import re
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from .base import BaseSource
from .registry import registry

logger = logging.getLogger(__name__)

RANKING_URLS = [
    'https://www.webnovel.com/ranking/novel/all_time/popular_rank',
    'https://www.webnovel.com/ranking/novel/all_time/power_rank',
    'https://www.webnovel.com/ranking/novel/season/best_sellers',
]


@registry.register('www.webnovel.com', 'webnovel.com')
class WebNovel(BaseSource):
    name = 'webnovel'
    label = 'WebNovel (EN → VI)'
    base_url = 'https://www.webnovel.com'
    needs_translation = True

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.webnovel.com/',
    }
    timeout = 20

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get(self, url, params=None):
        try:
            r = requests.get(
                url, headers=self.headers, params=params,
                timeout=self.timeout, allow_redirects=True,
            )
            r.raise_for_status()
            r.encoding = 'utf-8'
            return r
        except requests.RequestException as e:
            logger.warning(f"  ❌ [webnovel] {e}")
            return None

    def _soup_and_nextdata(self, url) -> tuple:
        """Return (BeautifulSoup, next_data_dict | None)."""
        r = self._get(url)
        if not r:
            return None, None
        soup = BeautifulSoup(r.text, 'html.parser')
        tag = soup.find('script', id='__NEXT_DATA__')
        if tag:
            try:
                return soup, json.loads(tag.string)
            except Exception:
                pass
        return soup, None

    @staticmethod
    def _extract_book_id(url: str) -> str | None:
        m = re.search(r'/book/(\d+)', url)
        return m.group(1) if m else None

    # ── get_novel_urls ────────────────────────────────────────────────────────

    def get_novel_urls(self, max_count: int = 20, query: str = '') -> list[tuple[str, str]]:
        """
        Lấy truyện từ trang ranking hoặc search.
        Nếu `query` được cung cấp → search, ngược lại dùng ranking.
        """
        if query:
            return self._search_novels(query, max_count)
        return self._ranking_novels(max_count)

    def _search_novels(self, query: str, max_count: int) -> list[tuple[str, str]]:
        search_url = f"{self.base_url}/search"
        soup, next_data = self._soup_and_nextdata(f"{search_url}?keywords={query}")
        results = []

        # Try __NEXT_DATA__ first
        if next_data:
            results = self._extract_books_from_nextdata(next_data)

        # Fallback: scrape anchor tags
        if not results and soup:
            results = self._extract_books_from_soup(soup)

        return results[:max_count]

    def _ranking_novels(self, max_count: int) -> list[tuple[str, str]]:
        results = []
        for rank_url in RANKING_URLS:
            if len(results) >= max_count:
                break
            soup, next_data = self._soup_and_nextdata(rank_url)

            if next_data:
                results += self._extract_books_from_nextdata(next_data)
            elif soup:
                results += self._extract_books_from_soup(soup)

            time.sleep(1.5)

        # Deduplicate
        seen, unique = set(), []
        for url, title in results:
            if url not in seen:
                seen.add(url)
                unique.append((url, title))
        return unique[:max_count]

    @staticmethod
    def _extract_books_from_nextdata(next_data: dict) -> list[tuple[str, str]]:
        """Walk __NEXT_DATA__ to find book items."""
        results = []
        raw = json.dumps(next_data)
        # Find all bookId+bookName pairs in JSON
        for m in re.finditer(
            r'"bookId"\s*:\s*"(\d+)".*?"bookName"\s*:\s*"([^"]+)"', raw
        ):
            book_id, book_name = m.group(1), m.group(2)
            slug = re.sub(r'[^a-z0-9]+', '-', book_name.lower()).strip('-')
            url = f"https://www.webnovel.com/book/{book_id}_{slug}"
            results.append((url, book_name))
        return results

    @staticmethod
    def _extract_books_from_soup(soup) -> list[tuple[str, str]]:
        """Fallback: scrape anchor tags pointing to /book/."""
        results = []
        for a in soup.select('a[href*="/book/"]'):
            href = a.get('href', '')
            if not re.search(r'/book/\d+', href):
                continue
            title = (
                a.get('title') or
                a.select_one('h3, h2, p') and a.select_one('h3, h2, p').get_text(strip=True) or
                a.get_text(strip=True)
            )
            if not title or len(title) < 2:
                continue
            full = href if href.startswith('http') else f"https://www.webnovel.com{href}"
            # Normalise to root book URL
            m = re.match(r'(https?://[^/]+/book/\d+[^/?#]*)', full)
            if m:
                results.append((m.group(1), title))
        return results

    # ── get_novel_info ────────────────────────────────────────────────────────

    def get_novel_info(self, url: str) -> dict:
        soup, next_data = self._soup_and_nextdata(url)
        if not soup:
            return {}

        title_en = author_en = desc_en = cover = status_raw = ''
        genres_raw = []

        if next_data:
            # Navigate the props tree
            props = next_data.get('props', {}).get('pageProps', {})
            book = (
                props.get('bookInfo') or
                props.get('book') or
                props.get('data', {}).get('bookInfo') or
                {}
            )
            title_en = book.get('bookName', '') or book.get('title', '')
            author_en = book.get('authorName', '') or book.get('author', '')
            desc_en = book.get('description', '') or book.get('intro', '')
            cover = book.get('coverUpdateTime', '') and book.get('bookId') and \
                f"https://img.webnovel.com/bookcover/{book['bookId']}/300/300.jpg"
            status_val = book.get('actionStatus', 0)
            status_raw = 'completed' if status_val == 2 else 'ongoing'
            tags = book.get('categoryItems', []) or book.get('tags', [])
            genres_raw = [
                (t.get('categoryName') or t.get('tagName') or t.get('name') or '').lower()
                for t in tags if isinstance(t, dict)
            ]

        # Fallback to HTML
        if not title_en and soup:
            t = soup.select_one('h1') or soup.select_one('[class*="book-name"]')
            title_en = t.get_text(strip=True) if t else ''
            a = soup.select_one('address') or soup.select_one('[class*="author"]')
            author_en = a.get_text(strip=True) if a else 'Unknown'
            d = soup.select_one('[class*="synopsis"] p') or soup.select_one('[class*="intro"] p')
            desc_en = d.get_text(strip=True) if d else ''
            cover_tag = soup.select_one('[class*="book-cover"] img') or soup.select_one('img[class*="cover"]')
            cover = cover_tag.get('src', '') if cover_tag else ''

        if not title_en:
            return {}

        logger.info(f"    🌐 Dịch metadata: {title_en[:50]}")
        try:
            from translator import translate_novel_info
            translated = translate_novel_info(title_en, author_en or 'Unknown', desc_en)
        except Exception as e:
            logger.warning(f"    ⚠️ Dịch metadata thất bại: {e}")
            translated = {'title': title_en, 'author': author_en, 'description': desc_en}

        return {
            'title': translated['title'] or title_en,
            'author': translated['author'] or author_en or 'Unknown',
            'description': translated['description'] or desc_en,
            'status': status_raw or 'ongoing',
            'cover_image': cover,
            'genres_raw': genres_raw,
            '_title_en': title_en,
        }

    # ── get_chapter_urls ──────────────────────────────────────────────────────

    def get_chapter_urls(self, url: str) -> list[str]:
        """Lấy danh sách URL chương từ __NEXT_DATA__ hoặc HTML."""
        soup, next_data = self._soup_and_nextdata(url)
        book_id = self._extract_book_id(url)
        chapters = []

        if next_data:
            chapters = self._extract_chapters_from_nextdata(next_data, book_id)

        if not chapters and soup:
            chapters = self._extract_chapters_from_soup(soup, url)

        logger.info(f"    📋 {len(chapters)} chương tìm được")
        return chapters

    def _extract_chapters_from_nextdata(self, next_data: dict, book_id: str) -> list[str]:
        raw = json.dumps(next_data)
        # Look for chapterId + chapterName pairs
        matches = re.findall(
            r'"chapterId"\s*:\s*"(\d+)"[^}]*?"chapterName"\s*:\s*"([^"]+)"',
            raw,
        )
        if not matches:
            matches = re.findall(
                r'"id"\s*:\s*"(\d+)"[^}]*?"name"\s*:\s*"([^"]+)"',
                raw,
            )
        results = []
        for ch_id, ch_name in matches:
            slug = re.sub(r'[^a-z0-9]+', '-', ch_name.lower()).strip('-') or 'chapter'
            book_part = f"{book_id}_book" if book_id else 'book'
            results.append(
                f"{self.base_url}/book/{book_part}/{ch_id}_{slug}"
            )
        return results

    def _extract_chapters_from_soup(self, soup, _base_url: str) -> list[str]:
        links = soup.select('a[href*="/book/"][href*="chapter"], a[href*="/book/"]:not([href$="/book/"])')
        seen, result = set(), []
        for a in links:
            href = a.get('href', '')
            if not href or '/book/' not in href:
                continue
            # Must have at least 2 path segments after /book/
            parts = href.rstrip('/').split('/book/')[-1].split('/')
            if len(parts) < 2:
                continue
            full = href if href.startswith('http') else urljoin(self.base_url, href)
            if full not in seen:
                seen.add(full)
                result.append(full)
        return result

    # ── get_chapter_content ───────────────────────────────────────────────────

    def get_chapter_content(self, url: str) -> str:
        soup, next_data = self._soup_and_nextdata(url)
        content_en = ''

        if next_data:
            content_en = self._extract_content_from_nextdata(next_data)

        if not content_en and soup:
            content_en = self._extract_content_from_soup(soup)

        if not content_en or len(content_en) < 30:
            logger.warning(f"    ⚠️ Không lấy được nội dung: {url}")
            return ''

        logger.info(f"    🌐 Dịch chương ({len(content_en)} ký tự)…")
        try:
            from translator import translate_chapter
            return translate_chapter(content_en)
        except Exception as e:
            logger.warning(f"    ⚠️ Dịch thất bại: {e} — giữ bản gốc")
            return content_en

    @staticmethod
    def _extract_content_from_nextdata(next_data: dict) -> str:
        raw = json.dumps(next_data)
        # Common keys for chapter content
        for key in ('"content"', '"chapterContent"', '"text"'):
            m = re.search(rf'{key}\s*:\s*"((?:[^"\\]|\\.){{50,}})"', raw)
            if m:
                text = m.group(1).encode().decode('unicode_escape', errors='replace')
                soup = BeautifulSoup(text, 'html.parser')
                paragraphs = [p.get_text(strip=True) for p in soup.find_all('p')]
                if paragraphs:
                    return '\n\n'.join(p for p in paragraphs if p)
                return soup.get_text('\n\n').strip()
        return ''

    @staticmethod
    def _extract_content_from_soup(soup) -> str:
        content_div = (
            soup.select_one('div.j_chapContent') or
            soup.select_one('div[class*="chapter-content"]') or
            soup.select_one('div[class*="cha-words"]') or
            soup.select_one('div[class*="reader-content"]') or
            soup.select_one('div#chapter-content')
        )
        if not content_div:
            return ''

        for tag in content_div.select('script, style, [class*="ads"]'):
            tag.decompose()

        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 5 and not re.search(r'https?://', text):
                paragraphs.append(text)

        return '\n\n'.join(paragraphs)
