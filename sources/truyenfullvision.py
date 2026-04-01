"""Adapter cho truyenfull.vision"""

import re
from .base import BaseSource
from .registry import registry


@registry.register('truyenfull.vision', 'truyenfull.tv', 'truyenfull.net')
class TruyenFullVision(BaseSource):
    name = 'truyenfullvision'
    base_url = 'https://truyenfull.vision'
    label = 'TruyenFull Vision (truyenfull.vision)'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
        'Referer': 'https://truyenfull.vision/',
    }

    def _normalize_url(self, url):
        """Đảm bảo URL luôn trỏ đúng domain truyenfull.vision."""
        parsed = url.split('//', 1)
        if len(parsed) == 2:
            # Thay domain khác bằng truyenfull.vision
            path = parsed[1].split('/', 1)
            return f"https://truyenfull.vision/{path[1] if len(path) > 1 else ''}"
        return url

    def get_novel_urls(self, max_count=80):
        results, seen = [], set()
        page = 1
        while len(results) < max_count:
            url = self.base_url + f'/danh-sach/truyen-full/trang-{page}/'
            print(f"  📡 [{self.name}] {url}")
            soup = self._soup(url)
            if not soup:
                break

            items = soup.select('.list-truyen .row[itemtype] h3.truyen-title a')
            if not items:
                break

            for a in items:
                href = a.get('href', '').strip()
                title = a.get_text(strip=True)
                if href and title and href not in seen:
                    if not href.startswith('http'):
                        href = self.base_url + href
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
        url = self._normalize_url(url)
        soup = self._soup(url)
        if not soup:
            return None

        title_el = soup.select_one('h3.title')
        title = title_el.get_text(strip=True) if title_el else ''
        if not title and soup.title:
            title = soup.title.get_text(strip=True).split('|')[0].strip()
        if not title:
            return None

        author = 'Đang cập nhật'
        author_el = soup.select_one('.info a[href*="tac-gia"]')
        if author_el:
            author = author_el.get_text(strip=True)

        desc = ''
        desc_el = soup.select_one('.desc-text')
        if desc_el:
            desc = desc_el.get_text(strip=True)

        cover_image = ''
        img_el = soup.select_one('.book img')
        if img_el:
            cover_image = img_el.get('src', '')
            if cover_image and not cover_image.startswith('http'):
                cover_image = self.base_url + cover_image

        status = 'completed'
        for span in soup.select('.info span'):
            text = span.get_text(strip=True).lower()
            if 'đang ra' in text or 'ongoing' in text:
                status = 'ongoing'
                break

        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('.info a[href*="the-loai"], a[href*="genre"]')
        ]

        return {'title': title, 'author': author, 'description': desc,
                'status': status, 'cover_image': cover_image, 'genres_raw': genres_raw}

    def get_chapter_urls(self, url):
        url = self._normalize_url(url)
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        all_urls = []
        page = 1

        while True:
            page_url = url.rstrip('/') + (f'?page={page}' if page > 1 else '')
            soup = self._soup(page_url)
            if not soup:
                break

            found = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'chuong-' in href and url.rstrip('/') in href:
                    found.append(href)

            if not found:
                break

            # Deduplicate & sort by chapter number
            for href in found:
                if href not in all_urls:
                    all_urls.append(href)

            next_btn = soup.select_one('.pagination li.active + li a')
            if not next_btn:
                break
            page += 1

        # Sort ascending by chapter number
        def _ch_num(u):
            m = re.search(r'chuong-(\d+)', u)
            return int(m.group(1)) if m else 0

        all_urls = sorted(set(all_urls), key=_ch_num)
        print(f"  📖 [{self.name}] {len(all_urls)} chương")
        return all_urls

    def get_chapter_content(self, url):
        url = self._normalize_url(url)
        soup = self._soup(url)
        if not soup:
            return ''

        div = soup.find('div', id='chapter-c')
        if not div:
            return ''

        # Remove ads
        for ad in div.find_all(class_=lambda v: v and 'ads' in v):
            ad.decompose()
        for el in div.find_all(['script', 'style', 'iframe']):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                paras.append(text)

        if not paras:
            text = div.get_text('\n', strip=True)
            paras = [l.strip() for l in text.splitlines() if l.strip()]

        return '\n\n'.join(paras)
