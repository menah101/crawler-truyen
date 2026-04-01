"""Adapter cho metruyencv.com"""

import re
from .base import BaseSource
from .registry import registry


@registry.register('metruyencv.com', 'www.metruyencv.com', 'metruyencv.net')
class MeTruyenCV(BaseSource):
    name = 'metruyencv'
    base_url = 'https://metruyencv.com'
    label = 'MeTruyenCV (metruyencv.com)'
    headers = {
        **BaseSource.headers,
        'Referer': 'https://metruyencv.com/',
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

            items = soup.select('.book-item h3 a, .truyen-item a.truyen-title, .list-truyen h3 a')
            if not items:
                break

            for a in items:
                href = a.get('href', '').strip()
                title = a.get_text(strip=True) or a.get('title', '').strip()
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
        for sel in ['h1.truyen-title', 'h1', '.title']:
            el = soup.select_one(sel)
            if el and 2 < len(el.get_text(strip=True)) < 200:
                title = el.get_text(strip=True)
                break
        if not title and soup.title:
            title = soup.title.get_text(strip=True).split('|')[0].strip()
        if not title:
            return None

        author = 'Đang cập nhật'
        for sel in ['.author a', 'a[href*="tac-gia"]', '.info-author']:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                author = el.get_text(strip=True)
                break

        desc = ''
        for sel in ['.description', '.summary-content', '.desc-text', '[itemprop="description"]']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 10:
                desc = el.get_text(strip=True)
                break

        cover_image = ''
        for sel in ['.book-cover img', '.thumb img', '.cover img', 'img[itemprop="image"]']:
            el = soup.select_one(sel)
            if el:
                src = el.get('src') or el.get('data-src', '')
                if src:
                    cover_image = src if src.startswith('http') else self.base_url + src
                    break

        status = 'completed'
        for el in soup.select('.info span, .label-success, .label-primary'):
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
        all_urls = []
        page = 1

        while True:
            page_url = url.rstrip('/') + f'?page={page}'
            soup = self._soup(page_url)
            if not soup:
                break

            links = soup.select('.list-chapter a, .chapter-list a, ul.list li a')
            if not links:
                break

            found = 0
            for a in links:
                href = a.get('href', '')
                if '/chuong-' in href or '/chapter-' in href:
                    if not href.startswith('http'):
                        href = self.base_url + href
                    if href not in all_urls:
                        all_urls.append(href)
                        found += 1

            if found == 0:
                break

            next_btn = soup.select_one('.pagination .next a, .pagination li.active + li a')
            if not next_btn:
                break
            page += 1

        print(f"  📖 [{self.name}] {len(all_urls)} chương")
        return all_urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = None
        for sel in ['#chapter-content', '.chapter-content', '#viet-content', '.reading-content']:
            div = soup.select_one(sel)
            if div:
                break
        if not div:
            return ''

        for el in div.find_all(['script', 'style', 'iframe', 'ins', 'button']):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text(strip=True)
            text = re.sub(r'^\d+[.)]\s*$', '', text).strip()
            if text:
                paras.append(text)

        if not paras:
            text = div.get_text('\n', strip=True)
            paras = [line.strip() for line in text.splitlines() if line.strip()]

        return '\n\n'.join(paras)
