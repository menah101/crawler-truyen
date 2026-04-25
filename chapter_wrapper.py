"""Chapter Wrapper — Sinh block editorial cho mỗi chương (intro, highlight, preview).

Giải pháp chính cho vấn đề AdSense "Low-value content": thêm nội dung **tự sinh**,
không trùng nguồn crawl → Google không gắn tag duplicate.

Mỗi chương sau khi wrap có 3 trường mới:
- summary       : 2-3 câu dẫn dắt ngay đầu chương (teaser, gợi cao trào, không spoil)
- highlight     : 1-2 câu bình luận điểm nhấn chương này (tâm lý nhân vật, twist, bối cảnh)
- next_preview  : 1 câu preview chương sau (cliffhanger giữ chân)

Dùng:
    # Batch từ thư mục chapters/*.json (ghi đè JSON với 3 field mới)
    python chapter_wrapper.py --dir docx_output/2026-04-19/ten-truyen/chapters

    # Hoặc gọi từ run.py:
    python run.py --wrap-from-dir docx_output/2026-04-19/ten-truyen

    # Wrap chapters đã có trong DB:
    python run.py --wrap-slug "ten truyen"
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


WRAPPER_PROMPT = """Bạn là biên tập viên của trang đọc truyện online "Hồng Trần Truyện". Nhiệm vụ: viết 3 block editorial ngắn cho 1 chương truyện để tăng giá trị biên tập (chống duplicate content).

⚠️ QUY TẮC NGÔN NGỮ TUYỆT ĐỐI:
- 100% tiếng Việt có dấu. KHÔNG dùng ký tự Hán/Nhật/Hàn. KHÔNG dùng dấu câu CJK (。，！？).

THÔNG TIN TRUYỆN:
Tên: {title}
Thể loại: {genres}

CHƯƠNG HIỆN TẠI (số {chapter_number} - "{chapter_title}"):
{chapter_excerpt}

{next_hint}

YÊU CẦU:
1. SUMMARY (2-3 câu, 40-80 từ): Giới thiệu chương này như trailer phim. Gợi không khí + câu hỏi để người đọc tò mò. KHÔNG tiết lộ kết thúc chương.
2. HIGHLIGHT (1-2 câu, 20-40 từ): Bình luận biên tập về điểm đáng chú ý của chương (tâm lý nhân vật / twist / chi tiết ẩn dụ / phong cách kể). Viết như editor viết review ngắn, KHÔNG tóm tắt lại nội dung.
3. NEXT_PREVIEW (1 câu, 15-25 từ): Câu nhấp cho chương sau. Nếu không có hint chương sau, đoán hợp lý dựa trên kết chương hiện tại.

