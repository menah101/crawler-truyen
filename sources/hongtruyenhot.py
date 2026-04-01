"""Adapter cho hongtruyenhot.net."""

import re
import time
from bs4 import BeautifulSoup
from .base import BaseSource
from .registry import registry


@registry.register('hongtruyenhot.net', 'hongtruyenhot.com')
class HongTruyenHot(BaseSource):
    name = 'hongtruyenhot'
    base_url = 'https://hongtruyenhot.net'
    label = 'Hồng Truyện Hot (hongtruyenhot.net)'

    # ── Tiện ích nội bộ ───────────────────────────────────────────

    def _extract_slug(self, url: str) -> str:
        """
        Lấy slug truyện từ URL (detail hoặc chapter).

        /truyen/ten-truyen-ht       → ten-truyen-ht
        /ten-truyen-ht/chuong-5     → ten-truyen-ht
        """
        url = url.rstrip('/')
        path = url.replace(self.base_url, '').lstrip('/')

        if path.startswith('truyen/'):
            return path[len('truyen/'):]

        # URL chương: slug/chuong-N
        if '/chuong-' in path:
            return path.split('/chuong-')[0]

        return path

    def _detail_url(self, slug: str) -> str:
        return f"{self.base_url}/truyen/{slug}"

    def _chapter_url(self, slug: str, n: int) -> str:
        return f"{self.base_url}/{slug}/chuong-{n}"

    # ── get_novel_urls ────────────────────────────────────────────

    def get_novel_urls(self, max_count=80):
        """
        Lấy danh sách truyện từ trang chủ và trang truyện mới.
        Trả về [(detail_url, title), ...]
        """
        results, seen = [], set()

        feed_pages = [
            self.base_url,
            f"{self.base_url}/truyen-moi",
        ]

        for page_url in feed_pages:
            print(f"  📡 [{self.name}] Lấy danh sách: {page_url}")
            soup = self._soup(page_url)
            if not soup:
                continue

            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/truyen/' not in href and 'story-item' not in str(a.parent):
                    continue
                # Chuẩn hoá URL detail
                if not href.startswith('http'):
                    href = self.base_url + href
                if 'hongtruyenhot' not in href:
                    continue
                # Chỉ lấy detail page, bỏ chapter URL
                if '/chuong-' in href:
                    # Chuyển về detail URL
                    slug = self._extract_slug(href)
                    href = self._detail_url(slug)

                if href in seen:
                    continue

                # Lấy title từ thẻ h3/h4 gần nhất hoặc text của link
                title = ''
                for tag in [a.find('h3'), a.find('h4'), a.find('h2')]:
                    if tag:
                        title = tag.get_text(strip=True)
                        break
                if not title:
                    title = a.get_text(strip=True)
                if not title or len(title) < 2:
                    continue

                # Bỏ suffix -ht, -HT
                title = re.sub(r'\s*-\s*[Hh][Tt]\s*$', '', title).strip()

                seen.add(href)
                results.append((href, title))
                if len(results) >= max_count:
                    break

            if len(results) >= max_count:
                break

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results

    # ── get_novel_info ────────────────────────────────────────────

    def get_novel_info(self, url: str) -> dict | None:
        """
        Lấy thông tin truyện từ detail page hoặc chapter URL.
        Trả về dict: title, author, description, status, cover_image, genres_raw
        """
        slug = self._extract_slug(url)
        detail_url = self._detail_url(slug)

        soup = self._soup(detail_url)
        if not soup:
            # Fallback: thử lấy từ chương đầu
            soup = self._soup(self._chapter_url(slug, 1))
            if not soup:
                return None

        # ── Title ────────────────────────────────────────────────
        title = ''
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Bỏ suffix -ht / -HT / " | Site name"
            title = re.sub(r'\s*-\s*[Hh][Tt]\s*$', '', title).strip()
            title = re.split(r'\s*\|\s*', title)[0].strip()

        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)

        if not title:
            return None

        # ── Author ───────────────────────────────────────────────
        author = 'Đang cập nhật'
        # Pattern: <strong>Tác giả:</strong> ... <a href="#">Author</a>
        tac_gia = soup.find(string=re.compile(r'Tác\s*gi[aả]', re.IGNORECASE))
        if tac_gia:
            parent = tac_gia.find_parent()
            if parent:
                # Tìm <a> anh em gần nhất
                sibling = parent.find_next_sibling()
                if sibling:
                    a_tag = sibling.find('a') or sibling
                    candidate = a_tag.get_text(strip=True) if a_tag else ''
                    if candidate and len(candidate) > 1:
                        author = candidate
                else:
                    # Tìm trong container cha
                    container = parent.find_parent()
                    if container:
                        a_tag = container.find('a', href='#')
                        if a_tag:
                            author = a_tag.get_text(strip=True) or author

        # ── Genres ───────────────────────────────────────────────
        genres_raw = [
            a.get_text(strip=True).lower()
            for a in soup.select('a[href*="/the-loai/"]')
        ]

        # ── Cover image ──────────────────────────────────────────
        cover_image = ''
        for sel in ['img[src*="stories"]', 'img[src*="cover"]',
                    '.book-cover img', '.novel-cover img', '.thumb img']:
            el = soup.select_one(sel)
            if el and el.get('src'):
                src = el['src']
                cover_image = src if src.startswith('http') else self.base_url + src
                break

        # ── Description ──────────────────────────────────────────
        desc = ''
        for sel in ['.description', '.desc', '.synopsis', '.summary',
                    '[class*="desc"]', '[class*="synopsis"]']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 20:
                desc = el.get_text(strip=True)
                break

        # ── Status ───────────────────────────────────────────────
        status = 'completed'
        status_text = soup.get_text()
        if re.search(r'đang\s*cập\s*nhật|ongoing|updating', status_text, re.IGNORECASE):
            status = 'ongoing'

        return {
            'title': title,
            'author': author,
            'description': desc,
            'status': status,
            'cover_image': cover_image,
            'genres_raw': genres_raw,
        }

    # ── get_chapter_urls ─────────────────────────────────────────

    def get_chapter_urls(self, url: str) -> list[str]:
        """
        Lấy danh sách URL tất cả các chương theo thứ tự.

        Chiến lược:
        1. Lấy slug từ URL
        2. Fetch chapter 1 để xác định slug thực tế (phòng redirect)
        3. Lấy số chương tối đa từ select dropdown
        4. Build URL danh sách: /slug/chuong-1 ... /slug/chuong-max
        """
        print(f"  📡 [{self.name}] Lấy danh sách chương: {url}")
        slug = self._extract_slug(url)

        # Fetch chương đầu để lấy max chapter từ dropdown
        ch1_url = self._chapter_url(slug, 1)
        soup = self._soup(ch1_url)
        if not soup:
            return []

        # Lấy max chapter từ tất cả <option value="N">
        opts = soup.find_all('option', value=re.compile(r'^\d+$'))
        chapter_nums = [int(o['value']) for o in opts if o['value'].isdigit()]
        max_ch = max(chapter_nums) if chapter_nums else 1

        # Xác nhận slug thực tế từ canonical link (phòng redirect)
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            real_slug = self._extract_slug(canonical['href'])
            if real_slug and real_slug != slug:
                print(f"  🔀 Slug redirect: {slug} → {real_slug}")
                slug = real_slug

        urls = [self._chapter_url(slug, n) for n in range(1, max_ch + 1)]
        print(f"  📖 [{self.name}] {len(urls)} chương (1 → {max_ch})")
        return urls

    # ── get_chapter_content ───────────────────────────────────────

    def get_chapter_content(self, url: str) -> str:
        """
        Lấy nội dung text thuần của 1 chương.

        Cấu trúc trang:
          <div class="chapter-wrapper">
            <div class="chapter-nav">...</div>          ← nav trên
            <div class="chapter-actions ...">...</div>  ← nút điều hướng
            <p>...</p>                                  ← NỘI DUNG
            <p>...</p>
            ...
            <div class="chapter-nav">...</div>          ← nav dưới
          </div>
        """
        soup = self._soup(url)
        if not soup:
            return ''

        wrapper = soup.find('div', class_='chapter-wrapper')
        if not wrapper:
            return ''

        # Tìm div chapter-actions (nav buttons) để lấy điểm bắt đầu nội dung
        actions = wrapper.find('div', class_=re.compile(r'chapter-actions'))
        if not actions:
            return ''

        # Lấy tất cả <p> sau chapter-actions và trước chapter-nav thứ hai
        paras = []
        found_actions = False
        found_second_nav = False

        for el in wrapper.children:
            if el == actions:
                found_actions = True
                continue
            if not found_actions:
                continue
            if hasattr(el, 'get') and 'chapter-nav' in el.get('class', []):
                found_second_nav = True
                break
            # Lấy tất cả <p> trong element này
            if hasattr(el, 'find_all'):
                for p in el.find_all('p', recursive=True):
                    # Xoá các thẻ rác bên trong
                    for junk in p.find_all(['script', 'style', 'span.ads']):
                        junk.decompose()
                    text = p.get_text(strip=True)
                    text = re.sub(r'\s{2,}', ' ', text)
                    if text and len(text) > 1:
                        paras.append(text)
            elif hasattr(el, 'strip') and el.strip():
                # TextNode
                text = el.strip()
                if len(text) > 5:
                    paras.append(text)

        if not paras:
            # Fallback: parse thô bằng regex (khi BeautifulSoup children không đúng thứ tự)
            html = str(wrapper)
            idx_actions = html.find('chapter-actions')
            if idx_actions >= 0:
                after = html[html.find('</div>', idx_actions) + 6:]
                idx_nav2 = after.find('chapter-nav')
                content_html = after[:idx_nav2] if idx_nav2 > 0 else after[:30000]
                raw_paras = re.findall(r'<p[^>]*>(.*?)</p>', content_html, re.DOTALL)
                for raw in raw_paras:
                    text = re.sub(r'<[^>]+>', '', raw).strip()
                    text = re.sub(r'\s{2,}', ' ', text)
                    if text and len(text) > 1:
                        paras.append(text)

        return '\n\n'.join(paras)
