"""Adapter cho monkeyd.com.vn / monkeyd.net.vn"""

import re
from .base import BaseSource
from .registry import registry


@registry.register('monkeyd.com.vn', 'monkeyd.net.vn', 'monkeyd.com', 'monkeyd.net')
class MonkeyD(BaseSource):
    name = 'monkeyd'
    base_url = 'https://monkeyd.com.vn'
    label = 'MonkeyD (monkeyd.com.vn)'
    headers = {
        **BaseSource.headers,
        'Referer': 'https://monkeyd.com.vn/',
    }

    def get_novel_urls(self, max_count=80):
        results, seen = [], set()
        page = 1
        while len(results) < max_count:
            url = self.base_url + f'/danh-sach/truyen-full?page={page}'
            print(f"  📡 [{self.name}] {url}")
            soup = self._soup(url)
            if not soup:
                break

            items = soup.select('.episode-title a, .book-item a[href*="/truyen/"]')
            if not items:
                break

            for a in items:
                href = a.get('href', '').strip()
                title = a.get_text(strip=True) or a.get('title', '')
                if href and title and href not in seen:
                    if not href.startswith('http'):
                        href = self.base_url + href
                    seen.add(href)
                    results.append((href, title))
                if len(results) >= max_count:
                    break

            next_btn = soup.select_one('.pagination .next a, .pagination li.active + li a')
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
        for sel in ['h1', 'h2', '.title']:
            el = soup.select_one(sel)
            if el and 2 < len(el.get_text(strip=True)) < 200:
                title = el.get_text(strip=True)
                break
        if not title:
            return None

        author = 'Đang cập nhật'
        for sel in ['.author a', 'a[href*="tac-gia"]']:
            el = soup.select_one(sel)
            if el:
                author = el.get_text(strip=True)
                break

        desc = ''
        for sel in ['.description', '.summary', '.desc-text']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 10:
                desc = el.get_text(strip=True)
                break

        cover_image = ''
        for sel in ['.book-cover img', '.thumb img', 'img[class*="cover"]']:
            el = soup.select_one(sel)
            if el:
                src = el.get('src', '')
                if src:
                    cover_image = src if src.startswith('http') else self.base_url + src
                    break

        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('a[href*="the-loai"], a[href*="genre"]')
        ]

        return {'title': title, 'author': author, 'description': desc,
                'status': 'completed', 'cover_image': cover_image, 'genres_raw': genres_raw}

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        soup = self._soup(url)
        if not soup:
            return []

        urls = []
        for div in soup.find_all('div', class_='episode-title'):
            for a in div.find_all('a', href=True):
                href = a['href']
                if not href.startswith('http'):
                    href = self.base_url + href
                urls.append(href)

        print(f"  📖 [{self.name}] {len(urls)} chương")
        return urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = soup.find('div', class_='content-container')
        if not div:
            return ''

        paras = []
        for p in div.find_all('p', class_=False):
            if p.find('em'):
                continue
            for el in p.find_all(['script', 'style', 'div', 'a', 'span']):
                el.decompose()
            text = p.get_text().strip()
            if text and len(text) > 10 and not re.search(r'https?://\S+', text):
                paras.append(text)

        return '\n\n'.join(paras)
