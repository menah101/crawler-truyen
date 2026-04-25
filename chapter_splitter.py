"""chapter_splitter.py — Tách chương trong DB local thành nhiều mảnh nhỏ.

Mục đích: tăng số chương cho thin novels (< MIN_CHAPTERS) để qua ngưỡng AdSense
"Low-value content". Giữ nguyên 100% nội dung gốc, chỉ cắt tại scene break
tự nhiên do LLM gợi ý. KHÔNG rewrite — đầu ra ghép lại đúng bằng đầu vào.

Dùng:
    # Split 1 truyện về target 10 chương
    python chapter_splitter.py --slug "ten truyen" --target 10

    # Preview không ghi DB
    python chapter_splitter.py --slug "ten truyen" --dry-run

    # Split tất cả thin novels (< 5 chương) về target 10
    python chapter_splitter.py --all-thin --target 10

    # Giới hạn 5 truyện đầu để test
    python chapter_splitter.py --all-thin --target 10 --max-novels 5 --dry-run

Workflow đề xuất:
    1. python chapter_splitter.py --all-thin --dry-run     # preview
    2. python chapter_splitter.py --all-thin                # apply (auto-backup DB)
    3. python audit_indexable.py                            # verify
    4. python run.py --wrap-slug "<slug>"                   # wrap §1 cho chương mới
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Min words per piece sau khi split — phải > 300 (ngưỡng audit_indexable)
# Đặt 400 cho buffer.
MIN_WORDS_PER_PIECE = 400
# Min words để chương được phép split — chương ngắn hơn giữ nguyên
MIN_WORDS_TO_SPLIT = MIN_WORDS_PER_PIECE * 2


SPLIT_PROMPT = """Bạn là biên tập viên tiểu thuyết. Hãy chia chương sau thành {n_pieces} phần TỰ NHIÊN — cắt tại scene break, chuyển cảnh, hoặc đối thoại kết thúc.

⚠️ TUYỆT ĐỐI:
- KHÔNG sửa nội dung. KHÔNG bịa thêm. CHỈ chọn vị trí cắt.
- Mỗi phần phải có nội dung mạch lạc, đủ ý.
- Phân bổ đều: mỗi phần xấp xỉ {avg_paragraphs} đoạn.

THÔNG TIN:
- Truyện: {novel_title}
- Chương: {chapter_title}
- Tổng số đoạn: {total_paragraphs}

NỘI DUNG CHƯƠNG (đánh số đoạn):
{numbered_content}

NHIỆM VỤ:
Trả về JSON đúng format sau (không markdown, không giải thích):
{{
  "splits": [<số đoạn cuối của phần 1>, <số đoạn cuối của phần 2>, ...],
  "titles": ["<tên phần 1>", "<tên phần 2>", "<tên phần 3>"]
}}

Số phần tử trong "splits" = {n_pieces} - 1 = {n_breaks}.
Số phần tử trong "titles" = {n_pieces}.
Tên phần ngắn 4-8 từ, gợi nội dung của phần đó.

