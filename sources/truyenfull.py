"""Adapter cho truyenfull.vn"""

import re
from .base import BaseSource
from .registry import registry


@registry.register('truyenfull.io', 'truyenfull.vn', 'truyenfull.com')
class TruyenFull(BaseSource):
    name = 'truyenfull'
    base_url = 'https://truyenfull.io'
    label = 'TruyenFull (truyenfull.io)'
    headers = {
        **BaseSource.headers,
        'Referer': 'https://truyenfull.io/',
    }

    # Trang danh sách truyện full
    _LIST_PAGES = [
        '/danh-sach/truyen-full/',
        '/danh-sach/truyen-moi/',
    ]

    def get_novel_urls(self, max_count=80):
        results, seen = [], set()
        for path in self._LIST_PAGES:
            page = 1
            while len(results) < max_count:
                url = self.base_url + path + (f'trang-{page}/' if page > 1 else '')
                print(f"  📡 [{self.name}] {url}")
                soup = self._soup(url)
                if not soup:
                    break

                items = soup.select('.list-truyen .row[itemtype]')
                if not items:
                    break

                for item in items:
                    a = item.select_one('h3.truyen-title a')
                    if not a:
                        continue
                    href = a.get('href', '').strip()
                    title = a.get_text(strip=True)
                    if href and title and href not in seen:
                        if not href.startswith('http'):
                            href = self.base_url + href
                        seen.add(href)
                        results.append((href, title))
                    if len(results) >= max_count:
                        break

                # Check next page
                next_btn = soup.select_one('.pagination li.active + li a')
                if not next_btn:
                    break
                page += 1

            if len(results) >= max_count:
                break

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results[:max_count]

    def get_novel_info(self, url):
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

        return {'title': title, 'author': author, 'description': desc,
                'status': status, 'cover_image': cover_image}

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        all_urls = []
        page = 1

        while True:
            page_url = url.rstrip('/') + (f'?page={page}' if page > 1 else '')
            soup = self._soup(page_url)
            if not soup:
                break

            links = soup.select('.list-chapter li a')
            if not links:
                break

            for a in links:
                href = a.get('href', '')
                if href:
                    if not href.startswith('http'):
                        href = self.base_url + href
                    all_urls.append(href)

            # Next page?
            next_btn = soup.select_one('.pagination li.active + li a')
            if not next_btn:
                break
            page += 1

        print(f"  📖 [{self.name}] {len(all_urls)} chương")
        return all_urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = soup.find('div', id='chapter-c')
        if not div:
            div = soup.select_one('.chapter-c')
        if not div:
            return ''

        for el in div.find_all(['script', 'style', 'iframe', 'button', 'ins']):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text(strip=True)
            text = re.sub(r'^\d+[.)]\s*$', '', text).strip()
            if text:
                paras.append(text)

        if not paras:
            # Fallback: split by <br>
            text = div.get_text('\n', strip=True)
            paras = [l.strip() for l in text.splitlines() if l.strip()]

        return '\n\n'.join(paras)
