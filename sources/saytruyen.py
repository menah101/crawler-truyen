"""Adapter cho saytruyen.com.vn / saytruyen.vn"""

import re
from .base import BaseSource
from .registry import registry


@registry.register('saytruyen.vn', 'saytruyen.com.vn', 'saytruyen.com', 'saytruyen.net')
class SayTruyen(BaseSource):
    name = 'saytruyen'
    base_url = 'https://saytruyen.vn'
    label = 'SayTruyen (saytruyen.com.vn)'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
        'Referer': 'https://saytruyen.vn/',
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

            items = soup.select('.story-detail__item a.story-detail__item--title, '
                                '.book-item a[href*="/truyen/"]')
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

            next_btn = soup.select_one('.pagination .next a, li.active + li a')
            if not next_btn:
                break
            page += 1

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results[:max_count]

    def get_novel_info(self, url):
        soup = self._soup(url)
        if not soup:
            return None

        # Title: h3.story-name (primary), fallback to img[alt] in thumbnail
        title = ''
        el = soup.select_one('h3.story-name')
        if el:
            title = el.get_text(strip=True)
        if not title:
            img = soup.select_one('.story-detail__top--image img[alt]')
            if img:
                title = img.get('alt', '').strip()
        if not title:
            return None

        # Author: first hover-title link inside the info block
        author = 'Đang cập nhật'
        info_block = soup.select_one('.story-detail__bottom--info')
        if info_block:
            # First <p> contains "Tác giả: <a>..."
            for p in info_block.select('p'):
                a = p.select_one('a.hover-title')
                if a:
                    author = a.get_text(strip=True)
                    break

        # Description
        desc = ''
        el = soup.select_one('.story-detail__top--desc')
        if el and len(el.get_text(strip=True)) > 10:
            desc = el.get_text(strip=True)

        # Cover image
        cover_image = ''
        img = soup.select_one('.story-detail__top--image img')
        if img:
            src = img.get('src', '')
            if src:
                cover_image = src if src.startswith('http') else self.base_url + src

        # Status
        status = 'completed'
        if info_block:
            text = info_block.get_text(strip=True).lower()
            if 'đang ra' in text or 'đang cập nhật' in text or 'ongoing' in text:
                status = 'ongoing'

        # Genres
        genres_raw = []
        if info_block:
            for a in info_block.select('a.hover-title'):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                # Skip author name (first link) and chapter links
                if '/the-loai/' in href or (text and text not in (author,)):
                    genres_raw.append(text)

        return {'title': title, 'author': author, 'description': desc,
                'status': status, 'cover_image': cover_image, 'genres_raw': genres_raw}

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        soup = self._soup(url)
        if not soup:
            return []

        links = soup.select('div.story-detail__list-chapter--list a')
        # Chỉ lấy link chương/ngoại truyện
        links = [a for a in links
                 if a.get('href') and ('/chuong-' in a['href'] or '/ngoai-truyen' in a['href'])]

        urls = []
        for a in links:
            href = a['href']
            if not href.startswith('http'):
                href = self.base_url + href
            urls.append(href)

        # Đảo ngược: chương 1 lên đầu
        urls = urls[::-1]
        print(f"  📖 [{self.name}] {len(urls)} chương")
        return urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = soup.find('div', class_='chapter-content')
        if not div:
            return ''

        for el in div.find_all(['div', 'script', 'style', 'iframe', 'button']):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text().strip()
            if text and len(text) > 5:
                paras.append(text)

        return '\n\n'.join(paras)