VÍ DỤ với chương 20 đoạn cắt 3 phần: {{"splits": [7, 14], "titles": ["Cuộc gặp ngoài quán", "Hồi tưởng đêm mưa", "Đối mặt cuối cùng"]}}
"""


def _count_words(text: str) -> int:
    """Đếm từ tiếng Việt — split theo whitespace, đủ chính xác cho audit."""
    return len(text.split()) if text else 0


def _split_paragraphs(content: str) -> list:
    """Tách content thành paragraphs.

    Thứ tự fallback (cho trường hợp content dính liền 1 khối):
      1. \\n\\n (paragraph chuẩn)
      2. \\n (xuống dòng đơn)
      3. rewriter.split_paragraphs() — regex chèn xuống dòng tại scene break
         (sau đối thoại đóng + chữ hoa, sau dấu : trước ", v.v.)
      4. Split theo câu (.!?), gộp thành paragraph ~3-5 câu
    """
    if "\n\n" in content:
        paras = [p.strip() for p in content.split("\n\n") if p.strip()]
    else:
        paras = [p.strip() for p in content.split("\n") if p.strip()]

    # Đủ paragraph rồi → return luôn
    if len(paras) >= 5:
        return paras

    # Content quá ngắn (< 600 từ) thì không cần fallback, để caller xử lý
    if _count_words(content) < MIN_WORDS_TO_SPLIT:
        return paras

    # Fallback 3: dùng rewriter.split_paragraphs để chèn paragraph break
    try:
        from rewriter import split_paragraphs as rp_split
        reformatted = rp_split(content)
        candidate = [p.strip() for p in reformatted.split("\n\n") if p.strip()]
        if len(candidate) >= 5:
            return candidate
        # Có thể chỉ tách được \n đơn — thử
        candidate_n = [p.strip() for p in reformatted.split("\n") if p.strip()]
        if len(candidate_n) >= len(candidate):
            candidate = candidate_n
        if len(candidate) >= 5:
            return candidate
    except Exception:
        pass

    # Fallback 4: split theo câu rồi gộp
    sentences = re.split(r"(?<=[.!?…])\s+", content.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) >= 10:
        # Target ~15-20 paragraphs để LLM có chỗ chia
        chunk = max(3, len(sentences) // 18)
        return [
            " ".join(sentences[i : i + chunk])
            for i in range(0, len(sentences), chunk)
        ]

    return paras


def _compute_split_plan(chapters: list, target: int) -> list:
    """Phân bổ số mảnh cho từng chương dựa trên wordCount.

    Args:
        chapters: list dict có 'wordCount' (hoặc tự đếm từ 'content').
        target: tổng số chương mong muốn sau split.

    Returns:
        list[int]: số mảnh cho mỗi chương (>= 1, sum == target gần nhất có thể).
        None nếu không khả thi (target * MIN_WORDS_PER_PIECE > tổng từ).
    """
    word_counts = [c.get("wordCount") or _count_words(c["content"]) for c in chapters]
    total_words = sum(word_counts)

    if total_words < target * MIN_WORDS_PER_PIECE:
        return None  # không đủ từ để chia target mảnh, mỗi mảnh ≥ 400

    # Tính tỷ lệ → số mảnh tỷ lệ với wordCount
    raw = [target * w / total_words for w in word_counts]
    pieces = [max(1, round(r)) for r in raw]

    # Mỗi mảnh phải ≥ MIN_WORDS_PER_PIECE — nếu chương quá ngắn cho số mảnh đề xuất, hạ xuống
    for i, w in enumerate(word_counts):
        max_pieces = max(1, w // MIN_WORDS_PER_PIECE)
        if pieces[i] > max_pieces:
            pieces[i] = max_pieces

    # Hiệu chỉnh tổng = target (cộng dồn vào chương dài nhất nếu thiếu/thừa)
    diff = target - sum(pieces)
    if diff != 0:
        order = sorted(range(len(word_counts)), key=lambda i: -word_counts[i])
        idx = 0
        while diff != 0 and idx < len(order):
            i = order[idx]
            if diff > 0:
                # Thêm 1 mảnh nếu chương đủ chỗ
                if word_counts[i] >= (pieces[i] + 1) * MIN_WORDS_PER_PIECE:
                    pieces[i] += 1
                    diff -= 1
                else:
                    idx += 1
            else:
                # Bớt 1 mảnh nếu chương đang chia nhiều
                if pieces[i] > 1:
                    pieces[i] -= 1
                    diff += 1
                else:
                    idx += 1

    return pieces


def _build_numbered_content(paragraphs: list) -> str:
    """Đánh số đoạn để LLM tham chiếu."""
    return "\n\n".join(f"[Đoạn {i + 1}] {p}" for i, p in enumerate(paragraphs))


def _llm_find_split_points(
    novel_title: str,
    chapter_title: str,
    paragraphs: list,
    n_pieces: int,
) -> Optional[dict]:
    """Gọi LLM để tìm vị trí cắt + đặt tên cho từng phần.

    Returns:
        {'splits': [int], 'titles': [str]} — hoặc None nếu fail / rate limit.

    Tự retry tới 3 lần với exponential backoff khi gặp 429 (rate limit).
    Mọi exception khác → return None để caller fallback chia đều.
    """
    if n_pieces <= 1:
        return None

    from chapter_wrapper import _call_llm

    prompt = SPLIT_PROMPT.format(
        n_pieces=n_pieces,
        n_breaks=n_pieces - 1,
        avg_paragraphs=len(paragraphs) // n_pieces,
        novel_title=novel_title or "(chưa rõ)",
        chapter_title=chapter_title or "(chưa rõ)",
        total_paragraphs=len(paragraphs),
        numbered_content=_build_numbered_content(paragraphs),
    )

    raw = None
    for attempt in range(3):
        try:
            raw = _call_llm(prompt)
            break
        except Exception as e:
            msg = str(e)
            is_rate_limit = "429" in msg or "rate" in msg.lower()
            if is_rate_limit and attempt < 2:
                wait = 30 * (2 ** attempt)  # 30s, 60s
                logger.warning(f"    ⏳ Rate limit (429), chờ {wait}s rồi retry ({attempt + 1}/3)")
                time.sleep(wait)
                continue
            logger.warning(f"    ⚠️ LLM exception: {msg[:120]} — fallback chia đều")
            return None

    if not raw:
        return None

    # Cắt JSON ra khỏi markdown nếu có
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    splits = data.get("splits") or []
    titles = data.get("titles") or []

    if not isinstance(splits, list) or not isinstance(titles, list):
        return None
    if len(splits) != n_pieces - 1 or len(titles) != n_pieces:
        return None
    if not all(isinstance(s, int) for s in splits):
        return None
    if not all(0 < s < len(paragraphs) for s in splits):
        return None
    if splits != sorted(splits):  # phải tăng dần
        return None

    return {"splits": splits, "titles": [str(t).strip() for t in titles]}


def _fallback_even_split(paragraphs: list, n_pieces: int) -> dict:
    """Fallback: cắt đều theo số paragraph khi LLM fail."""
    step = len(paragraphs) // n_pieces
    splits = [step * (i + 1) for i in range(n_pieces - 1)]
    titles = [f"Phần {i + 1}" for i in range(n_pieces)]
    return {"splits": splits, "titles": titles}


def _apply_split(paragraphs: list, split_plan: dict) -> list:
    """Tách paragraphs thành các phần theo split_plan.

    Returns:
        list[(title, content)] — title từ LLM (không prepend chapter title gốc
        để tránh trùng lặp với cột số chương trên UI).
    """
    splits = split_plan["splits"]
    titles = split_plan["titles"]
    n_pieces = len(titles)

    pieces = []
    boundaries = [0] + splits + [len(paragraphs)]

    for i in range(n_pieces):
        start, end = boundaries[i], boundaries[i + 1]
        sub_paras = paragraphs[start:end]
        content = "\n\n".join(sub_paras)

        # Title chỉ là part_title — số chương đã hiển thị ở cột riêng,
        # không cần prepend "Chương N — " gây trùng lặp.
        part_title = titles[i] or f"Phần {i + 1}"
        pieces.append((part_title, content))

    return pieces


def _process_chapter(
    chapter: dict,
    n_pieces: int,
    novel_title: str,
) -> Optional[list]:
    """Tách 1 chương thành n_pieces. Returns list[(title, content)] hoặc None nếu fail."""
    if n_pieces <= 1:
        return [(chapter["title"], chapter["content"])]

    paragraphs = _split_paragraphs(chapter["content"])
    if len(paragraphs) < n_pieces * 2:
        logger.warning(
            f"    ⚠️ Ch.{chapter['number']}: chỉ {len(paragraphs)} đoạn — "
            f"không đủ để chia {n_pieces} phần, giữ nguyên"
        )
        return [(chapter["title"], chapter["content"])]

    plan = _llm_find_split_points(novel_title, chapter["title"], paragraphs, n_pieces)
    if plan is None:
        logger.warning(
            f"    ⚠️ Ch.{chapter['number']}: LLM fail — fallback chia đều"
        )
        plan = _fallback_even_split(paragraphs, n_pieces)

    return _apply_split(paragraphs, plan)


def _backup_db() -> str:
    """Backup prisma/dev.db → prisma/dev.db.split-bak.<ts>."""
    from db_helper import get_db_path

    src = get_db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"DB không tồn tại: {src}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{src}.split-bak.{ts}"
    shutil.copy2(src, dst)
    logger.info(f"💾 Backup DB → {dst}")
    return dst


def _generate_cuid() -> str:
    """Sinh ID giả-cuid (Prisma chấp nhận string ID bất kỳ).

    Format: c<timestamp_base36><random_base36> — đủ unique cho insert local.
    """
    import secrets

    ts = format(int(time.time() * 1000), "x")
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _replace_chapters_in_db(conn, novel_id: str, new_chapters: list) -> int:
    """Replace toàn bộ chapters của novel bằng new_chapters trong 1 transaction.

    Args:
        new_chapters: list[(title, content)] — sẽ renumber 1..N.

    Returns:
        Số chapter mới được insert.
    """
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        # Cảnh báo audio sẽ mất reference
        audio_count = cur.execute(
            "SELECT COUNT(*) FROM Chapter WHERE novelId=? AND audioUrl IS NOT NULL AND audioUrl != ''",
            (novel_id,),
        ).fetchone()[0]
        if audio_count:
            logger.warning(
                f"    ⚠️ {audio_count} chương có audio sẽ mất reference — file S3 vẫn còn"
            )

        cur.execute("DELETE FROM Chapter WHERE novelId=?", (novel_id,))

        # Prisma lưu DateTime dưới dạng Int (epoch ms), không phải string
        now_ms = int(time.time() * 1000)
        for i, (title, content) in enumerate(new_chapters, start=1):
            cur.execute(
                """INSERT INTO Chapter
                   (id, number, title, content, wordCount, novelId, viewCount,
                    publishStatus, createdAt, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, 0, 'published', ?, ?)""",
                (_generate_cuid(), i, title, content, _count_words(content),
                 novel_id, now_ms, now_ms),
            )

        conn.commit()
        return len(new_chapters)
    except Exception:
        conn.rollback()
        raise


def split_novel_in_db(
    slug_keyword: str,
    *,
    target: int = 10,
    dry_run: bool = False,
    sleep_sec: float = 1.0,
) -> dict:
    """Split toàn bộ chương của 1 novel thành `target` chương."""
    from db_helper import get_connection, get_novel_with_chapters

    conn = get_connection()
    try:
        novel, chapters = get_novel_with_chapters(conn, slug_keyword)
        if not novel:
            logger.error(f"❌ Không tìm thấy truyện: {slug_keyword}")
            return {"ok": False, "error": "not_found"}

        title = novel["title"]
        n_old = len(chapters)
        logger.info(f"\n📖 {title} ({novel['slug']}) — hiện {n_old} chương")

        if n_old >= target:
            logger.info(f"  ⏭️  đã có ≥ {target} chương, skip")
            return {"ok": True, "skipped": True, "reason": "already_enough"}

        plan = _compute_split_plan(chapters, target)
        if plan is None:
            total_words = sum(c.get("wordCount") or _count_words(c["content"])
                              for c in chapters)
            logger.warning(
                f"  ⚠️ Tổng {total_words} từ không đủ để chia {target} chương "
                f"(min {MIN_WORDS_PER_PIECE}/chương). Skip."
            )
            return {"ok": False, "skipped": True, "reason": "too_short"}

        logger.info(f"  📋 Kế hoạch split: {plan} (sum = {sum(plan)})")

        # Build danh sách chapter mới
        new_chapters = []
        for ch, n_pieces in zip(chapters, plan):
            if n_pieces == 1:
                new_chapters.append((ch["title"], ch["content"]))
                continue

            logger.info(f"  ✂️  Ch.{ch['number']} → {n_pieces} mảnh ({_count_words(ch['content'])} từ)")
            pieces = _process_chapter(ch, n_pieces, title)
            if not pieces:
                logger.error(f"    ❌ Split fail Ch.{ch['number']}, dừng để tránh DB lệch")
                return {"ok": False, "error": "split_failed"}

            new_chapters.extend(pieces)
            if sleep_sec:
                time.sleep(sleep_sec)

        # Sanity check: tổng nội dung phải xấp xỉ bằng nhau (LLM chỉ cắt, ko sửa)
        old_total = sum(_count_words(c["content"]) for c in chapters)
        new_total = sum(_count_words(c[1]) for c in new_chapters)
        if abs(old_total - new_total) > old_total * 0.02:  # > 2% lệch
            logger.error(
                f"  ❌ Sanity check FAIL: old={old_total} từ, new={new_total} từ "
                f"(lệch {abs(old_total - new_total)}). Có thể LLM đã sửa nội dung. Dừng."
            )
            return {"ok": False, "error": "content_mismatch"}

        logger.info(f"  ✅ Sanity OK: {old_total} → {new_total} từ ({len(new_chapters)} chương)")

        if dry_run:
            logger.info(f"  🔍 DRY-RUN — không ghi DB. Preview 3 title đầu:")
            for i, (t, _) in enumerate(new_chapters[:3], 1):
                logger.info(f"    {i:>2}. {t}")
            return {"ok": True, "dry_run": True, "old": n_old, "new": len(new_chapters)}

        inserted = _replace_chapters_in_db(conn, novel["id"], new_chapters)
        logger.info(f"  💾 DB updated: {n_old} → {inserted} chương")
        return {"ok": True, "old": n_old, "new": inserted}

    finally:
        conn.close()


RETITLE_PROMPT = """Đặt 1 title ngắn 4-8 từ tiếng Việt cho đoạn truyện sau, gợi nội dung chính của đoạn (ai làm gì, biến cố, cảm xúc).

⚠️ TUYỆT ĐỐI:
- KHÔNG bắt đầu bằng "Chương N", "Phần N", "Đoạn N".
- KHÔNG dấu chấm cuối, KHÔNG ngoặc kép.
- Chỉ trả 1 dòng title duy nhất, không giải thích gì thêm.

NỘI DUNG ĐOẠN TRUYỆN:
{excerpt}

TITLE:"""


def _llm_retitle_chapter(content: str) -> Optional[str]:
    """Gọi LLM xin title 4-8 từ cho 1 chương. None nếu fail."""
    from chapter_wrapper import _call_llm

    excerpt = (content or "").strip()
    if len(excerpt) > 4000:
        excerpt = excerpt[:2000] + "\n[...]\n" + excerpt[-1500:]

    prompt = RETITLE_PROMPT.format(excerpt=excerpt)

    for attempt in range(3):
        try:
            raw = _call_llm(prompt)
            break
        except Exception as e:
            msg = str(e)
            if ("429" in msg or "rate" in msg.lower()) and attempt < 2:
                wait = 30 * (2 ** attempt)
                logger.warning(f"    ⏳ Rate limit, chờ {wait}s")
                time.sleep(wait)
                continue
            logger.warning(f"    ⚠️ Retitle LLM exception: {msg[:120]}")
            return None

    if not raw:
        return None

    # Lấy dòng đầu tiên non-empty, strip dấu nháy/markdown
    for line in raw.splitlines():
        line = line.strip().strip('"').strip("'").strip("*").strip("`").strip()
        if not line or line.lower().startswith(("title:", "tiêu đề:")):
            line = line.split(":", 1)[-1].strip().strip('"').strip("'")
        if line and len(line.split()) <= 15:
            return line.rstrip(".")
    return None


def retitle_fallback_chapters(
    *, dry_run: bool = False, sleep_sec: float = 1.0,
) -> dict:
    """Tìm các chapter có title generic 'Phần N' và đặt title có nghĩa qua LLM."""
    from db_helper import get_connection

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT c.id, c.title, c.content, c.number, n.slug, n.title AS novel_title
            FROM Chapter c
            JOIN Novel n ON n.id = c.novelId
            WHERE c.title GLOB 'Phần [0-9]*'
            ORDER BY n.slug, c.number
        """).fetchall()

        total = len(rows)
        logger.info(f"🔎 Tìm thấy {total} chapter cần retitle\n")

        stats = {"total": total, "ok": 0, "failed": 0}

        for i, row in enumerate(rows, 1):
            logger.info(f"[{i}/{total}] {row['slug']} ch.{row['number']} ({row['title']})")
            new_title = _llm_retitle_chapter(row["content"])
            if not new_title:
                logger.warning(f"    ❌ LLM fail, giữ nguyên")
                stats["failed"] += 1
                continue

            logger.info(f"    ✓ {new_title}")
            if not dry_run:
                conn.execute(
                    "UPDATE Chapter SET title=? WHERE id=?",
                    (new_title, row["id"]),
                )
                conn.commit()

            stats["ok"] += 1
            if sleep_sec:
                time.sleep(sleep_sec)

        return stats
    finally:
        conn.close()


