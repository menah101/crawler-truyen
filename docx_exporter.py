"""
docx_exporter.py — Xuất truyện đã viết lại ra file DOCX.

Cấu trúc giống hệt file mẫu vuong_phu_tam_bao.docx:
  - Normal style: Times New Roman 13pt
  - Lời chào → dòng trống → đoạn văn → dòng trống → ... → lời kết
  - KHÔNG có tiêu đề chương, KHÔNG dùng heading
  - align=LEFT, space_after=Pt(6) cho mỗi đoạn nội dung

Dùng khi DOCX_EXPORT_ENABLED = True trong config.py.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Slug ASCII để đặt tên file."""
    VIET = {
        'à':'a','á':'a','ả':'a','ã':'a','ạ':'a',
        'ă':'a','ắ':'a','ằ':'a','ẳ':'a','ẵ':'a','ặ':'a',
        'â':'a','ấ':'a','ầ':'a','ẩ':'a','ẫ':'a','ậ':'a',
        'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e',
        'ê':'e','ế':'e','ề':'e','ể':'e','ễ':'e','ệ':'e',
        'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
        'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o',
        'ô':'o','ố':'o','ồ':'o','ổ':'o','ỗ':'o','ộ':'o',
        'ơ':'o','ớ':'o','ờ':'o','ở':'o','ỡ':'o','ợ':'o',
        'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u',
        'ư':'u','ứ':'u','ừ':'u','ử':'u','ữ':'u','ự':'u',
        'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y','đ':'d',
    }
    t = text.lower()
    t = ''.join(VIET.get(c, c) for c in t)
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')[:80]


def clean_text(text: str) -> str:
    """Làm sạch nội dung trước khi xuất DOCX: xóa tiêu đề chương, ký tự rác, thay từ nhạy cảm."""
    if not text:
        return text

    VIETNAMESE_CHARS = r'a-zA-ZÀ-ÁÂÃÈ-ÉÊÌ-ÍÒ-ÓÔÕÙ-ÚĂĐĨŨƠà-áâãè-éêì-íò-óôõù-úăđĩũơƯ-ưẠ-Ỹỳ-ỷỹ'
    VIETNAMESE_WORD  = f'[{VIETNAMESE_CHARS}0-9_]'

    # Xóa dòng tiêu đề chương (Chương 1, chương II, ...)
    text = re.sub(
        r'(?im)^[^\S\r\n]*chương\s+([IVXLCDM]+|\d+)(\s*[:\-–—.]?\s*.*)?\s*$',
        '', text,
    )
    # Xóa dòng "—HẾT—" và biến thể
    text = re.sub(
        r'(?im)^[^\S\r\n]*[-–—~*\[\](【】]?\s*H[EÉẾ][Tt]\s*[-–—~*\[\](【】]?\s*$',
        '', text,
    )
    # Xóa số đứng đầu dòng trước chữ hoa (VD: "1 Tôi" → "Tôi")
    text = re.sub(
        r'(?im)^\s*\d+\s+(?=[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ][a-zàáâãèéêìíòóôõùúăđĩũơưạ-ỹ])',
        '', text,
    )
    # Xóa dòng chỉ chứa dấu gạch (_____, --------, ════════)
    text = re.sub(r'(?im)^[^\S\r\n]*[-_─—═=]{3,}\s*$', '', text)
    # Xóa dòng "số.Chữ" (VD: "9.Sáng", "12.Hôm nay")
    text = re.sub(
        r'(?im)^[^\S\r\n]*\d+\.[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ].*$',
        '', text,
    )
    # Gộp nhiều dòng trống
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Xóa dấu chấm trong từ (VD: "T.i.ế.n" → "Tiến")
    def remove_dots_in_word(match):
        return match.group(1).replace('.', '')
    text = re.sub(rf'(\b[{VIETNAMESE_CHARS}]+\.[{VIETNAMESE_CHARS}\.]+\b)', remove_dots_in_word, text)

    # Xóa "***g"
    text = re.sub(r'\s*\*{{3}}g\s*', ' ', text)

    # Xóa Mathematical Alphanumeric Symbols và Emoji
    text = re.sub(r'[\U0001D400-\U0001D7FF]', '', text)
    text = re.sub(r'[\U0001F300-\U0001FAFF]', '', text)

    # Thay từ nhạy cảm
    replacement_map = {
        r'\bchó má\b':    'ngu ngốc',
        r'\bchết\b':      'chít',
        r'\bgiết\b':      'xử',
        r'\bchém\b':      'xém',
        r'\bmáu\b':       'huyết',
        r'\bmáu me\b':    'thảm khốc',
        r'\bmáu lạnh\b':  'tàn nhẫn',
        r'\buống máu\b':  'hút cạn sinh lực',
        r'\bngực\b':      'vòng một',
        r'blogger':       'bờ lóc gơ',
        r'vlog':          'vi lóc',
        r'audio':         'au đi ô',
    }
    for pattern, replacement in replacement_map.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Tách câu bị dính liền: "nhẫnGió" → "nhẫn\nGió" (chữ thường + chữ HOA liền nhau)
    # Chỉ tách khi chữ trước KHÔNG phải tên riêng nước ngoài thường gặp
    _VIET_LOWER = r'[a-zàáảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]'
    _VIET_UPPER = r'[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴĐ]'
    text = re.sub(
        rf'({_VIET_LOWER})({_VIET_UPPER})',
        r'\1\n\2', text,
    )

    # Xóa ký tự đặc biệt không hợp lệ (giữ nguyên \n để tách đoạn)
    text = re.sub(rf'[^{VIETNAMESE_WORD}\s.,!?\'\"""\'\'…\-–—:;()\[\]{{}}\n]', '', text)
    # Gộp nhiều space trên cùng dòng (KHÔNG gộp \n)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Gộp nhiều \n liên tiếp thành 1
    text = re.sub(r'\n+', '\n', text).strip()

    return text


