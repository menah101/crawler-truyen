"""Novel Wrapper — Sinh editorial review + FAQ cho trang `/truyen/[slug]`.

Đi cùng `chapter_wrapper.py` để chống AdSense "Low-value content":
- `chapter_wrapper`  → tăng value cho trang chapter
- `novel_wrapper`    → tăng value cho trang novel (review, nhân vật, FAQ)

Mỗi novel sinh 3 block editorial:
- editorial_review   : 150-300 từ — giới thiệu, ưu/nhược, đối tượng phù hợp
- character_analysis : phân tích nhân vật chính (150-250 từ)
- faq                : 5-7 cặp Q&A (JSON array) — giúp render JSON-LD FAQPage
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


NOVEL_PROMPT = """Bạn là biên tập viên của "Hồng Trần Truyện". Viết 3 block editorial cho trang giới thiệu truyện — mục đích: tăng giá trị nội dung tự sinh, giúp site đạt tiêu chuẩn AdSense.

⚠️ QUY TẮC NGÔN NGỮ TUYỆT ĐỐI:
- 100% tiếng Việt có dấu. KHÔNG dùng ký tự Hán/Nhật/Hàn. KHÔNG dùng dấu câu CJK (。，！？).

THÔNG TIN TRUYỆN:
Tên: {title}
Tác giả: {author}
Thể loại: {genres}
Mô tả gốc: {description}
Số chương đã xuất bản: {chapter_count}

MẪU NỘI DUNG (trích các chương đại diện):
{excerpt}

YÊU CẦU:
1. EDITORIAL_REVIEW (150-300 từ): Review biên tập như phóng viên review sách. Gồm:
   - 1-2 câu mở: không khí truyện, cảm xúc chủ đạo.
   - Ưu điểm nổi bật (2-3 ý — văn phong, nhân vật, cốt truyện, cảm xúc).
   - Nhược điểm / lưu ý (1-2 ý — nhịp truyện, yếu tố có thể kén độc giả).
   - 1 câu kết luận: đối tượng độc giả phù hợp.
   KHÔNG spoil kết thúc. KHÔNG tóm tắt lại description.

2. CHARACTER_ANALYSIS (150-250 từ): Phân tích nhân vật chính:
   - Tên + vai trò.
   - Nét tính cách nổi bật (kèm dẫn chứng từ excerpt).
   - Hành trình tâm lý / cung bậc cảm xúc xuyên truyện.
   - Điểm khiến nhân vật này đáng nhớ hoặc gây tranh cãi.

3. FAQ (5-7 cặp Q&A): Câu hỏi người đọc hay thắc mắc. KHÔNG hỏi câu quá chung ("truyện này có hay không"). Ưu tiên:
   - Số chương / độ dài / truyện đã full chưa.
   - Kết thúc HE/BE/mở (có thể đoán dựa trên thể loại, KHÔNG spoil cụ thể).
   - Thể loại phụ, cảnh báo trigger (nếu có).
   - So sánh với truyện cùng thể loại.
   - Có audio/hóa truyện/drama không (dựa trên title nếu chưa chắc).
   Mỗi câu trả lời 2-4 câu, cụ thể, có giá trị thông tin.

FORMAT TRẢ VỀ (ĐÚNG format này, không thêm):
===EDITORIAL_REVIEW===
[150-300 từ tiếng Việt]
===CHARACTER_ANALYSIS===
[150-250 từ tiếng Việt]
===FAQ===
Q: [Câu hỏi 1]
A: [Trả lời 2-4 câu]

Q: [Câu hỏi 2]
A: [Trả lời]

