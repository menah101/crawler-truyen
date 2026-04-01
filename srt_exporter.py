"""
srt_exporter.py — Chuyen file DOCX da xuat sang SRT (phu de).

Su dung sau khi save_novel_as_docx() da tao xong file .docx.
Dung khi SRT_EXPORT_ENABLED = True trong config.py.
"""

import os
import logging

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Chuyen giay sang dinh dang SRT: HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    s  = int(seconds) % 60
    m  = int(seconds // 60) % 60
    h  = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_into_chunks(text: str, words_per_chunk: int) -> list:
    """Tach van ban thanh cac doan nho theo so tu."""
    words = text.split()
    return [
        ' '.join(words[i:i + words_per_chunk])
        for i in range(0, len(words), words_per_chunk)
        if words[i:i + words_per_chunk]
    ]


def docx_text_to_srt(
    text: str,
    output_file: str,
    duration_per_line: float = 20.0,
    words_per_second: float = 0.25,
) -> None:
    """Chuyen chuoi van ban thanh file SRT."""
    words_per_chunk = max(1, int(duration_per_line * words_per_second))
    chunks = _split_into_chunks(text, words_per_chunk)

    out_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(out_dir, exist_ok=True)

    current_time = 0.0
    with open(output_file, 'w', encoding='utf-8') as f:
        for idx, chunk in enumerate(chunks, start=1):
            word_count = len(chunk.split())
            duration   = word_count / words_per_second
            start      = current_time
            end        = current_time + duration
            f.write(f"{idx}\n")
            f.write(f"{_format_time(start)} --> {_format_time(end)}\n")
            f.write(f"{chunk}\n\n")
            current_time = end


def convert_docx_to_srt(
    input_file: str,
    output_file: str,
    duration_per_line: float = 20.0,
    words_per_second: float = 0.25,
) -> bool:
    """
    Chuyen file DOCX sang SRT. Tra ve True neu thanh cong.

    Args:
        input_file:        Duong dan file .docx nguon
        output_file:       Duong dan file .srt dau ra
        duration_per_line: Thoi luong toi da moi dong phu de (giay)
        words_per_second:  So tu doc moi giay (de tinh thoi gian)

    Returns:
        True neu thanh cong, False neu loi.
    """
    try:
        from docx import Document
    except ImportError:
        logger.error("Thieu thu vien python-docx. Chay: pip install python-docx")
        return False

    from docx_exporter import clean_text

    if not os.path.exists(input_file):
        logger.error(f"Khong tim thay file DOCX: {input_file}")
        return False

    try:
        doc = Document(input_file)
        full_text = ' '.join(
            clean_text(p.text)
            for p in doc.paragraphs
            if p.text.strip()
        )
        logger.info(f"  Da xu ly van ban tu: {input_file}")
    except Exception as e:
        logger.error(f"Loi khi doc file DOCX: {e}")
        return False

    if not full_text.strip():
        logger.warning("Van ban rong sau khi lam sach.")
        return False

    try:
        docx_text_to_srt(full_text, output_file, duration_per_line, words_per_second)
        logger.info(f"  Da xuat SRT: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Loi khi chuyen doi SRT: {e}")
        return False
