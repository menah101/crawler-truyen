"""Adapter cho vivutruyen.net / truyenmeomeo.com"""

import re
from urllib.parse import urljoin
from .base import BaseSource
from .registry import registry


@registry.register('vivutruyen.net', 'vivutruyen.com', 'truyenmeomeo.com', 'www.truyenmeomeo.com')
class VivuTruyen(BaseSource):
    name = 'vivutruyen'
    base_url = 'https://vivutruyen.net'
    label = 'VivuTruyen (vivutruyen.net)'
    headers = {
        **BaseSource.headers,
        'Referer': 'https://vivutruyen.net/',
    }

    def get_novel_urls(self, max_count=80):
        results, seen = [], set()
        page = 1
        while len(results) < max_count:
            url = self.base_url + f'/moi-cap-nhat/?page={page}'
            print(f"  📡 [{self.name}] {url}")
            soup = self._soup(url)
            if not soup:
                break

            items = soup.select('.list-truyen .row h3.truyen-title a, '
                                '.list-truyen .truyen-item a.truyen-title, '
                                '.list-story .story-item a')
            if not items:
                break

            for a in items:
                href = a.get('href', '').strip()
                title = a.get_text(strip=True) or a.get('title', '').strip()
                if href and title and href not in seen:
                    if not href.startswith('http'):
                        href = urljoin(self.base_url, href)
                    seen.add(href)
                    results.append((href, title))
                if len(results) >= max_count:
                    break

            next_btn = soup.select_one('.pagination li.active + li a')
            if not next_btn:
                break
            page += 1

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results[:max_count]

    def get_novel_info(self, url):
        soup = self._soup(url)
        if not soup:
            return None

        title = ''
        for sel in ['h3.title', 'h1', '.truyen-title']:
            el = soup.select_one(sel)
            if el and 2 < len(el.get_text(strip=True)) < 200:
                title = el.get_text(strip=True)
                break
        if not title and soup.title:
            title = soup.title.get_text(strip=True).split('|')[0].strip()
        if not title:
            return None

        author = 'Đang cập nhật'
        for sel in ['.info a[href*="tac-gia"]', '.author a', '.info-author']:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                author = el.get_text(strip=True)
                break

        desc = ''
        for sel in ['.desc-text', '.description', '.summary-content']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 10:
                desc = el.get_text(strip=True)
                break

        cover_image = ''
        for sel in ['.book img', '.thumb img', '.cover img', 'img[itemprop="image"]']:
            el = soup.select_one(sel)
            if el:
                src = el.get('src') or el.get('data-src', '')
                if src:
                    cover_image = src if src.startswith('http') else urljoin(self.base_url, src)
                    break

        status = 'completed'
        for sel in ['.info span', '.label']:
            for el in soup.select(sel):
                text = el.get_text(strip=True).lower()
                if 'đang ra' in text or 'ongoing' in text or 'chưa hoàn' in text:
                    status = 'ongoing'
                    break

        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('a[href*="the-loai"], .info a[href*="genre"]')
        ]

        return {'title': title, 'author': author, 'description': desc,
                'status': status, 'cover_image': cover_image, 'genres_raw': genres_raw}

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        soup = self._soup(url)
        if not soup:
            return []

        links = (
            soup.select('ul.list-chapter a')
            or soup.select('div.list-chapter a')
            or soup.find_all('a', class_='chap-title')
        )

        urls = []
        for a in links:
            href = a.get('href', '')
            if href and ('/chuong-' in href or '/chapter-' in href):
                full = href if href.startswith('http') else urljoin(url, href)
                if full not in urls:
                    urls.append(full)

        # vivutruyen lists newest first — reverse to get chapter 1 first
        urls.reverse()
        print(f"  📖 [{self.name}] {len(urls)} chương")
        return urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = (
            soup.select_one('div#chapter-content')
            or soup.select_one('div.chapter-content')
            or soup.select_one('div.uk-width-1-1.reading')
        )
        if not div:
            return ''

        for el in div.find_all(['script', 'style', 'iframe', 'button', 'ins']):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 5 and not re.search(r'https?://\S+', text):
                paras.append(text)

        if not paras:
            text = div.get_text('\n', strip=True)
            paras = [line.strip() for line in text.splitlines() if line.strip()]

        return '\n\n'.join(paras)
