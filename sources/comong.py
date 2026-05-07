"""Adapter cho comong.info (Cổ Mộng) — WordPress + custom 'chapter' post type."""

import re
from .base import BaseSource
from .registry import registry


@registry.register('comong.info', 'comong.com', 'comong.net')
class ComOng(BaseSource):
    name = 'comong'
    base_url = 'https://comong.info'
    label = 'Cổ Mộng (comong.info)'

    # Slug đầu URL không phải truyện (loại trừ khi quét listing)
    _NON_NOVEL_SLUGS = {
        'about', 'contact', 'privacy', 'tos', 'terms',
        'category', 'tag', 'tac_gia', 'author', 'chapter',
        'page', 'feed', 'sitemap', 'tin-tuc', 'wp-login.php',
    }

    # Các trang category dùng làm fallback khi cần thêm truyện
    _CATEGORIES = [
        'hien-dai', 'co-dai', 'ngon-tinh', 'xuyen-khong',
        'cung-dau', 'linh-di', 'hao-mon', 'tien-hiep',
    ]

    # ── Helpers ──────────────────────────────────────────────────

    def _is_novel_url(self, url: str) -> bool:
        """True nếu URL có dạng https://comong.info/<slug>/ (1 segment)."""
        if not url.startswith(self.base_url + '/'):
            return False
        path = url[len(self.base_url) + 1:].rstrip('/')
        if not path or '/' in path:
            return False
        return path not in self._NON_NOVEL_SLUGS

    def _extract_boxes(self, soup) -> list[tuple[str, str]]:
        """Lấy (url, title) từ các box truyện trên trang listing."""
        out = []
        for box in soup.find_all('div', class_='box-blog-post'):
            a = box.find('a', href=True)
            heading = box.find(['h5', 'h4', 'h3', 'h2'])
            if not a or not heading:
                continue
            href = a['href']
            if not self._is_novel_url(href):
                continue
            title = heading.get_text(strip=True)
            if title:
                out.append((href, title))
        return out

    # ── get_novel_urls ───────────────────────────────────────────

    def get_novel_urls(self, max_count=80):
        """Lấy danh sách truyện từ trang chủ + các trang category (có phân trang)."""
        results, seen = [], set()

        def _scan(url: str) -> int:
            """Trả về số truyện mới thu được từ một URL listing."""
            print(f"  📡 [{self.name}] Lấy danh sách: {url}")
            soup = self._soup(url)
            if not soup:
                return 0
            added = 0
            for href, title in self._extract_boxes(soup):
                if href in seen or len(results) >= max_count:
                    continue
                seen.add(href)
                results.append((href, title))
                added += 1
            return added

        # Trang chủ
        _scan(self.base_url + '/')

        # Mỗi category: lần lượt /category/<cat>/, /page/2/, /page/3/...
        # Dừng khi 1 trang không trả thêm truyện mới (hết phân trang).
        for cat in self._CATEGORIES:
            if len(results) >= max_count:
                break
            page = 1
            while len(results) < max_count:
                url = (f'{self.base_url}/category/{cat}/' if page == 1
                       else f'{self.base_url}/category/{cat}/page/{page}/')
                if _scan(url) == 0:
                    break
                page += 1

        print(f"  📚 [{self.name}] {len(results)} truyện")
        return results

    # ── get_novel_info ───────────────────────────────────────────

    def get_novel_info(self, url):
        soup = self._soup(url)
        if not soup:
            return None

        # ── Title ──
        title = ''
        h1 = soup.select_one('h1.story-title') or soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            og = soup.find('meta', property='og:title')
            if og and og.get('content'):
                title = re.split(r'\s*[-|]\s*', og['content'])[0].strip()
        if not title:
            return None

        # ── Info block ──
        info = soup.find('div', class_='info')

        # Author: <strong>Tác giả</strong>: <span><a>...</a></span>
        author = 'Đang cập nhật'
        if info:
            tag = info.find('strong', string=re.compile(r'Tác\s*gi[aả]', re.I))
            if tag:
                span = tag.find_next('span')
                if span:
                    candidate = span.get_text(strip=True)
                    if candidate:
                        author = candidate

        # Genres: link đến /category/...
        genres_raw = []
        if info:
            tag = info.find('strong', string=re.compile(r'Thể\s*loại', re.I))
            if tag:
                span = tag.find_next('span')
                if span:
                    genres_raw = [
                        a.get_text(strip=True).lower()
                        for a in span.find_all('a', href=True)
                        if '/category/' in a['href']
                    ]
        if not genres_raw:
            genres_raw = [
                a.get_text(strip=True).lower()
                for a in soup.select('a[href*="/category/"]')
                if a.get_text(strip=True)
            ]

        # Status
        status = 'completed'
        if info:
            text = info.get_text(' ', strip=True).lower()
            if re.search(r'đang\s*(ra|cập\s*nhật)|ongoing|updating', text):
                status = 'ongoing'

        # Cover image: og:image (luôn có) hoặc img.attachment-original
        cover_image = ''
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            cover_image = og['content']
        if not cover_image:
            img = soup.select_one('div.img-inner img.attachment-original, img.attachment-original')
            if img and img.get('src'):
                src = img['src']
                cover_image = src if src.startswith('http') else self.base_url + src

        # Description: ưu tiên meta description, sau đó <p> trong section content
        desc = ''
        md = soup.find('meta', attrs={'name': 'description'})
        if md and md.get('content'):
            desc = md['content'].strip()
        if not desc:
            og_desc = soup.find('meta', property='og:description')
            if og_desc and og_desc.get('content'):
                desc = og_desc['content'].strip()

        return {
            'title': title,
            'author': author,
            'description': desc,
            'status': status,
            'cover_image': cover_image,
            'genres_raw': genres_raw,
        }

    # ── get_chapter_urls ─────────────────────────────────────────

    def get_chapter_urls(self, url):
        print(f"  📡 [{self.name}] Lấy chương: {url}")
        soup = self._soup(url)
        if not soup:
            return []

        urls, seen = [], set()
        for item in soup.find_all('div', class_='chapter-item'):
            a = item.find('a', href=True)
            if not a:
                continue
            href = a['href']
            if '/chapter/' not in href:
                continue
            if not href.startswith('http'):
                href = self.base_url + href
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)

        # Một số layout WP đảo thứ tự — đảm bảo chương 1 ở đầu
        def _ch_num(u):
            m = re.search(r'/chuong-(\d+)', u)
            return int(m.group(1)) if m else 10**9

        if len(urls) >= 2 and _ch_num(urls[0]) > _ch_num(urls[-1]):
            urls = urls[::-1]

        print(f"  📖 [{self.name}] {len(urls)} chương")
        return urls

    # ── get_chapter_content ──────────────────────────────────────

    def get_chapter_content(self, url):
        soup = self._soup(url)
        if not soup:
            return ''

        div = soup.find('div', class_='page-description')
        if not div:
            return ''

        # Bỏ các nút "Thu gọn / Xem thêm nội dung" và rác khác
        for el in div.find_all(['script', 'style', 'iframe', 'button']):
            el.decompose()
        for el in div.find_all('div', class_=re.compile(r'w2w_read_more|readmore', re.I)):
            el.decompose()

        paras = []
        for p in div.find_all('p'):
            text = p.get_text(' ', strip=True)
            text = re.sub(r'\s{2,}', ' ', text)
            if text and len(text) > 1:
                paras.append(text)

        return '\n\n'.join(paras)
