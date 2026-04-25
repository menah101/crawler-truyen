#!/usr/bin/env python3
"""Social media publisher — chia sẻ truyện lên Telegram / Discord / X (Twitter).

Đọc metadata truyện (title, description, cover, hashtags) rồi đăng đồng thời
lên nhiều kênh. Mỗi adapter tự kiểm tra cấu hình `.env`, tự skip nếu thiếu.

CLI:
    python social_publisher.py --from-dir docx_output/YYYY-MM-DD/ten-truyen
    python social_publisher.py --title "X" --url "..." --cover cover.jpg
    python social_publisher.py --from-dir ... --only telegram,discord
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SITE_URL, DOCX_CHANNEL_NAME  # noqa: E402

logger = logging.getLogger(__name__)

TWEET_MAX = 280
TELEGRAM_CAPTION_MAX = 1024
DISCORD_EMBED_DESC_MAX = 4096
INSTAGRAM_CAPTION_MAX = 2200
PINTEREST_DESC_MAX = 800
FACEBOOK_POST_MAX = 5000

FACEBOOK_GRAPH_VERSION = 'v19.0'


# ──────────────────────────────────────────────────────────────────
# Payload
# ──────────────────────────────────────────────────────────────────

@dataclass
class NovelPayload:
    title: str
    url: str
    description: str = ''
    cover_path: str = ''       # file local — cho Telegram/Discord/X upload
    cover_url: str = ''        # URL public — bắt buộc cho IG/Pinterest
    hashtags: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)

    def hashtag_string(self, sep: str = ' ') -> str:
        tags = [h if h.startswith('#') else f'#{h}' for h in self.hashtags]
        return sep.join(tags)


# ──────────────────────────────────────────────────────────────────
# Base adapter
# ──────────────────────────────────────────────────────────────────

class BaseAdapter:
    name: str = 'base'

    def is_configured(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def publish(self, payload: NovelPayload) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _truncate(text: str, max_len: int, suffix: str = '…') -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - len(suffix)].rstrip() + suffix


# ──────────────────────────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────────────────────────

class TelegramAdapter(BaseAdapter):
    name = 'telegram'

    def __init__(self):
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _caption(self, payload: NovelPayload) -> str:
        title = payload.title.strip()
        desc = payload.description.strip()
        url = payload.url.strip()
        tags = payload.hashtag_string()

        # HTML parse_mode: <b> bold, <a href>
        parts = [f'<b>📖 {title}</b>']
        if desc:
            parts.append('')
            parts.append(desc)
        parts.append('')
        parts.append(f'👉 <a href="{url}">Đọc truyện tại đây</a>')
        if tags:
            parts.append('')
            parts.append(tags)

        caption = '\n'.join(parts)
        return self._truncate(caption, TELEGRAM_CAPTION_MAX)

    def publish(self, payload: NovelPayload) -> dict:
        import requests

        caption = self._caption(payload)
        api = f'https://api.telegram.org/bot{self.token}'

        if payload.cover_path and os.path.exists(payload.cover_path):
            url = f'{api}/sendPhoto'
            with open(payload.cover_path, 'rb') as f:
                r = requests.post(
                    url,
                    data={
                        'chat_id': self.chat_id,
                        'caption': caption,
                        'parse_mode': 'HTML',
                    },
                    files={'photo': f},
                    timeout=60,
                )
        else:
            url = f'{api}/sendMessage'
            r = requests.post(
                url,
                data={
                    'chat_id': self.chat_id,
                    'text': caption,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': 'false',
                },
                timeout=30,
            )

        if r.status_code != 200:
            return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}'}

        data = r.json()
        if not data.get('ok'):
            return {'ok': False, 'error': data.get('description', 'unknown')}

        msg_id = data.get('result', {}).get('message_id')
        return {'ok': True, 'message_id': msg_id}


# ──────────────────────────────────────────────────────────────────
# Discord
# ──────────────────────────────────────────────────────────────────

class DiscordAdapter(BaseAdapter):
    name = 'discord'

    def __init__(self):
        self.webhook = os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
        self.username = os.environ.get('DISCORD_USERNAME', DOCX_CHANNEL_NAME) or 'Truyện Bot'

    def is_configured(self) -> bool:
        return bool(self.webhook)

    def publish(self, payload: NovelPayload) -> dict:
        import requests

        desc = self._truncate(payload.description, DISCORD_EMBED_DESC_MAX)
        embed = {
            'title': payload.title,
            'url': payload.url,
            'description': desc,
            'color': 0xE74C3C,  # đỏ sẫm — tone truyện cổ trang
        }

        if payload.hashtags:
            embed['footer'] = {'text': payload.hashtag_string(sep=' ')}

        files = None
        if payload.cover_path and os.path.exists(payload.cover_path):
            fname = os.path.basename(payload.cover_path)
            embed['image'] = {'url': f'attachment://{fname}'}
            files = {'file': (fname, open(payload.cover_path, 'rb'))}

        data = {
            'username': self.username,
            'content': f'📖 **Truyện mới:** {payload.title}',
            'embeds': [embed],
        }

        try:
            if files:
                r = requests.post(
                    self.webhook,
                    data={'payload_json': json.dumps(data)},
                    files=files,
                    timeout=60,
                )
            else:
                r = requests.post(self.webhook, json=data, timeout=30)
        finally:
            if files:
                files['file'][1].close()

        if r.status_code not in (200, 204):
            return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}'}

        return {'ok': True}


# ──────────────────────────────────────────────────────────────────
# X (Twitter)
# ──────────────────────────────────────────────────────────────────

class TwitterAdapter(BaseAdapter):
    name = 'twitter'

    def __init__(self):
        self.consumer_key = os.environ.get('TWITTER_CONSUMER_KEY', '').strip()
        self.consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET', '').strip()
        self.access_token = os.environ.get('TWITTER_ACCESS_TOKEN', '').strip()
        self.access_secret = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET', '').strip()

    def is_configured(self) -> bool:
        return all([
            self.consumer_key, self.consumer_secret,
            self.access_token, self.access_secret,
        ])

    def _tweet_text(self, payload: NovelPayload) -> str:
        # Twitter tự rút gọn URL thành 23 ký tự (t.co) → dùng URL làm cuối
        url = payload.url
        hashtags = payload.hashtag_string()

        # Budget: 280 - 23 (url) - 1 (space) - len(hashtags) - 1 = remaining cho title+desc
        budget = TWEET_MAX - 23 - 1
        if hashtags:
            budget -= len(hashtags) + 1

        body = f'📖 {payload.title}'
        if payload.description:
            body += f'\n\n{payload.description}'

        body = self._truncate(body, max(50, budget))
        parts = [body, url]
        if hashtags:
            parts.insert(1, hashtags)
        return '\n'.join(parts)

    def publish(self, payload: NovelPayload) -> dict:
        try:
            import tweepy
        except ImportError:
            return {
                'ok': False,
                'error': 'tweepy chưa cài — `pip install tweepy`',
            }

        text = self._tweet_text(payload)

        auth = tweepy.OAuth1UserHandler(
            self.consumer_key, self.consumer_secret,
            self.access_token, self.access_secret,
        )
        api_v1 = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=self.access_token,
            access_token_secret=self.access_secret,
        )

        media_ids = []
        if payload.cover_path and os.path.exists(payload.cover_path):
            try:
                media = api_v1.media_upload(filename=payload.cover_path)
                media_ids.append(media.media_id)
            except Exception as e:
                logger.warning(f'Twitter media upload failed: {e}')

        try:
            resp = client.create_tweet(
                text=text,
                media_ids=media_ids or None,
            )
        except Exception as e:
            return {'ok': False, 'error': str(e)}

        tweet_id = resp.data.get('id') if resp and resp.data else None
        return {'ok': True, 'tweet_id': tweet_id}


# ──────────────────────────────────────────────────────────────────
# Facebook Page (Graph API)
# ──────────────────────────────────────────────────────────────────

class FacebookPageAdapter(BaseAdapter):
    """Đăng lên Facebook Fanpage qua Graph API.

    Có cover_path → POST /{page_id}/photos (upload ảnh + caption).
    Không có → POST /{page_id}/feed với message + link (Facebook tự lấy OG).
    """
    name = 'facebook'

    def __init__(self):
        self.page_id = os.environ.get('FACEBOOK_PAGE_ID', '').strip()
        self.token = os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN', '').strip()

    def is_configured(self) -> bool:
        return bool(self.page_id and self.token)

    def _message(self, payload: NovelPayload) -> str:
        parts = [f'📖 {payload.title}']
        if payload.description:
            parts.append('')
            parts.append(payload.description)
        parts.append('')
        parts.append(f'👉 Đọc tại: {payload.url}')
        if payload.hashtags:
            parts.append('')
            parts.append(payload.hashtag_string())
        return self._truncate('\n'.join(parts), FACEBOOK_POST_MAX)

    def publish(self, payload: NovelPayload) -> dict:
        import requests

        msg = self._message(payload)
        base = f'https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}/{self.page_id}'

        if payload.cover_path and os.path.exists(payload.cover_path):
            with open(payload.cover_path, 'rb') as f:
                r = requests.post(
                    f'{base}/photos',
                    data={
                        'caption': msg,
                        'access_token': self.token,
                    },
                    files={'source': f},
                    timeout=60,
                )
        else:
            r = requests.post(
                f'{base}/feed',
                data={
                    'message': msg,
                    'link': payload.url,
                    'access_token': self.token,
                },
                timeout=30,
            )

        if r.status_code != 200:
            return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}'}

        data = r.json()
        post_id = data.get('post_id') or data.get('id')
        if not post_id:
            return {'ok': False, 'error': f'No post_id in response: {data}'}
        return {'ok': True, 'post_id': post_id}


# ──────────────────────────────────────────────────────────────────
# Instagram Business (Graph API, 2-step)
# ──────────────────────────────────────────────────────────────────

class InstagramAdapter(BaseAdapter):
    """Đăng ảnh lên Instagram Business account.

    Yêu cầu: IG Business phải link với 1 Facebook Page, dùng cùng
    PAGE_ACCESS_TOKEN. Ảnh phải có URL public (cover_url) — IG Graph
    API KHÔNG chấp nhận multipart upload.

    Flow:
      1. POST /{ig_user_id}/media      → trả creation_id
      2. POST /{ig_user_id}/media_publish?creation_id=...
    """
    name = 'instagram'

    def __init__(self):
        self.ig_user_id = os.environ.get('INSTAGRAM_USER_ID', '').strip()
        self.token = os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN', '').strip()

    def is_configured(self) -> bool:
        return bool(self.ig_user_id and self.token)

    def _caption(self, payload: NovelPayload) -> str:
        parts = [f'📖 {payload.title}']
        if payload.description:
            parts.append('')
            parts.append(payload.description)
        parts.append('')
        # IG không auto-link URL trong caption, nhưng vẫn show text
        parts.append(f'🔗 Link ở bio | {payload.url}')
        if payload.hashtags:
            parts.append('')
            # IG giới hạn 30 hashtag
            parts.append(' '.join(payload.hashtags[:30]))
        return self._truncate('\n'.join(parts), INSTAGRAM_CAPTION_MAX)

    def publish(self, payload: NovelPayload) -> dict:
        import requests

        if not payload.cover_url:
            return {
                'ok': False,
                'error': 'Instagram cần cover_url (URL public của ảnh bìa)',
            }

        caption = self._caption(payload)
        base = f'https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}/{self.ig_user_id}'

        # Step 1: create media container
        r1 = requests.post(
            f'{base}/media',
            data={
                'image_url': payload.cover_url,
                'caption': caption,
                'access_token': self.token,
            },
            timeout=60,
        )
        if r1.status_code != 200:
            return {'ok': False, 'error': f'create_media HTTP {r1.status_code}: {r1.text[:200]}'}

        creation_id = r1.json().get('id')
        if not creation_id:
            return {'ok': False, 'error': f'No creation_id: {r1.json()}'}

        # Step 2: publish
        r2 = requests.post(
            f'{base}/media_publish',
            data={
                'creation_id': creation_id,
                'access_token': self.token,
            },
            timeout=60,
        )
        if r2.status_code != 200:
            return {'ok': False, 'error': f'publish HTTP {r2.status_code}: {r2.text[:200]}'}

        return {'ok': True, 'media_id': r2.json().get('id')}


# ──────────────────────────────────────────────────────────────────
# Pinterest (API v5)
# ──────────────────────────────────────────────────────────────────

class PinterestAdapter(BaseAdapter):
    name = 'pinterest'

    def __init__(self):
        self.token = os.environ.get('PINTEREST_ACCESS_TOKEN', '').strip()
        self.board_id = os.environ.get('PINTEREST_BOARD_ID', '').strip()

    def is_configured(self) -> bool:
        return bool(self.token and self.board_id)

    def _description(self, payload: NovelPayload) -> str:
        parts = []
        if payload.description:
            parts.append(payload.description)
        if payload.hashtags:
            parts.append('')
            parts.append(payload.hashtag_string())
        return self._truncate('\n'.join(parts), PINTEREST_DESC_MAX)

    def publish(self, payload: NovelPayload) -> dict:
        import requests

        if not payload.cover_url:
            return {
                'ok': False,
                'error': 'Pinterest cần cover_url (URL public của ảnh)',
            }

        body = {
            'board_id': self.board_id,
            'title': self._truncate(payload.title, 100),
            'description': self._description(payload),
            'link': payload.url,
            'media_source': {
                'source_type': 'image_url',
                'url': payload.cover_url,
            },
        }

        r = requests.post(
            'https://api.pinterest.com/v5/pins',
            headers={
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            },
            json=body,
            timeout=60,
        )

        if r.status_code not in (200, 201):
            return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}'}

        return {'ok': True, 'pin_id': r.json().get('id')}


ADAPTERS = [
    TelegramAdapter,
    DiscordAdapter,
    TwitterAdapter,
    FacebookPageAdapter,
    InstagramAdapter,
    PinterestAdapter,
]


# ──────────────────────────────────────────────────────────────────
# seo.txt parser
# ──────────────────────────────────────────────────────────────────

def parse_seo_file(seo_path: str) -> dict:
    """Đọc seo.txt, trả về {title, description, hashtags}."""
    if not os.path.exists(seo_path):
        return {}

    with open(seo_path, encoding='utf-8') as f:
        text = f.read()

    def _section(name: str) -> str:
        m = re.search(
            rf'===\s*{re.escape(name)}\s*===(.+?)(?====|\Z)',
            text, re.IGNORECASE | re.DOTALL,
        )
        return m.group(1).strip() if m else ''

    # Title: first non-empty line của section TIÊU ĐỀ YOUTUBE
    titles_section = _section('TIÊU ĐỀ YOUTUBE')
    title = ''
    for line in titles_section.splitlines():
        line = line.strip().lstrip('0123456789.-) ')
        if line:
            title = line
            break

    # Description
    description = _section('MÔ TẢ')
    if not description:
        description = _section('DESCRIPTION')

    # Hashtags
    hashtags = []
    tags_section = _section('HASHTAG') or _section('TAGS')
    if tags_section:
        hashtags = re.findall(r'#[\w\u00C0-\u1EF9]+', tags_section)

    return {
        'title': title,
        'description': description,
        'hashtags': hashtags,
    }


def _lookup_cover_url_from_db(slug: str) -> str:
    """Tìm cover public URL từ DB qua slug. Trả '' nếu không có."""
    try:
        from db_helper import get_connection
    except Exception:
        return ''
    try:
        conn = get_connection()
        row = conn.execute(
            'SELECT coverImage FROM Novel WHERE slug = ? LIMIT 1',
            (slug,),
        ).fetchone()
        conn.close()
    except Exception:
        return ''

    if not row:
        return ''

    cover = row['coverImage'] if hasattr(row, 'keys') else row[0]
    if not cover:
        return ''
    if cover.startswith(('http://', 'https://')):
        return cover
    if cover.startswith('/'):
        return f'{SITE_URL.rstrip("/")}{cover}'
    return ''


def payload_from_db(slug: str, *, novel_dir: str = '') -> Optional[NovelPayload]:
    """Build payload từ DB (bảng Novel) — dùng khi không có seo.txt.

    Nếu `novel_dir` có, vẫn ưu tiên cover file local để upload cho FB/Telegram/Discord/X.
    """
    try:
        from db_helper import get_connection
    except Exception:
        return None
    try:
        conn = get_connection()
        row = conn.execute(
            'SELECT slug, title, description, coverImage, genres, tags '
            'FROM Novel WHERE slug = ? LIMIT 1',
            (slug,),
        ).fetchone()
        conn.close()
    except Exception:
        return None

    if not row:
        return None

    row = dict(row) if hasattr(row, 'keys') else row
    cover_img = row.get('coverImage') or ''
    cover_url = ''
    if cover_img.startswith(('http://', 'https://')):
        cover_url = cover_img
    elif cover_img.startswith('/'):
        cover_url = f'{SITE_URL.rstrip("/")}{cover_img}'

    cover_path = ''
    if novel_dir:
        for c in ('cover.jpg', 'cover.png', 'thumbnail_youtube.jpg'):
            p = os.path.join(novel_dir, c)
            if os.path.exists(p):
                cover_path = p
                break

    # Hashtag từ tags + genres
    tags_str = (row.get('tags') or '') + ',' + (row.get('genres') or '')
    hashtags = []
    for t in tags_str.split(','):
        t = t.strip()
        if t:
            # '#co-trang' → '#cotrang' để tránh tag bị cắt bởi dấu gạch
            hashtags.append('#' + re.sub(r'[^\w\u00C0-\u1EF9]', '', t))

    return NovelPayload(
        title=row.get('title', ''),
        url=f'{SITE_URL.rstrip("/")}/truyen/{slug}',
        description=(row.get('description') or '')[:800],
        cover_path=cover_path,
        cover_url=cover_url,
        hashtags=hashtags[:10],
    )


def payload_from_novel_dir(novel_dir: str) -> NovelPayload:
    """Ghép NovelPayload từ thư mục truyện (seo.txt + cover.jpg)."""
    novel_dir = os.path.abspath(novel_dir)
    meta = parse_seo_file(os.path.join(novel_dir, 'seo.txt'))

    slug = os.path.basename(novel_dir)
    title = meta.get('title') or slug.replace('-', ' ').title()
    # Bỏ prefix "Truyện Audio" và suffix "| Hồng Trần..."  nếu có
    title = re.sub(r'^\s*truyện audio\s*[:\-–]?\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\|.+$', '', title).strip()

    url = f'{SITE_URL.rstrip("/")}/truyen/{slug}'

    # Cover local: ưu tiên cover.jpg, fallback thumbnail đầu tiên
    cover = ''
    for candidate in ('cover.jpg', 'cover.png', 'thumbnail_youtube.jpg'):
        p = os.path.join(novel_dir, candidate)
        if os.path.exists(p):
            cover = p
            break
    if not cover:
        thumbs = sorted(glob.glob(os.path.join(novel_dir, 'thumbnails', '*')))
        if thumbs:
            cover = thumbs[0]

    # Cover URL public (cho IG/Pinterest) — lookup DB
    cover_url = _lookup_cover_url_from_db(slug)

    return NovelPayload(
        title=title,
        url=url,
        description=meta.get('description', ''),
        cover_path=cover,
        cover_url=cover_url,
        hashtags=meta.get('hashtags', []),
    )


# ──────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────

def publish_to_all(
    payload: NovelPayload,
    *,
    only: Optional[list[str]] = None,
    dry_run: bool = False,
) -> dict:
    """Đăng lên tất cả adapter đã cấu hình. Trả về dict {name: result}."""
    results: dict = {}
    for cls in ADAPTERS:
        adapter = cls()
        if only and adapter.name not in only:
            continue

        if not adapter.is_configured():
            results[adapter.name] = {'ok': False, 'skipped': True, 'reason': 'not configured'}
            logger.info(f'⏭️  {adapter.name}: chưa cấu hình (skip)')
            continue

        if dry_run:
            results[adapter.name] = {'ok': True, 'dry_run': True}
            logger.info(f'🧪 {adapter.name}: [DRY RUN] sẽ đăng "{payload.title}"')
            continue

        logger.info(f'🚀 {adapter.name}: đăng "{payload.title}"')
        try:
            results[adapter.name] = adapter.publish(payload)
        except Exception as e:
            logger.error(f'❌ {adapter.name}: {e}')
            results[adapter.name] = {'ok': False, 'error': str(e)}

        if results[adapter.name].get('ok'):
            logger.info(f'✅ {adapter.name}: OK')
        else:
            logger.warning(f'❌ {adapter.name}: {results[adapter.name].get("error", "?")}')

    return results


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def _cli():
    ap = argparse.ArgumentParser(description='Chia sẻ truyện lên MXH')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--from-dir', type=str, metavar='NOVEL_DIR',
                     help='Thư mục truyện (docx_output/YYYY-MM-DD/slug/)')
    src.add_argument('--title', type=str, help='Tiêu đề (dùng cùng --url)')

    ap.add_argument('--url', type=str, default='', help='URL truyện')
    ap.add_argument('--description', type=str, default='')
    ap.add_argument('--cover', type=str, default='', help='Đường dẫn file ảnh bìa (upload cho FB/Telegram/Discord/X)')
    ap.add_argument('--cover-url', type=str, default='', help='URL public của ảnh bìa (bắt buộc cho IG/Pinterest)')
    ap.add_argument('--hashtags', type=str, default='', help='Hashtag cách nhau bằng space')
    ap.add_argument('--only', type=str, default='',
                    help='Chỉ đăng lên 1 số adapter (VD: --only telegram,discord)')
    ap.add_argument('--dry-run', action='store_true', help='Không đăng thật, chỉ in preview')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )

    if args.from_dir:
        payload = payload_from_novel_dir(args.from_dir)
        # Override từ CLI nếu có
        if args.url:
            payload.url = args.url
        if args.cover:
            payload.cover_path = args.cover
        if args.cover_url:
            payload.cover_url = args.cover_url
        if args.description:
            payload.description = args.description
    else:
        payload = NovelPayload(
            title=args.title,
            url=args.url,
            description=args.description,
            cover_path=args.cover,
            cover_url=args.cover_url,
            hashtags=args.hashtags.split() if args.hashtags else [],
        )

    only = [x.strip() for x in args.only.split(',') if x.strip()] or None

    print()
    print('📋 Payload:')
    print(f'   Title      : {payload.title}')
    print(f'   URL        : {payload.url}')
    print(f'   Cover file : {payload.cover_path or "(none)"}')
    print(f'   Cover URL  : {payload.cover_url or "(none — IG/Pinterest sẽ skip)"}')
    print(f'   Hashtags   : {payload.hashtag_string() or "(none)"}')
    print(f'   Description: {payload.description[:80]}{"..." if len(payload.description) > 80 else ""}')
    print()

    results = publish_to_all(payload, only=only, dry_run=args.dry_run)

    print()
    print('📊 Kết quả:')
    for name, r in results.items():
        icon = '✅' if r.get('ok') else ('⏭️' if r.get('skipped') else '❌')
        extra = ''
        if r.get('dry_run'):
            extra = ' (dry run)'
        elif r.get('error'):
            extra = f' — {r["error"][:80]}'
        elif r.get('reason'):
            extra = f' — {r["reason"]}'
        print(f'   {icon} {name}{extra}')


if __name__ == '__main__':
    _cli()