def split_all_thin(
    *,
    min_chapters: int = 5,
    target: int = 10,
    dry_run: bool = False,
    max_novels: int = 0,
    sleep_sec: float = 1.0,
) -> dict:
    """Split mọi truyện published có < min_chapters chương."""
    from db_helper import get_connection

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT n.id, n.slug, n.title, COUNT(c.id) AS cnt
            FROM Novel n
            LEFT JOIN Chapter c ON c.novelId=n.id AND c.publishStatus='published'
            WHERE n.publishStatus='published'
            GROUP BY n.id
            HAVING cnt > 0 AND cnt < ?
            ORDER BY cnt ASC, n.slug ASC
        """, (min_chapters,)).fetchall()
    finally:
        conn.close()

    total = len(rows)
    if max_novels > 0:
        rows = rows[:max_novels]

    logger.info(f"\n🎯 Tìm thấy {total} thin novels (< {min_chapters} chương). Xử lý {len(rows)}.\n")

    stats = {"total": len(rows), "ok": 0, "skipped": 0, "failed": 0, "details": []}

    for i, row in enumerate(rows, 1):
        logger.info(f"━━━ [{i}/{len(rows)}] {row['slug']} ━━━")
        try:
            result = split_novel_in_db(
                row["slug"], target=target, dry_run=dry_run, sleep_sec=sleep_sec,
            )
            stats["details"].append({"slug": row["slug"], **result})
            if result.get("skipped"):
                stats["skipped"] += 1
            elif result.get("ok"):
                stats["ok"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.exception(f"❌ Exception cho {row['slug']}: {e}")
            stats["failed"] += 1
            stats["details"].append({"slug": row["slug"], "ok": False, "error": str(e)})

    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Split chương trong DB local thành nhiều mảnh nhỏ."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="Slug/title của 1 truyện")
    g.add_argument("--all-thin", action="store_true",
                   help="Split mọi truyện < min-chapters chương")
    g.add_argument("--retitle-fallbacks", action="store_true",
                   help="Tìm chapter có title 'Phần N' và đặt title có nghĩa qua LLM")

    ap.add_argument("--target", type=int, default=10,
                    help="Số chương sau khi split (default 10)")
    ap.add_argument("--min-chapters", type=int, default=5,
                    help="Ngưỡng thin novel khi --all-thin (default 5)")
    ap.add_argument("--max-novels", type=int, default=0,
                    help="Giới hạn số truyện khi --all-thin (0 = không giới hạn)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview, không ghi DB")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Delay giây giữa các LLM call (default 1.0)")
    ap.add_argument("--no-backup", action="store_true",
                    help="Bỏ qua backup DB (cẩn thận)")

    args = ap.parse_args()

    if not args.dry_run and not args.no_backup:
        _backup_db()

    if args.slug:
        result = split_novel_in_db(
            args.slug, target=args.target,
            dry_run=args.dry_run, sleep_sec=args.sleep,
        )
        logger.info(f"\n📊 Kết quả: {json.dumps(result, ensure_ascii=False)}")
        sys.exit(0 if result.get("ok") else 1)
    elif args.retitle_fallbacks:
        stats = retitle_fallback_chapters(
            dry_run=args.dry_run, sleep_sec=args.sleep,
        )
        logger.info(
            f"\n📊 Retitle xong: {stats['ok']}/{stats['total']} OK, {stats['failed']} fail"
        )
        sys.exit(0 if stats["failed"] == 0 else 1)
    else:
        stats = split_all_thin(
            min_chapters=args.min_chapters, target=args.target,
            dry_run=args.dry_run, max_novels=args.max_novels,
            sleep_sec=args.sleep,
        )
        logger.info(
            f"\n📊 Tổng kết: {stats['ok']} OK | {stats['skipped']} skip | {stats['failed']} fail"
        )
        sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
