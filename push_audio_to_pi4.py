"""push_audio_to_pi4.py — Đẩy MP3 chương từ docx_output/ lên pi4.

Quét `docx_output/<date>/<slug>/audio/<voice>/chapter_NNNN.mp3`, POST lên
`/api/admin/upload-audio` (auth bằng X-Import-Secret). Pi4 sẽ upload S3 +
update Chapter.audioUrl/audioDuration.

Yêu cầu:
- Đã chạy `python tts_generator.py <slug> --voice <voice>` để có MP3.
- Novel + chapter tương ứng đã có trên pi4 (qua push_to_pi4.py).

Resume: skip MP3 nào đã có chapter.audioUrl trên pi4 (tự skip ở step lookup),
hoặc skip-on-success qua marker file `<mp3>.uploaded` (offline check).

Dùng:
    # Push 1 truyện (mặc định voice=female)
    python push_audio_to_pi4.py --slug "ten-truyen"

    # Voice khác
    python push_audio_to_pi4.py --slug "ten-truyen" --voice male

    # Push nhiều
    python push_audio_to_pi4.py --slugs t1 t2 t3 --voice female

    # Tất cả slug có audio dưới ngày X
    python push_audio_to_pi4.py --date 2026-04-27

    # Force re-upload (bỏ qua marker file)
    python push_audio_to_pi4.py --slug t1 --force

    # Dry-run preview
    python push_audio_to_pi4.py --slug t1 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

VOICES = ("female", "male")
CHAPTER_RE = re.compile(r"^chapter_(\d+)\.mp3$")


def _docx_root() -> Path:
    try:
        from config import DOCX_OUTPUT_DIR  # type: ignore
        return Path(DOCX_OUTPUT_DIR)
    except ImportError:
        return Path(__file__).parent / "docx_output"


def _find_audio_dir(slug: str, voice: str, date: str | None) -> Path | None:
    """Trả audio dir của 1 slug + voice. Nếu có nhiều ngày → dùng `date` filter."""
    root = _docx_root()
    if date:
        p = root / date / slug / "audio" / voice
        return p if p.is_dir() else None

    matches = [d for d in root.glob(f"*/{slug}/audio/{voice}") if d.is_dir()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.error(f"⚠️ {slug} có audio ở nhiều ngày — dùng --date để chọn:")
        for m in matches:
            logger.error(f"   {m}")
        return None
    return None


def _list_mp3s(audio_dir: Path) -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for f in sorted(audio_dir.glob("chapter_*.mp3")):
        m = CHAPTER_RE.match(f.name)
        if not m:
            continue
        out.append((int(m.group(1)), f))
    return out


def push_slug(
    slug: str, voice: str, date: str | None, *,
    dry_run: bool = False, sleep_sec: float = 0.3, force: bool = False,
) -> dict:
    """Push toàn bộ MP3 của 1 slug+voice. Trả stats."""
    from api_client import upload_chapter_audio

    stats = {"slug": slug, "uploaded": 0, "skipped_marker": 0, "failed": 0,
             "missing_chapter": 0, "files": 0}

    audio_dir = _find_audio_dir(slug, voice, date)
    if not audio_dir:
        logger.error(f"❌ {slug}: không tìm thấy audio/{voice}/")
        stats["failed"] = -1
        return stats

    mp3s = _list_mp3s(audio_dir)
    if not mp3s:
        logger.warning(f"⚠️ {slug}: thư mục audio/{voice}/ rỗng")
        return stats

    stats["files"] = len(mp3s)
    total_bytes = sum(p.stat().st_size for _, p in mp3s)
    logger.info(f"📤 {slug} ({voice}): {len(mp3s)} files / {total_bytes/1024/1024:.1f} MB")
    logger.info(f"   {audio_dir}")

    for i, (num, mp3) in enumerate(mp3s, 1):
        marker = mp3.with_suffix(".mp3.uploaded")
        if marker.exists() and not force:
            stats["skipped_marker"] += 1
            continue

        size_kb = mp3.stat().st_size / 1024
        logger.info(f"  [{i:>3}/{len(mp3s)}] chương {num:>4}  {size_kb:>5.0f}KB  {mp3.name}")

        if dry_run:
            continue

        try:
            res = upload_chapter_audio(slug, num, mp3)
            dur = res.get("duration")
            logger.info(f"          ✅ {dur}s  → {res.get('url','')[:80]}")
            marker.write_text(f"{res.get('url','')}\n")
            stats["uploaded"] += 1
        except RuntimeError as e:
            msg = str(e)
            if "404" in msg and "không tồn tại" in msg.lower():
                logger.warning(f"          ⚠️ chapter {num} chưa có trên pi4 — skip")
                stats["missing_chapter"] += 1
            else:
                logger.error(f"          ❌ {msg[:200]}")
                stats["failed"] += 1
        except FileNotFoundError as e:
            logger.error(f"          ❌ {e}")
            stats["failed"] += 1

        if sleep_sec and i < len(mp3s):
            time.sleep(sleep_sec)

    return stats


def find_slugs_in_date(date: str, voice: str) -> list[str]:
    root = _docx_root() / date
    if not root.is_dir():
        return []
    out = []
    for novel in sorted(root.iterdir()):
        if (novel / "audio" / voice).is_dir():
            out.append(novel.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Push MP3 chương từ docx_output/ → pi4")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="1 slug")
    g.add_argument("--slugs", nargs="+", help="nhiều slug, cách nhau bằng space")
    g.add_argument("--date", help="quét tất cả novel có audio dưới docx_output/<date>/")

    ap.add_argument("--voice", choices=VOICES, default="female",
                    help="Voice subdir cần push. Default: female")
    ap.add_argument("--date-filter", dest="date_filter",
                    help="Khi --slug/--slugs có ở nhiều ngày, ép 1 ngày cụ thể")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Bỏ qua marker .uploaded → re-upload")
    ap.add_argument("--sleep", type=float, default=0.3,
                    help="Delay giữa các upload (giây). Default: 0.3")
    args = ap.parse_args()

    if args.date:
        date_for_lookup = args.date
        slugs = find_slugs_in_date(args.date, args.voice)
        if not slugs:
            logger.info(f"(không có novel nào trong docx_output/{args.date}/ với audio/{args.voice}/)")
            return 0
        logger.info(f"🔎 {len(slugs)} slug có audio/{args.voice} dưới {args.date}\n")
    else:
        date_for_lookup = args.date_filter
        slugs = [args.slug] if args.slug else args.slugs

    total = {"uploaded": 0, "skipped_marker": 0, "failed": 0, "missing_chapter": 0, "files": 0}
    per_slug: list[dict] = []

    for s in slugs:
        st = push_slug(s, args.voice, date_for_lookup,
                       dry_run=args.dry_run, sleep_sec=args.sleep, force=args.force)
        per_slug.append(st)
        if st["failed"] >= 0:
            for k in ("uploaded", "skipped_marker", "failed", "missing_chapter", "files"):
                total[k] += st[k]
        logger.info("")

    logger.info("📊 Tổng kết:")
    logger.info(f"   Files:    {total['files']}")
    logger.info(f"   Uploaded: {total['uploaded']}")
    logger.info(f"   Skipped:  {total['skipped_marker']} (đã có marker .uploaded)")
    logger.info(f"   Missing:  {total['missing_chapter']} (chapter chưa có trên pi4)")
    logger.info(f"   Failed:   {total['failed']}")
    return 0 if total["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