[... 5-7 cặp Q&A]
"""


CJK_CHAR_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')


def _has_cjk(s: str) -> bool:
    return bool(CJK_CHAR_RE.search(s or ''))


def _call_llm(prompt_text: str) -> Optional[str]:
    """Wrap §2 dùng WRAP_PROVIDER (mặc định anthropic) — content giá trị cao."""
    from chapter_wrapper import _call_wrap_llm
    return _call_wrap_llm(prompt_text)


def _parse_faq(block: str) -> list[dict]:
    """Parse lines 'Q: ...\nA: ...' → [{q, a}, ...]."""
    faqs = []
    cur_q = None
    cur_a_lines = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^Q\s*[:.]\s*(.+)', line, re.IGNORECASE)
        if m:
            if cur_q and cur_a_lines:
                faqs.append({'q': cur_q, 'a': ' '.join(cur_a_lines).strip()})
            cur_q = m.group(1).strip()
            cur_a_lines = []
            continue
        m = re.match(r'^A\s*[:.]\s*(.+)', line, re.IGNORECASE)
        if m:
            cur_a_lines.append(m.group(1).strip())
            continue
        if cur_q is not None and cur_a_lines:
            cur_a_lines.append(line)
    if cur_q and cur_a_lines:
        faqs.append({'q': cur_q, 'a': ' '.join(cur_a_lines).strip()})
    return faqs


def _parse_output(raw: str) -> dict:
    out = {'editorial_review': '', 'character_analysis': '', 'faq': []}
    if not raw:
        return out
    parts = re.split(r'===\s*([A-Z_]+)\s*===', raw)
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip().lower()
        val = parts[i + 1].strip()
        if key == 'editorial_review':
            out['editorial_review'] = val
        elif key == 'character_analysis':
            out['character_analysis'] = val
        elif key == 'faq':
            out['faq'] = _parse_faq(val)
    return out


def _build_excerpt(chapters: list, max_chars: int = 5000) -> str:
    """Lấy mẫu từ chương đầu, giữa, cuối — giúp LLM hiểu arc toàn truyện."""
    if not chapters:
        return ''
    n = len(chapters)
    idxs = sorted({0, n // 3, 2 * n // 3, n - 1})
    selected = [chapters[i] for i in idxs if i < n]
    per = max_chars // max(len(selected), 1)
    parts = []
    for ch in selected:
        content = (ch.get('content', '') or '').strip()
        if not content:
            continue
        snippet = content[:per]
        last = max(snippet.rfind('.'), snippet.rfind('!'), snippet.rfind('?'))
        if last > per * 0.7:
            snippet = snippet[: last + 1]
        parts.append(f"[Chương {ch.get('number', '?')}]\n{snippet}")
    return '\n\n'.join(parts)


def wrap_novel(
    *,
    title: str,
    author: str = '',
    genres: str = '',
    description: str = '',
    chapters: list,
) -> dict:
    """Sinh editorial_review + character_analysis + faq cho 1 novel.

    Returns:
        {'editorial_review': str, 'character_analysis': str, 'faq': [{q, a}, ...]}
    """
    prompt = NOVEL_PROMPT.format(
        title=title or '(chưa rõ)',
        author=author or '(khuyết danh)',
        genres=genres or '(chưa rõ)',
        description=(description or '(không có)')[:500],
        chapter_count=len(chapters),
        excerpt=_build_excerpt(chapters),
    )

    raw = _call_llm(prompt)
    if not raw:
        logger.error('  ❌ LLM trả về rỗng')
        return {'editorial_review': '', 'character_analysis': '', 'faq': []}

    if _has_cjk(raw):
        logger.warning('  ⚠️  Output có CJK — retry')
        retry = _call_llm(
            'LẦN TRƯỚC BẠN VIẾT LẪN CHỮ HÁN. HÃY VIẾT LẠI 100% TIẾNG VIỆT CÓ DẤU, '
            'KHÔNG MỘT KÝ TỰ HÁN/NHẬT/HÀN NÀO.\n\n' + prompt
        )
        if retry and not _has_cjk(retry):
            raw = retry
        elif retry:
            raw = CJK_CHAR_RE.sub('', retry)

    parsed = _parse_output(raw)
    logger.info(
        f"  ✅ review: {len(parsed['editorial_review'])} chars | "
        f"character: {len(parsed['character_analysis'])} chars | "
        f"faq: {len(parsed['faq'])} items"
    )
    return parsed


def wrap_novel_from_dir(novel_dir: str) -> dict:
    """Đọc chapters/*.json + seo.txt/DB rồi wrap (không ghi vào DB)."""
    if os.path.basename(novel_dir) == 'chapters':
        novel_dir = os.path.dirname(novel_dir)

    ch_files = sorted(glob.glob(os.path.join(novel_dir, 'chapters', '*.json')))
    chapters = []
    for f in ch_files:
        with open(f, encoding='utf-8') as fp:
            chapters.append(json.load(fp))

    title = author = genres = description = ''
    seo_path = os.path.join(novel_dir, 'seo.txt')
    if os.path.exists(seo_path):
        with open(seo_path, encoding='utf-8') as fp:
            for line in fp:
                s = line.strip()
                if not title and s and not s.startswith('=') and not s.startswith('#'):
                    title = s
                m = re.search(r'The loai[:\s]+([^\s|]+)', s, re.IGNORECASE)
                if m:
                    genres = m.group(1).strip()
                m = re.search(r'Tac gia[:\s]+([^|]+)', s, re.IGNORECASE)
                if m:
                    author = m.group(1).strip()
    if not title:
        title = os.path.basename(novel_dir).replace('-', ' ').title()

    result = wrap_novel(
        title=title, author=author, genres=genres, description=description, chapters=chapters,
    )
    # Ghi vào novel_wrapper.json trong novel_dir để user kiểm tra
    out_path = os.path.join(novel_dir, 'novel_wrapper.json')
    with open(out_path, 'w', encoding='utf-8') as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    logger.info(f'  💾 Đã lưu: {out_path}')
    return result


def wrap_novel_in_db(slug_keyword: str, *, skip_existing: bool = True) -> dict:
    """Wrap + update trực tiếp các cột editorialReview/characterAnalysis/faq của Novel."""
    from db_helper import get_connection, get_novel_with_chapters

    conn = get_connection()
    try:
        novel, chapters = get_novel_with_chapters(conn, slug_keyword)
        if not novel:
            raise ValueError(f'Không tìm thấy truyện: {slug_keyword}')

        # Skip chỉ khi đã có ĐỦ cả 3 field non-empty (faq != "[]")
        existing_faq = novel.get('faq') or ''
        has_faq = bool(existing_faq) and existing_faq.strip() not in ('', '[]')
        if (skip_existing and novel.get('editorialReview')
                and novel.get('characterAnalysis') and has_faq):
            logger.info(f'  ⏭️  {novel["slug"]}: đã có đủ wrapper — skip (dùng --redo để ghi đè)')
            return {'skipped': True}

        result = wrap_novel(
            title=novel['title'],
            author=novel.get('author', ''),
            genres=novel.get('genres', ''),
            description=novel.get('description', ''),
            chapters=[dict(c) for c in chapters],
        )
        if not result.get('editorial_review'):
            logger.error('  ❌ Không sinh được review — bỏ qua update')
            return {'error': 'llm failed'}

        # Chỉ UPDATE field LLM trả về non-empty — preserve existing tốt hơn là ghi rỗng
        sets, params = [], []
        if result.get('editorial_review'):
            sets.append('editorialReview=?'); params.append(result['editorial_review'])
        else:
            logger.warning('  ⚠️ Section editorial_review trống — giữ nguyên DB')
        if result.get('character_analysis'):
            sets.append('characterAnalysis=?'); params.append(result['character_analysis'])
        else:
            logger.warning('  ⚠️ Section character_analysis trống — giữ nguyên DB')
        if result.get('faq'):
            sets.append('faq=?'); params.append(json.dumps(result['faq'], ensure_ascii=False))
        else:
            logger.warning('  ⚠️ Section faq trống — giữ nguyên DB')

        if not sets:
            logger.error('  ❌ Tất cả section trống — không update')
            return {'error': 'all sections empty'}

        params.append(novel['id'])
        conn.execute(f'UPDATE Novel SET {", ".join(sets)} WHERE id=?', params)
        conn.commit()
        logger.info(f'  💾 Đã update DB cho: {novel["slug"]}')
        return result
    finally:
        conn.close()


def wrap_all_novels_in_db(*, skip_existing: bool = True, sleep_sec: float = 2.0) -> dict:
    """Wrap toàn bộ novel đã published trong DB."""
    from db_helper import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT slug FROM Novel WHERE publishStatus='published' "
            "ORDER BY createdAt DESC"
        ).fetchall()
    finally:
        conn.close()

    stats = {'total': len(rows), 'wrapped': 0, 'skipped': 0, 'failed': 0}
    for r in rows:
        slug = r['slug']
        logger.info(f'📖 {slug}')
        try:
            res = wrap_novel_in_db(slug, skip_existing=skip_existing)
            if res.get('skipped'):
                stats['skipped'] += 1
            elif res.get('error') or not res.get('editorial_review'):
                stats['failed'] += 1
            else:
                stats['wrapped'] += 1
        except Exception as e:
            logger.exception(f'  ❌ {slug}: {e}')
            stats['failed'] += 1
        if sleep_sec:
            time.sleep(sleep_sec)
    return stats


def _cli():
    ap = argparse.ArgumentParser(description='Novel editorial wrapper (review/character/FAQ)')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--slug', type=str, help='Wrap 1 novel trong DB')
    g.add_argument('--dir', type=str, help='Wrap từ novel dir (ghi ra novel_wrapper.json)')
    g.add_argument('--all', action='store_true', help='Wrap toàn bộ novel published trong DB')
    ap.add_argument('--redo', action='store_true', help='Ghi đè wrapper đã có')
    ap.add_argument('--sleep', type=float, default=2.0, help='Giây giữa mỗi novel (chỉ --all)')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-7s %(message)s',
                        datefmt='%H:%M:%S')

    if args.all:
        stats = wrap_all_novels_in_db(skip_existing=not args.redo, sleep_sec=args.sleep)
        print(f'\n📊 Tổng kết: {stats}')
    elif args.slug:
        r = wrap_novel_in_db(args.slug, skip_existing=not args.redo)
        print(f'\n{"✅" if r.get("editorial_review") else "❌"} Done')
    elif args.dir:
        r = wrap_novel_from_dir(args.dir)
        print(f'\n{"✅" if r.get("editorial_review") else "❌"} Done')


if __name__ == '__main__':
    _cli()