def _add_para(doc, text: str, space_after_pt: float = 6.0):
    """Thêm 1 đoạn văn LEFT-align, space_after=space_after_pt pt."""
    from docx.shared import Pt
    from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    p = doc.add_paragraph(text)
    p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    p.paragraph_format.space_after = Pt(space_after_pt)
    return p


CHAR_LIMIT = 60_000   # ký tự tối đa mỗi file DOCX


def _write_docx(
    slug: str,
    part: int | None,
    title: str,
    author: str,
    chapters: list,
    output_dir: str,
    channel_name: str,
    total_parts: int,
) -> str:
    """Ghi một file DOCX cho một nhóm chương. Trả về đường dẫn file."""
    from docx import Document
    from docx.shared import Pt

    suffix   = f"_p{part}" if part is not None else ""
    out_path = os.path.join(output_dir, f"{slug}{suffix}.docx")

    doc   = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(13)

    # ── Lời chào ───────────────────────────────────────────────────────────
    doc.add_paragraph()

    if channel_name:
        if part is not None:
            greeting = (
                f"Chào mừng các bạn đến với {channel_name}. "
                f"Chúc các bạn nghe truyện vui vẻ. "
                f"(Phần {part}/{total_parts})"
            )
        else:
            greeting = (
                f"Chào mừng các bạn đến với {channel_name}. "
                f"Chúc các bạn nghe truyện vui vẻ."
            )
    else:
        greeting = f"{title} — {author}"
        if part is not None:
            greeting += f" (Phần {part}/{total_parts})"

    _add_para(doc, greeting)
    doc.add_paragraph()

    # ── Nội dung ───────────────────────────────────────────────────────────
    for ch in chapters:
        content = clean_text(ch.get('content', ''))
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                _add_para(doc, stripped)
                doc.add_paragraph()

    # ── Lời kết ────────────────────────────────────────────────────────────
    if part is not None and part < total_parts:
        ending = (
            f"Hết phần {part}. Mời các bạn nghe tiếp phần {part + 1}."
            + (f" Nhớ like và đăng ký kênh {channel_name}." if channel_name else "")
        )
    else:
        ending = (
            f"Hoàn văn. Nhớ like và đăng ký kênh {channel_name} để nghe nhiều chuyện ngôn tình hay."
            if channel_name
            else "Hoàn văn."
        )
    _add_para(doc, ending)

    doc.save(out_path)
    return out_path


