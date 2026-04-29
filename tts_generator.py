"""
TTS generator — chuyển chapter JSON/TXT → MP3 per-chapter bằng Microsoft Edge TTS.

Usage:
  python tts_generator.py <novel-dir>            # đọc cả thư mục chapters/
  python tts_generator.py <slug>                 # tìm slug trong docx_output/
  python tts_generator.py path/to/file.txt       # 1 file → 1 mp3 cùng tên
  python tts_generator.py --list                 # liệt kê novel có sẵn

Tùy chọn:
  --voice female|male   giọng nữ HoaiMy / giọng nam NamMinh (default female)
  --rate -10%           tốc độ so với default (default -5% — chậm hơn 1 chút)

Hỗ trợ chapter format trong <novel>/chapters/:
  • *.json — {number, title, content}
  • *.txt  — text thuần, number lấy từ tên file (vd 0001.txt → chương 1)

Output:
  <novel-dir>/audio/<voice>/chapter_0001.mp3
  <novel-dir>/audio/<voice>/chapter_0002.mp3
  …

Resume: bỏ qua chapter nào đã có MP3 (size > 1KB).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

import edge_tts

logger = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male":   "vi-VN-NamMinhNeural",
}

DEFAULT_RATE = "+0%"          # MS Edge đang reject rate âm intermittent → giữ ở 0
MIN_MP3_BYTES = 1024          # dưới 1KB coi như file hỏng → regenerate
TTS_RETRIES   = 3             # retry NoAudioReceived (Edge TTS hay flaky)
TTS_RETRY_DELAY = 1.5         # giây giữa các lần retry


def _clean_text(raw: str) -> str:
    """
    Làm sạch nội dung chương trước khi feed vào TTS.
    - Gộp các dòng `"\\n\\n` thành dấu nháy kép dính liền
    - Loại khoảng trắng thừa, dòng trống lặp
    - Chuẩn hoá newline → 1 dòng trống phân cách đoạn
    """
    if not raw:
        return ""
    # Gộp pattern `"\n\n` (dấu mở/đóng dialogue bị crawler tách dòng)
    text = re.sub(r'"\s*\n\s*\n\s*', '"', raw)
    text = re.sub(r'\n\s*\n\s*"', '"', text)
    # Gộp \n liên tiếp → tối đa 1 dòng trống
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim từng dòng
    text = "\n".join(line.strip() for line in text.splitlines())
    # Xoá dòng trống ở đầu/cuối
    return text.strip()


def _build_chapter_text(ch: dict) -> str:
    title = (ch.get("title") or "").strip()
    content = _clean_text(ch.get("content") or "")
    if title and content:
        # Một khoảng lặng ngắn giữa tiêu đề và nội dung
        return f"{title}.\n\n{content}"
    return content or title


async def _tts_to_file(text: str, voice: str, rate: str, out_path: Path) -> bool:
    """Gọi edge-tts, lưu ra MP3. Trả True nếu file > MIN_MP3_BYTES.

    Retry tối đa TTS_RETRIES lần khi NoAudioReceived (Edge TTS hay flaky,
    đặc biệt với rate âm — server đôi khi reject ngẫu nhiên).
    """
    tmp_path = out_path.with_suffix(".mp3.part")

    last_err: Exception | None = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate)
            await comm.save(str(tmp_path))
            last_err = None
            break
        except Exception as e:
            last_err = e
            if tmp_path.exists():
                tmp_path.unlink()
            if attempt < TTS_RETRIES:
                logger.warning(f"  ⏳ attempt {attempt}/{TTS_RETRIES} fail ({str(e)[:60]}) — retry sau {TTS_RETRY_DELAY}s")
                await asyncio.sleep(TTS_RETRY_DELAY)

    if last_err is not None:
        logger.error(f"  ❌ edge-tts fail (sau {TTS_RETRIES} lần): {last_err}")
        return False

    if not tmp_path.exists() or tmp_path.stat().st_size < MIN_MP3_BYTES:
        logger.error(f"  ❌ MP3 rỗng hoặc quá nhỏ (< {MIN_MP3_BYTES}B)")
        if tmp_path.exists():
            tmp_path.unlink()
        return False

    tmp_path.rename(out_path)
    return True


def _load_chapter_file(p: Path) -> tuple[int | None, dict]:
    """
    Đọc 1 file chapter (.json hoặc .txt). Trả (number, chapter_dict).
    - JSON: {number, title, content} — dùng nguyên số chương từ JSON.
    - TXT : text thuần — number lấy từ stem file (vd 0001.txt → 1),
            title để rỗng, content là toàn bộ nội dung file.
    Nếu parse fail trả (None, {}).
    """
    suffix = p.suffix.lower()
    try:
        if suffix == ".json":
            ch = json.loads(p.read_text(encoding="utf-8"))
            num = ch.get("number")
            if not isinstance(num, int):
                stem_digits = p.stem.lstrip("0") or "0"
                try:
                    num = int(stem_digits)
                except ValueError:
                    return None, {}
            return num, ch
        if suffix == ".txt":
            content = p.read_text(encoding="utf-8")
            stem_digits = p.stem.lstrip("0") or "0"
            try:
                num = int(stem_digits)
            except ValueError:
                # Tên file không phải số → vẫn TTS được nhưng không đánh số chương.
                return 0, {"number": 0, "title": p.stem, "content": content}
            return num, {"number": num, "title": "", "content": content}
    except Exception as e:
        logger.warning(f"  ⚠️ {p.name}: {e}")
    return None, {}


async def generate_novel(novel_dir: Path, voice_key: str, rate: str) -> tuple[int, int]:
    """
    Chạy TTS cho mọi chapter JSON/TXT trong novel_dir/chapters/.
    Trả (done, skipped).
    """
    voice = VOICES[voice_key]
    chapters_dir = novel_dir / "chapters"
    if not chapters_dir.is_dir():
        logger.error(f"❌ Không tìm thấy {chapters_dir}")
        return 0, 0

    out_dir = novel_dir / "audio" / voice_key
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ưu tiên .json; với mỗi stem chỉ lấy 1 file (.json > .txt)
    by_stem: dict[str, Path] = {}
    for ext in (".json", ".txt"):
        for p in chapters_dir.glob(f"*{ext}"):
            by_stem.setdefault(p.stem, p)
    chapter_files = sorted(by_stem.values(), key=lambda p: p.name)

    if not chapter_files:
        logger.error(f"❌ Không có chapter .json/.txt trong {chapters_dir}")
        return 0, 0

    logger.info(f"📚 {novel_dir.name}: {len(chapter_files)} chương → {out_dir}")
    logger.info(f"   Voice: {voice} ({voice_key})  |  Rate: {rate}")

    done = 0
    skipped = 0
    for cf in chapter_files:
        num, ch = _load_chapter_file(cf)
        if num is None:
            logger.warning(f"  ⚠️ {cf.name}: không xác định được số chương — bỏ qua")
            continue

        out_path = out_dir / f"chapter_{num:04d}.mp3"
        if out_path.exists() and out_path.stat().st_size >= MIN_MP3_BYTES:
            skipped += 1
            continue

        text = _build_chapter_text(ch)
        if not text:
            logger.warning(f"  ⚠️ Chương {num}: nội dung rỗng")
            continue

        logger.info(f"  🔊 Chương {num:4d}  ({len(text):>6,} chars)  → {out_path.name}")
        ok = await _tts_to_file(text, voice, rate, out_path)
        if ok:
            size_kb = out_path.stat().st_size / 1024
            logger.info(f"     ✅ {size_kb:.0f}KB")
            done += 1

    logger.info(f"🏁 Xong: {done} mới, {skipped} đã có sẵn")
    return done, skipped


async def generate_single_file(text_path: Path, voice_key: str, rate: str) -> bool:
    """
    Convert 1 file văn bản (.txt / .json) → 1 mp3 cùng thư mục, cùng tên.
    """
    voice = VOICES[voice_key]
    num, ch = _load_chapter_file(text_path)
    if not ch:
        logger.error(f"❌ Không đọc được {text_path}")
        return False

    text = _build_chapter_text(ch)
    if not text:
        logger.error(f"❌ Nội dung rỗng: {text_path}")
        return False

    out_path = text_path.with_suffix(f".{voice_key}.mp3")
    logger.info(f"🔊 {text_path.name} ({len(text):,} chars) → {out_path.name}")
    logger.info(f"   Voice: {voice}  |  Rate: {rate}")
    ok = await _tts_to_file(text, voice, rate, out_path)
    if ok:
        size_kb = out_path.stat().st_size / 1024
        logger.info(f"✅ {out_path}  ({size_kb:.0f}KB)")
    return ok


def _find_novel(arg: str) -> Path | None:
    """Accept absolute path HOẶC slug (tìm dưới docx_output/)."""
    p = Path(arg)
    if p.is_absolute() and p.is_dir():
        return p

    try:
        from config import DOCX_OUTPUT_DIR  # type: ignore
        root = Path(DOCX_OUTPUT_DIR)
    except ImportError:
        root = Path(__file__).parent / "docx_output"

    if (root / arg).is_dir():
        return root / arg

    # Tìm slug trong subdirs của mỗi ngày
    matches = list(root.glob(f"*/{arg}"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.error(f"Trùng tên {arg} trong nhiều ngày:")
        for m in matches:
            logger.error(f"  - {m}")
        return None
    return None


def _list_novels() -> None:
    try:
        from config import DOCX_OUTPUT_DIR  # type: ignore
        root = Path(DOCX_OUTPUT_DIR)
    except ImportError:
        root = Path(__file__).parent / "docx_output"

    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        for novel in sorted(date_dir.iterdir()):
            if novel.is_dir() and (novel / "chapters").is_dir():
                n = len(list((novel / "chapters").glob("*.json")))
                print(f"{date_dir.name}/{novel.name}  ({n} chương)")


def main() -> int:
    parser = argparse.ArgumentParser(description="TTS cho truyện bằng Microsoft Edge TTS")
    parser.add_argument("target", nargs="?", help="Path tuyệt đối, hoặc slug novel")
    parser.add_argument("--voice", choices=["female", "male"], default="female",
                        help="Giọng nữ (HoaiMy) hay nam (NamMinh). Default: female")
    parser.add_argument("--rate", default=DEFAULT_RATE,
                        help="Tốc độ so với default (vd -10%%, +5%%). Default: -5%%")
    parser.add_argument("--list", action="store_true", help="Liệt kê tất cả novel trong docx_output")
    args = parser.parse_args()

    if args.list:
        _list_novels()
        return 0

    if not args.target:
        parser.print_help()
        return 1

    # Single file mode: target trỏ thẳng tới 1 file .txt/.json
    target_path = Path(args.target)
    if target_path.is_file() and target_path.suffix.lower() in (".txt", ".json"):
        ok = asyncio.run(generate_single_file(target_path, args.voice, args.rate))
        return 0 if ok else 1

    novel_dir = _find_novel(args.target)
    if not novel_dir:
        logger.error(f"❌ Không tìm thấy novel/file: {args.target}")
        logger.error("   Chạy `--list` để xem danh sách")
        return 1

    asyncio.run(generate_novel(novel_dir, args.voice, args.rate))
    return 0


if __name__ == "__main__":
    sys.exit(main())
