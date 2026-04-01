"""
Scraper cho yeungontinh.baby — dựa trên code gốc đã hoạt động.
"""

import requests
from bs4 import BeautifulSoup
import re


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Referer': 'https://yeungontinh.baby/'
}
TIMEOUT = 10
BASE_URL = 'https://yeungontinh.baby'


def _make_request(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request error: {e}")
        return None


FEED_URL = BASE_URL + '/feed/'


def get_novel_urls(max_count=80):
    """Get novels from RSS feed — reliable, clean URLs + titles."""
    print(f"  📡 Fetching RSS feed: {FEED_URL}")
    response = _make_request(FEED_URL)
    if not response:
        return []

    # Parse RSS XML
    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')

    if not items:
        # Fallback: parse as HTML if xml parser fails
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('item')

    results = []
    seen = set()

    for item in items:
        title_el = item.find('title')
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # WordPress RSS: <link> text can be .string, .next_sibling, or inside CDATA
        href = ''
        link_el = item.find('link')
        if link_el:
            # Try .string first
            if link_el.string:
                href = str(link_el.string).strip()
            # WordPress often puts URL as text node after <link> tag
            if not href and link_el.next_sibling:
                sibling = str(link_el.next_sibling).strip()
                if sibling.startswith('http'):
                    href = sibling
            # Try get_text
            if not href:
                href = link_el.get_text(strip=True)

        # Also try <guid> as fallback
        if not href:
            guid_el = item.find('guid')
            if guid_el:
                href = guid_el.get_text(strip=True)

        if not href or not title or href in seen:
            continue

        # Clean URL
        href = href.strip()
        if not href.startswith('http'):
            href = BASE_URL + href

        seen.add(href)
        results.append((href, title))

        if len(results) >= max_count:
            break

    print(f"  📚 Found {len(results)} novels from feed")
    return results


def get_novel_info(main_url):
    """Lấy thông tin truyện (title có dấu, author...)."""
    response = _make_request(main_url)
    if not response:
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # Title
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

    # Author
    author = 'Đang cập nhật'
    for sel in ['.author', 'a[href*="tac-gia"]']:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            author = el.get_text(strip=True)
            break

    # Description
    desc = ''
    for sel in ['.desc-text', '.description', '.summary']:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 10:
            desc = el.get_text(strip=True)
            break

    # Cover image
    cover_image = ''
    for sel in ['.book-cover img', '.novel-cover img', '.thumb img', '.cover img', 'img.thumbnail', 'img[class*="cover"]']:
        el = soup.select_one(sel)
        if el and el.get('src'):
            cover_image = el['src']
            if not cover_image.startswith('http'):
                cover_image = BASE_URL + cover_image
            break
    if not cover_image:
        # Fallback: find first img with a plausible cover URL
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if any(k in src for k in ['cover', 'thumb', 'truyen', 'novel', 'book']):
                cover_image = src if src.startswith('http') else BASE_URL + src
                break

    return {
        'title': title,
        'author': author,
        'description': desc,
        'status': 'completed',
        'cover_image': cover_image,
    }


def get_chapter_urls(main_url):
    """Lấy danh sách URL chương."""
    print(f"  📡 Lấy danh sách chương: {main_url}")
    response = _make_request(main_url)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    chapter_links = soup.select('.chapter-item a')

    urls = []
    for link in chapter_links:
        url = link.get('href')
        if url:
            if not url.startswith('http'):
                url = BASE_URL + url
            urls.append(url)

    print(f"  📖 Tìm thấy {len(urls)} chương")
    return urls


def get_chapter_content(chapter_url):
    """Lấy nội dung chương."""
    print(f"  📥 Tải chương: {chapter_url}")
    response = _make_request(chapter_url)
    if not response:
        return ""

    soup = BeautifulSoup(response.text, 'html.parser')
    content_div = soup.find('div', class_='page-description')
    if not content_div:
        return ""

    for element in content_div.find_all(['script', 'style', 'iframe', 'button']):
        element.decompose()
    for element in content_div.find_all('div', class_='w2w_read_more'):
        element.decompose()

    paragraphs = []
    for p in content_div.find_all('p'):
        text = p.get_text(strip=True)
        if text:
            # Strip standalone section numbers: "1", "2.", "I.", etc.
            text = re.sub(r'^\d+[.)]\s*$', '', text)
            text = re.sub(r'^\d+$', '', text)
            text = text.strip()
            if text:
                paragraphs.append(text)

    return "\n\n".join(paragraphs)
