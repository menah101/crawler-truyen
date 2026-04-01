"""Adapter cho tvtruyen.com."""

import re
import json
import time
import logging
from .base import BaseSource
from .registry import registry

logger = logging.getLogger(__name__)


@registry.register('www.tvtruyen.com', 'tvtruyen.com')
class TvTruyen(BaseSource):
    name = 'tvtruyen'
    label = 'TvTruyen (tvtruyen.com)'
    base_url = 'https://www.tvtruyen.com'

    # ── Novel listing ─────────────────────────────────────────────────────────

    def get_novel_urls(self, max_count: int = 80) -> list[tuple[str, str]]:
        seen, results = set(), []
        page = 1
        while len(results) < max_count:
            url = f"{self.base_url}/?page={page}"
            soup = self._soup(url)
            if not soup:
                break
            cards = soup.select('.comic-card a[itemprop="url"]')
            if not cards:
                break
            for a in cards:
                href = a.get('href', '')
                if not href:
                    continue
                full = href if href.startswith('http') else f"{self.base_url}{href}"
                if full in seen:
                    continue
                seen.add(full)
                title_tag = a.find_parent('.comic-card')
                title = ''
                if title_tag:
                    t = title_tag.select_one('h3[itemprop="name"]')
                    title = t.get_text(strip=True) if t else ''
                results.append((full, title))
                if len(results) >= max_count:
                    break
            page += 1
            time.sleep(1.0)
        return results

    # ── Novel info ────────────────────────────────────────────────────────────

    def get_novel_info(self, url: str) -> dict:
        soup = self._soup(url)
        if not soup:
            return {}

        # Title
        title_tag = soup.select_one('h3.title[itemprop="name"], h3#comic_name')
        title = title_tag.get_text(strip=True) if title_tag else ''
        if not title:
            return {}

        # Author
        author_tag = soup.select_one('a[itemprop="author"]')
        author = author_tag.get_text(strip=True) if author_tag else 'Đang cập nhật'

        # Description — prefer JSON-LD schema
        desc = ''
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or '')
                if isinstance(data, dict) and data.get('description'):
                    desc = data['description']
                    break
            except Exception:
                pass
        if not desc:
            d = soup.select_one('.desc p, .summary p, .intro p')
            desc = d.get_text(strip=True) if d else ''

        # Status
        status_tag = soup.select_one('.text-success.item-value')
        status_text = status_tag.get_text(strip=True).lower() if status_tag else ''
        status = 'completed' if 'full' in status_text or 'hoàn' in status_text else 'ongoing'

        # Cover image
        cover_tag = soup.select_one('img[itemprop="image"]')
        cover = cover_tag.get('src', '') if cover_tag else ''

        # Genres
        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('a[itemprop="genre"]')
        ]

        return {
            'title': title,
            'author': author,
            'description': desc,
            'status': status,
            'cover_image': cover,
            'genres_raw': genres_raw,
        }

    # ── Chapter list ──────────────────────────────────────────────────────────

    def get_chapter_urls(self, url: str) -> list[str]:
        """Lấy tất cả URL chương (hỗ trợ phân trang)."""
        chapters = []
        page = 1
        while True:
            page_url = f"{url}?page={page}#mobile-list-chapter"
            soup = self._soup(page_url)
            if not soup:
                break

            links = soup.select('a.chapter-link[data-chapter]')
            if not links:
                break

            for a in links:
                href = a.get('href', '')
                if href:
                    full = href if href.startswith('http') else f"{self.base_url}{href}"
                    chapters.append(full)

            # Check if next page exists
            next_page = soup.select_one('li.custom-page-item.nav-next:not(.is-disabled) a')
            if not next_page:
                break
            page += 1
            time.sleep(0.8)

        # tvtruyen lists newest first — reverse to get chapter 1 first
        chapters.reverse()
        return chapters

    # ── Chapter content ───────────────────────────────────────────────────────

    def get_chapter_content(self, url: str) -> str:
        soup = self._soup(url)
        if not soup:
            return ''

        content_div = soup.select_one('div#chapter-content')
        if not content_div:
            return ''

        # Remove attribution signatures
        for sig in content_div.select('span.signature, script, style'):
            sig.decompose()

        paragraphs = []
        for p in content_div.find_all('p'):
            # Replace <br> with newline before extracting text
            for br in p.find_all('br'):
                br.replace_with('\n')
            text = p.get_text(strip=True)
            if text and len(text) > 3 and not re.search(r'https?://', text):
                paragraphs.append(text)

        return '\n\n'.join(paragraphs)
