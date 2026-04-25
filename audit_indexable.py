"""
Audit indexable content — liệt kê truyện/chương có nguy cơ bị AdSense / Google
gắn nhãn "Low-value content" hoặc "Soft 404".

Các signal kiểm tra:
  1. Novel có < MIN_CHAPTERS chương published → thin content.
  2. Novel thiếu editorialReview / characterAnalysis / faq → chưa qua wrapper §2.
  3. Chapter published nhưng thiếu summary + highlight → chưa qua wrapper §1.
  4. Chapter có wordCount < MIN_WORDS → teaser-level, ít content.
  5. Novel có description rỗng hoặc < 80 ký tự → metadata nghèo.

Chạy:
    python audit_indexable.py              # report tổng thể
    python audit_indexable.py --json       # xuất JSON
    python audit_indexable.py --min-chapters 5 --min-words 300
"""

import argparse
import json
import sys
from db_helper import get_connection


MIN_CHAPTERS_DEFAULT = 5
MIN_WORDS_DEFAULT = 300
MIN_DESC_LEN = 80


def audit(min_chapters: int, min_words: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    novels = cur.execute("""
        SELECT id, slug, title, description,
               editorialReview, characterAnalysis, faq,
               publishStatus
        FROM Novel
    """).fetchall()

    chapter_counts = dict(cur.execute("""
        SELECT novelId, COUNT(*)
        FROM Chapter
        WHERE publishStatus = 'published'
        GROUP BY novelId
    """).fetchall())

    thin_novels = []
    unwrapped_novels = []
    weak_description = []

    for n in novels:
        if n["publishStatus"] != "published":
            continue
        count = chapter_counts.get(n["id"], 0)
        if count < min_chapters:
            thin_novels.append({
                "slug": n["slug"], "title": n["title"], "chapters": count,
            })
        if not n["editorialReview"] or not n["characterAnalysis"] or not n["faq"]:
            unwrapped_novels.append({
                "slug": n["slug"], "title": n["title"],
                "hasReview": bool(n["editorialReview"]),
                "hasAnalysis": bool(n["characterAnalysis"]),
                "hasFaq": bool(n["faq"]),
            })
        if not n["description"] or len(n["description"]) < MIN_DESC_LEN:
            weak_description.append({
                "slug": n["slug"], "title": n["title"],
                "descLen": len(n["description"] or ""),
            })

    unwrapped_chapters = cur.execute("""
        SELECT c.id, c.number, c.title, c.wordCount,
               n.slug AS novelSlug, n.title AS novelTitle
        FROM Chapter c
        JOIN Novel n ON n.id = c.novelId
        WHERE c.publishStatus = 'published'
          AND (c.summary IS NULL OR c.summary = ''
            OR c.highlight IS NULL OR c.highlight = '')
        ORDER BY n.slug, c.number
    """).fetchall()

    short_chapters = cur.execute("""
        SELECT c.number, c.title, c.wordCount,
               n.slug AS novelSlug, n.title AS novelTitle
        FROM Chapter c
        JOIN Novel n ON n.id = c.novelId
        WHERE c.publishStatus = 'published'
          AND c.wordCount < ?
        ORDER BY c.wordCount ASC
        LIMIT 200
    """, (min_words,)).fetchall()

    conn.close()

    return {
        "thinNovels": thin_novels,
        "unwrappedNovels": unwrapped_novels,
        "weakDescription": weak_description,
        "unwrappedChapters": [dict(r) for r in unwrapped_chapters],
        "shortChapters": [dict(r) for r in short_chapters],
        "thresholds": {
            "minChapters": min_chapters,
            "minWords": min_words,
            "minDescLen": MIN_DESC_LEN,
        },
    }


def print_report(r: dict) -> None:
    t = r["thresholds"]
    print(f"\n{'=' * 60}")
    print(f"  AUDIT INDEXABLE — ngưỡng: {t['minChapters']} chương, "
          f"{t['minWords']} từ/chương, {t['minDescLen']} ký tự desc")
    print(f"{'=' * 60}\n")

    print(f"[1] Thin novels (< {t['minChapters']} chương): {len(r['thinNovels'])}")
    for n in r["thinNovels"][:20]:
        print(f"    - {n['slug']:<40} {n['chapters']} ch.  ({n['title']})")
    if len(r["thinNovels"]) > 20:
        print(f"    ... và {len(r['thinNovels']) - 20} truyện khác")

    print(f"\n[2] Novel chưa wrap editorial §2: {len(r['unwrappedNovels'])}")
    for n in r["unwrappedNovels"][:20]:
        missing = []
        if not n["hasReview"]: missing.append("review")
        if not n["hasAnalysis"]: missing.append("analysis")
        if not n["hasFaq"]: missing.append("faq")
        print(f"    - {n['slug']:<40} thiếu: {', '.join(missing)}")
    if len(r["unwrappedNovels"]) > 20:
        print(f"    ... và {len(r['unwrappedNovels']) - 20} truyện khác")

    print(f"\n[3] Novel có description yếu (< {t['minDescLen']} ký tự): {len(r['weakDescription'])}")
    for n in r["weakDescription"][:10]:
        print(f"    - {n['slug']:<40} {n['descLen']} ký tự")

    print(f"\n[4] Chapter chưa wrap §1: {len(r['unwrappedChapters'])}")
    by_novel = {}
    for c in r["unwrappedChapters"]:
        by_novel.setdefault(c["novelSlug"], 0)
        by_novel[c["novelSlug"]] += 1
    for slug, count in sorted(by_novel.items(), key=lambda x: -x[1])[:15]:
        print(f"    - {slug:<40} {count} chương")

    print(f"\n[5] Chapter ngắn (< {t['minWords']} từ): {len(r['shortChapters'])}")
    for c in r["shortChapters"][:10]:
        print(f"    - {c['novelSlug']}/chuong/{c['number']:<5} {c['wordCount']} từ")

    print(f"\n{'-' * 60}")
    print("Khuyến nghị:")
    if r["thinNovels"]:
        print(f"  • Ẩn {len(r['thinNovels'])} truyện < {t['minChapters']} chương "
              f"(đổi publishStatus='pending') hoặc bổ sung nội dung.")
    if r["unwrappedNovels"]:
        print(f"  • Chạy: python run.py --review-all  # wrap §2 cho "
              f"{len(r['unwrappedNovels'])} truyện")
    if r["unwrappedChapters"]:
        slugs = sorted({c['novelSlug'] for c in r["unwrappedChapters"]})
        print(f"  • Chạy wrap §1 cho {len(slugs)} truyện có chương chưa wrap:")
        for s in slugs[:3]:
            print(f"      python run.py --wrap-slug \"{s}\"")
    if r["weakDescription"]:
        print(f"  • Viết lại description cho {len(r['weakDescription'])} truyện "
              f"(tối thiểu {t['minDescLen']} ký tự).")
    print()


def main():
    ap = argparse.ArgumentParser(description="Audit AdSense-risk content")
    ap.add_argument("--min-chapters", type=int, default=MIN_CHAPTERS_DEFAULT,
                    help=f"Ngưỡng thin content (default {MIN_CHAPTERS_DEFAULT})")
    ap.add_argument("--min-words", type=int, default=MIN_WORDS_DEFAULT,
                    help=f"Ngưỡng chapter ngắn (default {MIN_WORDS_DEFAULT})")
    ap.add_argument("--json", action="store_true", help="Xuất JSON thay vì report")
    args = ap.parse_args()

    report = audit(args.min_chapters, args.min_words)

    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_report(report)


if __name__ == "__main__":
    main()