def stage_chapters(title: str, chapters: list, output_dir: str) -> str:
    """
    Lưu từng chương vào staging folder (JSON) để build DOCX sau.
    Trả về đường dẫn staging folder.

    Staging folder: <output_dir>/<slug>/chapters/<num:04d>.json
    """
    import json

    slug        = _slugify(title)
    stage_dir   = os.path.join(output_dir, slug, 'chapters')
    os.makedirs(stage_dir, exist_ok=True)

    for ch in chapters:
        num      = ch.get('number', 0)
        filename = os.path.join(stage_dir, f"{num:04d}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(ch, f, ensure_ascii=False, indent=2)

    logger.info(f"  📂 Staged {len(chapters)} chương → {stage_dir}")
    return stage_dir


def load_staged_chapters(title: str, output_dir: str) -> list:
    """
    Đọc tất cả chương đã staged, sort theo số chương.
    Trả về list chapters đã sort.
    """
    import json

    slug      = _slugify(title)
    stage_dir = os.path.join(output_dir, slug, 'chapters')

    if not os.path.isdir(stage_dir):
        return []

    chapters = []
    for fname in sorted(os.listdir(stage_dir)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(stage_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                chapters.append(json.load(f))
        except Exception as e:
            logger.warning(f"  ⚠️ Không đọc được {fname}: {e}")

    # Sort theo số chương (đề phòng tên file bị lệch)
    chapters.sort(key=lambda c: c.get('number', 0))
    return chapters


def build_docx_from_staged(
    title: str,
    author: str,
    output_dir: str,
    channel_name: str = '',
) -> list[str] | None:
    """
    Đọc tất cả staged chapters, sort theo số chương, rồi build DOCX.
    Xóa các file DOCX cũ của truyện trước khi build lại.
    Trả về list đường dẫn file DOCX đã tạo.
    """
    chapters = load_staged_chapters(title, output_dir)
    if not chapters:
        logger.warning(f"  ⚠️ Không có chương nào trong staging cho '{title}'")
        return None

    logger.info(f"  🔨 Build DOCX từ {len(chapters)} chương đã staged (sort theo số chương)...")
    return _build_docx(title, author, chapters, output_dir, channel_name)


def _build_docx(
    title: str,
    author: str,
    chapters: list,
    output_dir: str,
    channel_name: str = '',
) -> list[str] | None:
    """
    Build DOCX từ danh sách chương (đã được sort trước).
    Tự động tách file nếu vượt CHAR_LIMIT.
    Xóa các file DOCX cũ trước khi ghi mới.
    """
    try:
        import docx as _docx_check  # noqa: F401
    except ImportError:
        logger.error("❌ Thiếu thư viện python-docx. Chạy: pip install python-docx")
        return None

    slug       = _slugify(title)
    novel_dir  = os.path.join(output_dir, slug)
    os.makedirs(novel_dir, exist_ok=True)

    # Xóa các file DOCX cũ để tránh phần thừa sau khi rebuild
    # Dùng try/except để không crash nếu file đang mở hoặc bị khóa
    for f in os.listdir(novel_dir):
        if f.endswith('.docx') and not f.startswith('~$'):
            try:
                os.remove(os.path.join(novel_dir, f))
            except OSError as e:
                logger.warning(f"  ⚠️ Không thể xóa DOCX cũ {f}: {e}")

    total_chars = sum(len(ch.get('content', '')) for ch in chapters)

    if total_chars <= CHAR_LIMIT:
        out_path = _write_docx(slug, None, title, author, chapters, novel_dir, channel_name, 1)
        logger.info(f"  📄 DOCX: {out_path}  ({len(chapters)} chương, {total_chars:,} ký tự)")
        return [out_path]

    # Tách thành nhiều phần theo CHAR_LIMIT
    groups: list[list] = []
    current_group: list = []
    current_chars = 0

    for ch in chapters:
        ch_len = len(ch.get('content', ''))
        if current_group and current_chars + ch_len > CHAR_LIMIT:
            groups.append(current_group)
            current_group = []
            current_chars = 0
        current_group.append(ch)
        current_chars += ch_len
    if current_group:
        groups.append(current_group)

    total_parts = len(groups)
    out_paths: list[str] = []

    for idx, group in enumerate(groups, start=1):
        out_path = _write_docx(slug, idx, title, author, group, novel_dir, channel_name, total_parts)
        group_chars = sum(len(ch.get('content', '')) for ch in group)
        logger.info(
            f"  📄 DOCX phần {idx}/{total_parts}: {out_path}"
            f"  ({len(group)} chương, {group_chars:,} ký tự)"
        )
        out_paths.append(out_path)

    return out_paths


def save_novel_as_docx(
    title: str,
    author: str,
    chapters: list,
    output_dir: str,
    channel_name: str = '',
) -> list[str] | None:
    """
    Stage các chương mới rồi build lại toàn bộ DOCX từ staged chapters.
    Đảm bảo DOCX luôn được sort theo số chương và đúng giới hạn ký tự.
    """
    # 1. Stage các chương mới (ghi đè nếu đã có)
    stage_chapters(title, chapters, output_dir)

    # 2. Load tất cả staged chapters (bao gồm cả cũ + mới), đã sort
    all_chapters = load_staged_chapters(title, output_dir)

    # 3. Build lại toàn bộ DOCX
    return _build_docx(title, author, all_chapters, output_dir, channel_name)