FORMAT TRẢ VỀ (ĐÚNG format này, không thêm):
===SUMMARY===
[2-3 câu tiếng Việt]
===HIGHLIGHT===
[1-2 câu tiếng Việt]
===NEXT_PREVIEW===
[1 câu tiếng Việt]
"""


CJK_CHAR_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')


def _has_cjk(s: str) -> bool:
    return bool(CJK_CHAR_RE.search(s or ''))


def _excerpt(content: str, max_chars: int = 2500) -> str:
    """Lấy đoạn đầu + đoạn cuối chương để LLM nắm đủ bối cảnh mà không tốn context."""
    content = (content or '').strip()
    if len(content) <= max_chars:
        return content
    head = content[: max_chars // 2]
    tail = content[-max_chars // 2 :]
    return f"{head}\n[... lược bớt giữa chương ...]\n{tail}"


def _parse_output(raw: str) -> dict:
    out = {'summary': '', 'highlight': '', 'next_preview': ''}
    if not raw:
        return out
    sections = re.split(r'===\s*([A-Z_]+)\s*===', raw)
    # sections = ['', 'SUMMARY', 'text', 'HIGHLIGHT', 'text', 'NEXT_PREVIEW', 'text']
    for i in range(1, len(sections) - 1, 2):
        key = sections[i].strip().lower()
        val = sections[i + 1].strip()
        if key == 'summary':
            out['summary'] = val
        elif key == 'highlight':
            out['highlight'] = val
        elif key == 'next_preview':
            out['next_preview'] = val
    return out


def _dispatch_llm(prompt_text: str, provider: str) -> Optional[str]:
    """Dispatch theo provider name. Fallthrough Ollama nếu key thiếu hoặc provider lạ."""
    from config import (
        ANTHROPIC_API_KEY,
        ANTHROPIC_MODEL,
        GEMINI_API_KEY,
        GEMINI_MODEL,
        OLLAMA_BASE_URL,
        OLLAMA_MODEL,
    )
    from hook_generator import _call_anthropic, _call_gemini, _call_ollama

    if provider == 'gemini' and GEMINI_API_KEY:
        return _call_gemini(prompt_text, GEMINI_API_KEY, GEMINI_MODEL)
    if provider == 'anthropic' and ANTHROPIC_API_KEY:
        return _call_anthropic(prompt_text, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
    return _call_ollama(prompt_text, OLLAMA_BASE_URL, OLLAMA_MODEL)


def _call_llm(prompt_text: str) -> Optional[str]:
    """Provider cho REWRITE_PROVIDER — dùng trong splitter, retitle, rewriter.

    Splitter/retitle/rewriter là task tốn nhiều token nhưng yêu cầu chất lượng
    không quá cao → dùng Gemini cho rẻ.
    """
    from config import REWRITE_PROVIDER
    return _dispatch_llm(prompt_text, REWRITE_PROVIDER)


def _call_wrap_llm(prompt_text: str) -> Optional[str]:
    """Provider cho WRAP_PROVIDER — dùng trong wrap §1 + wrap §2.

    Wrap sinh content giá trị cao (review/analysis/FAQ) — dùng model mạnh
    hơn (Anthropic) để chất lượng tốt, ít CJK drift.
    """
    from config import WRAP_PROVIDER
    return _dispatch_llm(prompt_text, WRAP_PROVIDER)


def wrap_chapter(
    chapter: dict,
    *,
    novel_title: str = '',
    genres: str = '',
    next_chapter_title: str = '',
) -> dict:
    """Sinh summary/highlight/next_preview cho 1 chương.

    Args:
        chapter: dict với ít nhất {number, title, content}.
        novel_title, genres: metadata để LLM viết đúng tông.
        next_chapter_title: tên chương kế tiếp (giúp LLM viết preview sát hơn).

    Returns:
        {'summary': str, 'highlight': str, 'next_preview': str}
        Rỗng nếu LLM fail.
    """
    next_hint = (
        f'HINT CHƯƠNG KẾ TIẾP (tên): "{next_chapter_title}"'
        if next_chapter_title
        else 'Không có hint chương sau — hãy đoán dựa trên cái kết của chương hiện tại.'
    )
    prompt = WRAPPER_PROMPT.format(
        title=novel_title or '(chưa rõ)',
        genres=genres or '(chưa rõ)',
        chapter_number=chapter.get('number', '?'),
        chapter_title=chapter.get('title', '') or f"Chương {chapter.get('number', '?')}",
        chapter_excerpt=_excerpt(chapter.get('content', '')),
        next_hint=next_hint,
    )

    raw = _call_wrap_llm(prompt)
    if not raw:
        return {'summary': '', 'highlight': '', 'next_preview': ''}

    # Retry 1 lần nếu CJK drift
    if _has_cjk(raw):
        retry_prompt = (
            'LẦN TRƯỚC BẠN VIẾT LẪN CHỮ HÁN. HÃY VIẾT LẠI 100% TIẾNG VIỆT CÓ DẤU, '
            'KHÔNG MỘT KÝ TỰ HÁN/NHẬT/HÀN NÀO.\n\n' + prompt
        )
        raw2 = _call_wrap_llm(retry_prompt)
        if raw2 and not _has_cjk(raw2):
            raw = raw2
        elif raw2:
            raw = CJK_CHAR_RE.sub('', raw2)

    return _parse_output(raw)


def wrap_chapters_dir(
    chapters_dir: str,
    *,
    novel_title: str = '',
    genres: str = '',
    only_numbers: Optional[set[int]] = None,
    skip_existing: bool = True,
    sleep_sec: float = 1.0,
) -> dict:
    """Batch wrap tất cả chương JSON trong thư mục (ghi đè tại chỗ).

    Mỗi file sau khi wrap sẽ có thêm 3 key: summary, highlight, next_preview.
    """
    if not os.path.isdir(chapters_dir):
        raise FileNotFoundError(f'Thư mục không tồn tại: {chapters_dir}')

    files = sorted(glob.glob(os.path.join(chapters_dir, '*.json')))
    if not files:
        raise FileNotFoundError(f'Không có file JSON trong: {chapters_dir}')

    chapters = []
    for f in files:
        with open(f, encoding='utf-8') as fp:
            chapters.append((f, json.load(fp)))

    stats = {'total': len(chapters), 'wrapped': 0, 'skipped': 0, 'failed': 0}

    for i, (f, ch) in enumerate(chapters):
        num = ch.get('number')
        if only_numbers and num not in only_numbers:
            continue
        if skip_existing and ch.get('summary') and ch.get('highlight'):
            logger.info(f'  ⏭️  Ch.{num}: đã có wrapper, skip')
            stats['skipped'] += 1
            continue

        next_title = chapters[i + 1][1].get('title', '') if i + 1 < len(chapters) else ''

        logger.info(f'  ✍️  Ch.{num}: wrapping...')
        result = wrap_chapter(
            ch, novel_title=novel_title, genres=genres, next_chapter_title=next_title
        )

        if not result.get('summary'):
            logger.warning(f'  ❌ Ch.{num}: LLM fail')
            stats['failed'] += 1
            continue

        ch.update(result)
        tmp = f + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(ch, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, f)

        stats['wrapped'] += 1
        if sleep_sec:
            time.sleep(sleep_sec)

    return stats


def wrap_chapters_in_db(
    slug_keyword: str,
    *,
    only_numbers: Optional[set[int]] = None,
    skip_existing: bool = True,
    sleep_sec: float = 1.0,
) -> dict:
    """Wrap toàn bộ chương của 1 novel trong Prisma SQLite, update trực tiếp DB."""
    from db_helper import get_connection, get_novel_with_chapters

    conn = get_connection()
    try:
        novel, chapters = get_novel_with_chapters(conn, slug_keyword)
        if not novel:
            raise ValueError(f'Không tìm thấy truyện: {slug_keyword}')

        title = novel['title']
        genres = novel.get('genres', '') or ''
        ch_list = [dict(c) for c in chapters]

        stats = {'total': len(ch_list), 'wrapped': 0, 'skipped': 0, 'failed': 0}

        for i, ch in enumerate(ch_list):
            num = ch['number']
            if only_numbers and num not in only_numbers:
                continue
            if skip_existing and ch.get('summary') and ch.get('highlight'):
                stats['skipped'] += 1
                continue

            next_title = ch_list[i + 1]['title'] if i + 1 < len(ch_list) else ''
            logger.info(f'  ✍️  Ch.{num}: wrapping...')
            result = wrap_chapter(
                ch, novel_title=title, genres=genres, next_chapter_title=next_title
            )
            if not result.get('summary'):
                stats['failed'] += 1
                continue

            conn.execute(
                'UPDATE Chapter SET summary=?, highlight=?, nextPreview=? WHERE id=?',
                (result['summary'], result['highlight'], result['next_preview'], ch['id']),
            )
            conn.commit()
            stats['wrapped'] += 1
            if sleep_sec:
                time.sleep(sleep_sec)

        return stats
    finally:
        conn.close()


def wrap_all_chapters_in_db(
    *,
    skip_existing: bool = True,
    sleep_sec: float = 1.0,
    only_unwrapped: bool = True,
) -> dict:
    """Wrap §1 cho TOÀN BỘ novel đã published trong DB.

    Args:
        skip_existing: skip chapter đã có summary+highlight (recommended).
        only_unwrapped: chỉ loop các novel còn chapter chưa wrap (default True).
                        False = loop tất cả novel published.
    """
    from db_helper import get_connection

    conn = get_connection()
    try:
        if only_unwrapped:
            rows = conn.execute("""
                SELECT DISTINCT n.slug
                FROM Novel n
                JOIN Chapter c ON c.novelId = n.id
                WHERE n.publishStatus = 'published'
                  AND c.publishStatus = 'published'
                  AND (c.summary IS NULL OR c.summary = ''
                    OR c.highlight IS NULL OR c.highlight = '')
                ORDER BY n.slug
            """).fetchall()
        else:
            rows = conn.execute(
                "SELECT slug FROM Novel WHERE publishStatus='published' "
                "ORDER BY slug"
            ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    logger.info(f'🎯 Tìm thấy {total} truyện cần wrap §1')

    stats = {'total': total, 'wrapped': 0, 'skipped': 0, 'failed': 0,
             'chapters_wrapped': 0}
    for i, r in enumerate(rows, 1):
        slug = r['slug']
        logger.info(f'[{i}/{total}] 📖 {slug}')
        try:
            res = wrap_chapters_in_db(
                slug, skip_existing=skip_existing, sleep_sec=sleep_sec,
            )
            stats['chapters_wrapped'] += res.get('wrapped', 0)
            if res.get('failed'):
                stats['failed'] += 1
            else:
                stats['wrapped'] += 1
        except Exception as e:
            logger.exception(f'  ❌ {slug}: {e}')
            stats['failed'] += 1

    return stats


def _cli():
    ap = argparse.ArgumentParser(description='Chapter editorial wrapper (chống AdSense low-value)')
    ap.add_argument('--dir', type=str, metavar='CHAPTERS_DIR',
                    help='Thư mục chứa chapters/*.json. Chấp nhận cả novel dir lẫn chapters/ subdir.')
    ap.add_argument('--slug', type=str, metavar='KEYWORD',
                    help='Wrap chapters của truyện trong DB (khớp keyword theo slug/title)')
    ap.add_argument('--title', type=str, default='', help='Tên truyện (cho --dir)')
    ap.add_argument('--genres', type=str, default='', help='Thể loại (cho --dir)')
    ap.add_argument('--chapter', type=int, nargs='+', metavar='N',
                    help='Chỉ wrap các số chương liệt kê')
    ap.add_argument('--redo', action='store_true', help='Ghi đè wrapper đã có')
    ap.add_argument('--sleep', type=float, default=1.0, help='Giây giữa mỗi chương (rate limit)')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-7s %(message)s',
                        datefmt='%H:%M:%S')

    only = set(args.chapter) if args.chapter else None

    if args.slug:
        stats = wrap_chapters_in_db(
            args.slug, only_numbers=only, skip_existing=not args.redo, sleep_sec=args.sleep,
        )
    elif args.dir:
        d = args.dir
        if os.path.basename(d) != 'chapters' and os.path.isdir(os.path.join(d, 'chapters')):
            d = os.path.join(d, 'chapters')
        stats = wrap_chapters_dir(
            d, novel_title=args.title, genres=args.genres,
            only_numbers=only, skip_existing=not args.redo, sleep_sec=args.sleep,
        )
    else:
        ap.print_help()
        sys.exit(1)

    print()
    print(f"📊 Tổng kết: {stats}")


if __name__ == '__main__':
    _cli()
