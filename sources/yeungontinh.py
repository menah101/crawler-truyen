"""Adapter cho yeungontinh.baby (nguồn gốc, đã hoạt động)."""

import re
from bs4 import BeautifulSoup
from .base import BaseSource
from .registry import registry


@registry.register('yeungontinh.baby', 'yeungontinh.net', 'yeungontinh.com')
class YeunGoNTinh(BaseSource):
    name = 'yeungontinh'
    base_url = 'https://yeungontinh.baby'
    label = 'Yêung Ôn Tình (yeungontinh.baby)'

    def get_novel_urls(self, max_count=80):
        feed_url = self.base_url + '/feed/'
        print(f"  📡 [{self.name}] RSS: {feed_url}")
        r = self._get(feed_url)
        if not r:
            return []

        soup = BeautifulSoup(r.content, 'xml')
        items = soup.find_all('item') or BeautifulSoup(r.content, 'html.parser').find_all('item')

        results, seen = [], set()
        for item in items:
            title_el = item.find('title')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            href = ''
            link_el = item.find('link')
            if link_el:
                if link_el.string:
                    href = str(link_el.string).strip()
                if not href and link_el.next_sibling:
                    s = str(link_el.next_sibling).strip()
                    if s.startswith('http'):
                        href = s
                if not href:
                    href = link_el.get_text(strip=True)
            if not href:
                guid = item.find('guid')
                if guid:
                    href = guid.get_text(strip=True)

            if not href or not title or href in seen:
                continue
            if not href.startswith('http'):
                href = self.base_url + href
            seen.add(href)
            results.append((href, title))
            if len(results) >= max_count:
                break

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results

    def get_novel_info(self, url):
        soup = self._soup(url)
        if not soup:
            return None

        title = ''
        for tag in ['h1', 'h2', 'h3']:
            el = soup.find(tag)
            if el and 2 < len(el.get_text(strip=True)) < 200:
                title = el.get_text(strip=True)
                break
        if not title and soup.title:
            title = soup.title.get_text(strip=True).split('|')[0].split(' - ')[0].strip()
        if not title:
            return None

        author = 'Đang cập nhật'
        for sel in ['.author', 'a[href*="tac-gia"]']:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                author = el.get_text(strip=True)
                break

        desc = ''
        for sel in ['.desc-text', '.description', '.summary']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 10:
                desc = el.get_text(strip=True)
                break

        cover_image = ''
        for sel in ['.book-cover img', '.novel-cover img', '.thumb img', '.cover img',
                    'img.thumbnail', 'img[class*="cover"]']:
            el = soup.select_one(sel)
            if el and el.get('src'):
                cover_image = el['src']
                if not cover_image.startswith('http'):
                    cover_image = self.base_url + cover_image
                break
        if not cover_image:
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if any(k in src for k in ['cover', 'thumb', 'truyen', 'novel', 'book']):
                    cover_image = src if src.startswith('http') else self.base_url + src
                    break

        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('a[href*="the-loai"], a[href*="genre"], a[href*="category"]')
        ]

        return {'title': title, 'author': author, 'description': desc,
                'status': 'completed', 'cover_image': cover_image, 'genres_raw': genres_raw}

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        soup = self._soup(url)
        if not soup:
            return []
        links = soup.select('.chapter-item a')
        urls = []
        for a in links:
            href = a.get('href', '')
            if href:
                if not href.startswith('http'):
                    href = self.base_url + href
                urls.append(href)
        print(f"  📖 [{self.name}] {len(urls)} chương")
        return urls

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''
        # Hỗ trợ cả hai class (tuỳ phiên bản trang)
        div = soup.find('div', class_='story-content') or soup.find('div', class_='page-description')
        if not div:
            return ''
        for el in div.find_all(['script', 'style', 'iframe', 'button']):
            el.decompose()
        for el in div.find_all('div', class_='w2w_read_more'):
            el.decompose()
        paras = []
        # Thử tìm trong thẻ <p> trước
        for p in div.find_all('p'):
            text = p.get_text(strip=True)
            text = re.sub(r'^\d+[.)]\s*$', '', text)
            text = re.sub(r'^\d+$', '', text).strip()
            if text:
                paras.append(text)
        # Nếu không có <p>, lấy từ thẻ <div> con (trang dùng <div> thay <p>)
        if not paras:
            for child in div.find_all('div', recursive=False):
                text = child.get_text(strip=True)
                text = re.sub(r'^\d+[.)]\s*$', '', text)
                text = re.sub(r'^\d+$', '', text).strip()
                if text:
                    paras.append(text)
        return '\n\n'.join(paras)
