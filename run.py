#!/usr/bin/env python3
"""
🏯 Cổ Trang Các — Crawler đa nguồn

  python run.py                        # Tự động: 1 truyện ngẫu nhiên (nguồn mặc định)
  python run.py --interactive          # Chọn nguồn + truyện thủ công
  python run.py --source truyenfull    # Chỉ định nguồn
  python run.py --count 3              # 3 truyện ngẫu nhiên
  python run.py --url "URL"            # Crawl 1 URL cụ thể
  python run.py --url "URL" --chapters 1 12 15   # Chỉ tải chương 1, 12, 15
  python run.py --schedule             # Chạy hàng ngày lúc 8h
  python run.py --test                 # Test (1 truyện, 3 chương)

Nguồn có sẵn: yeungontinh | truyenfull | metruyencv
# Interactive mode (chọn nguồn + truyện thủ công)
python run.py --interactive

# Chỉ định nguồn
python run.py --source truyenfull
python run.py --source metruyencv --count 3

# Xem danh sách nguồn
python run.py --list-sources

# Crawl URL cụ thể từ nguồn khác
python run.py --source truyenfull --url "https://truyenfull.io/ten-truyen/"
"""

import argparse
import logging
import sys
import os
import re
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (CRAWL_SCHEDULE, REQUEST_DELAY, GENRE_MAP, IMPORT_MODE,
                    DOCX_EXPORT_ENABLED, DOCX_OUTPUT_DIR, DOCX_CHANNEL_NAME,
                    SRT_DURATION_PER_LINE, SRT_WORDS_PER_SECOND,
                    HF_API_TOKEN, HF_IMAGE_RATIO)
                    # SRT_EXPORT_ENABLED — tạm comment vì chức năng SRT đã tắt

# ── Thư mục output có ngày — VD: docx_output/2026-03-25/ ─────────
# Tính lazy mỗi lần dùng để tránh sai ngày khi script chạy xuyên đêm
def _get_today_dir() -> str:
    return os.path.join(DOCX_OUTPUT_DIR, datetime.now().strftime('%Y-%m-%d'))

# Alias dùng cho các chỗ cần giá trị ngay (không chạy xuyên đêm)
_TODAY_DIR = _get_today_dir()


def _find_novel_dir(slug_or_title: str) -> str | None:
    """
    Tìm thư mục truyện trong cả DOCX_OUTPUT_DIR (flat cũ)
    và các thư mục con theo ngày (YYYY-MM-DD/slug/).
    Trả về đường dẫn đầy đủ hoặc None.
    """
    from docx_exporter import _slugify
    slug = _slugify(slug_or_title) if slug_or_title else ""
    candidates = [slug, slug_or_title]

    # Tìm trong thư mục flat cũ
    for c in candidates:
        p = os.path.join(DOCX_OUTPUT_DIR, c)
        if os.path.isdir(p):
            return p

    # Tìm trong các ngày con (mới nhất trước)
    try:
        date_dirs = sorted(
            [d for d in os.listdir(DOCX_OUTPUT_DIR)
             if os.path.isdir(os.path.join(DOCX_OUTPUT_DIR, d)) and len(d) == 10 and d[4] == '-'],
            reverse=True,
        )
    except OSError:
        return None

    for date_dir in date_dirs:
        for c in candidates:
            p = os.path.join(DOCX_OUTPUT_DIR, date_dir, c)
            if os.path.isdir(p):
                return p

    return None
from sources import SOURCES, get_source, get_source_for_url
from db_helper import (
    get_connection, novel_exists, chapter_exists,
    insert_novel, insert_chapter, slugify,
    get_all_novel_slugs, get_all_novel_titles, get_stats,
)
from rewriter import rewrite_chapter, rewrite_novel_meta, check_rewriter, sanitize_description

DEFAULT_SOURCE = 'yeungontinh'


def _export_docx_with_confirm(title, author, chapters):
    """Hỏi người dùng trước khi xuất DOCX. Trả về list đường dẫn đã lưu (có thể rỗng)."""
    import sys
    from docx_exporter import save_novel_as_docx

    if not sys.stdin.isatty():
        # Chạy tự động (schedule / cron) — xuất không hỏi
        result = save_novel_as_docx(title, author, chapters,
                                    output_dir=_TODAY_DIR,
                                    channel_name=DOCX_CHANNEL_NAME)
        if isinstance(result, list):
            return result
        return [result] if result else []

    print(f"\n📄 Truyện: {title}  ({len(chapters)} chương)")
    print(f"   Thư mục: {_TODAY_DIR}")
    choice = input("💾 Bạn có muốn lưu file DOCX không? [Y/n]: ").strip().lower()
    if choice in ('', 'y', 'yes'):
        result = save_novel_as_docx(title, author, chapters,
                                    output_dir=_TODAY_DIR,
                                    channel_name=DOCX_CHANNEL_NAME)
        if isinstance(result, list):
            return result
        return [result] if result else []

    print("⏭️  Bỏ qua — file DOCX chưa được lưu.")
    return []


def _export_srt_with_confirm(docx_paths):
    """Hỏi người dùng trước khi chuyển DOCX sang SRT."""
    import sys
    from srt_exporter import convert_docx_to_srt

    if not docx_paths:
        return

    if sys.stdin.isatty():
        choice = input("\n🔄 Bạn có muốn chuyển sang file SRT không? [Y/n]: ").strip().lower()
        if choice not in ('', 'y', 'yes'):
            print("⏭️  Bỏ qua — file SRT chưa được tạo.")
            return

    for docx_path in docx_paths:
        srt_path = os.path.join(
            os.path.dirname(docx_path),   # cùng thư mục với file DOCX
            os.path.splitext(os.path.basename(docx_path))[0] + '.srt',
        )
        convert_docx_to_srt(docx_path, srt_path,
                             SRT_DURATION_PER_LINE, SRT_WORDS_PER_SECOND)
        print(f"✅ Đã xuất SRT: {srt_path}")


def _analyze_seo_with_confirm(title, author, genres, chapters, docx_paths, auto=False):
    """Hỏi người dùng trước khi phân tích SEO. Lưu seo.txt vào cùng thư mục với DOCX.
    auto=True: bỏ qua hỏi confirm (dùng khi có flag --seo).
    """
    import sys
    from seo_analyzer import analyze_novel_seo

    if not auto and sys.stdin.isatty():
        choice = input("\n🔍 Bạn có muốn phân tích SEO cho YouTube không? [Y/n]: ").strip().lower()
        if choice not in ('', 'y', 'yes'):
            print("⏭️  Bỏ qua — SEO chưa được tạo.")
            return

    # Dùng thư mục của file DOCX đầu tiên; nếu không có DOCX thì tự tạo theo slug
    from docx_exporter import _slugify
    slug = _slugify(title)
    if docx_paths:
        output_dir = os.path.dirname(docx_paths[0])
    else:
        output_dir = os.path.join(_TODAY_DIR, slug)

    from config import SITE_URL
    novel_url = f"{SITE_URL.rstrip('/')}/truyen/{slug}"

    out_path = analyze_novel_seo(title, author, genres, chapters, output_dir,
                                  channel_name=DOCX_CHANNEL_NAME,
                                  novel_url=novel_url)
    if out_path:
        print(f"✅ Đã lưu SEO: {out_path}")


def _ask_era(current_era: str, current_decade: str = "") -> tuple:
    """
    Hỏi user chọn era thủ công. Trả về (era, decade).
    Nếu stdin không phải tty hoặc user nhấn Enter → giữ nguyên.
    """
    import sys
    if not sys.stdin.isatty():
        return current_era, current_decade

    era_label = {"co-trang": "CỔ TRANG", "hien-dai": "HIỆN ĐẠI", "thap-nien": "THẬP NIÊN"}.get(current_era, current_era.upper())
    print(f"\n🎭  Era hiện tại: [{era_label}]{f' ({current_decade})' if current_decade else ''}")
    print("   1. Cổ Trang   (cung đình, tiên hiệp, huyền huyễn, ...)")
    print("   2. Hiện Đại   (ngôn tình, đô thị, đam mỹ, ...)")
    print("   3. Thập Niên  (60s, 70s, 80s, 90s, 2000s)")
    era_choice = input("   Chọn era [1/2/3] hoặc Enter để giữ nguyên: ").strip()

    era, decade = current_era, current_decade
    if era_choice == "1":
        era, decade = "co-trang", ""
    elif era_choice == "2":
        era, decade = "hien-dai", ""
    elif era_choice == "3":
        era = "thap-nien"
        dec_choice = input("   Thập niên nào? [60s/70s/80s/90s/2000s]: ").strip().lower()
        decade = dec_choice if dec_choice in ("60s", "70s", "80s", "90s", "2000s") else "default"

    era_label = {"co-trang": "CỔ TRANG", "hien-dai": "HIỆN ĐẠI", "thap-nien": "THẬP NIÊN"}.get(era, era.upper())
    print(f"   ✅ Era: [{era_label}]{f' ({decade})' if decade else ''}")
    return era, decade


def _generate_images_with_confirm(title, genres_str, chapters, docx_paths, auto=False):
    """
    Tạo 10 thumbnail 16:9 đa dạng góc chụp, bám sát nội dung truyện.

    - Phân biệt era từ scenes.json hoặc thể loại: co-trang / hien-dai / thap-nien
    - 10 shot types hoàn toàn khác nhau (wide, atmospheric, detail, action, ...)
    - Chọn câu từ 10 vị trí trải đều trong truyện — mỗi hình bám sát 1 thời điểm khác nhau
    - Không xoay quanh nhân vật: chỉ 3/10 hình có close_up nhân vật
    """
    import sys, hashlib, json as _json
    from image_generator import sentence_to_image

    if not HF_API_TOKEN:
        print("⚠️  HF_API_TOKEN chưa được cấu hình — bỏ qua tạo thumbnail.")
        print("   Thêm HF_API_TOKEN=hf_... vào file .env")
        return

    if not auto and sys.stdin.isatty():
        choice = input("\n🖼️  Bạn có muốn tạo 10 thumbnail 16:9 cho truyện này không? [Y/n]: ").strip().lower()
        if choice not in ('', 'y', 'yes'):
            print("⏭️  Bỏ qua — thumbnail chưa được tạo.")
            return

    if not chapters:
        print("⚠️  Không có chương nào để tạo thumbnail.")
        return

    # ── Thư mục lưu thumbnail ───────────────────────────────────────
    if docx_paths:
        novel_dir  = os.path.dirname(docx_paths[0])
        thumbs_dir = os.path.join(novel_dir, 'thumbnails')
    else:
        from docx_exporter import _slugify
        novel_dir  = os.path.join(_TODAY_DIR, _slugify(title))
        thumbs_dir = os.path.join(novel_dir, 'thumbnails')
    os.makedirs(thumbs_dir, exist_ok=True)

    # ── Era từ thể loại — đây là nguồn tin cậy nhất ────────────────
    _GENRE_ERA = {
        "co-trang": "co-trang", "cung-dinh": "co-trang", "tien-hiep": "co-trang",
        "huyen-huyen": "co-trang", "vo-hiep": "co-trang", "lich-su": "co-trang",
        "xuyen-khong": "co-trang", "xuyen-thanh": "co-trang",
        "ngon-tinh": "hien-dai", "hien-dai": "hien-dai", "do-thi": "hien-dai",
        "hai-huoc": "hien-dai", "trong-sinh": "hien-dai", "dam-my": "hien-dai",
    }
    genre_first  = genres_str.split(',')[0].strip() if genres_str else ""
    era_by_genre = _GENRE_ERA.get(genre_first, "") if genre_first else ""

    # ── Đọc character từ scenes.json (nếu đã chạy --shorts) ────────
    era            = ""
    decade         = ""
    character_desc = ""
    scenes_json    = os.path.join(novel_dir, 'shorts', 'scenes.json')
    if os.path.exists(scenes_json):
        try:
            with open(scenes_json, encoding='utf-8') as f:
                sdata = _json.load(f)
            char           = sdata.get('character', {})
            era_from_json  = char.get('era', '')
            decade         = char.get('decade', '')
            character_desc = char.get('appearance', '')
            # Dùng era từ genre nếu genre mapping rõ ràng (tránh LLM trả sai era)
            # Chỉ giữ era từ scenes.json khi genre không có trong mapping
            # hoặc khi era là "thap-nien" (cần decade, genre không cung cấp được)
            if era_by_genre and era_from_json != "thap-nien":
                era = era_by_genre
                if era != era_from_json:
                    print(f"   ⚠️  scenes.json era [{era_from_json.upper()}] bị override bởi genre '{genre_first}' → [{era.upper()}]")
                else:
                    print(f"   Era từ genre '{genre_first}': [{era.upper()}] {character_desc[:60]}...")
            else:
                era = era_from_json or era_by_genre or "co-trang"
                print(f"   Era từ scenes.json: [{era.upper()}] {character_desc[:60]}...")
        except Exception:
            pass

    # ── Fallback nếu không có scenes.json ──────────────────────────
    if not era:
        era = era_by_genre or "co-trang"
        print(f"   Era suy ra từ thể loại '{genre_first}': [{era.upper()}]")

    # ── Hỏi xác nhận era thủ công ────────────────────────────────
    if not auto:
        era, decade = _ask_era(era, decade)

    genre       = genres_str.split(',')[0].strip() if genres_str else "co-trang"
    base_seed   = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % (2**31)
    THUMB_RATIO = "16:9"
    headers     = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    # Thêm vào cuối mỗi sentence: chặn 18+, anatomy lỗi, ảnh bị cắt
    _ANATOMY_HINT = (
        "safe for work, family friendly, fully clothed, no nudity, no adult content, "
        "complete image fully framed, no cropped limbs, "
        "perfect anatomy, exactly two arms, no extra limbs, no missing limbs, "
        "no deformed hands, no extra fingers, no floating body parts"
    )

    # ── 20 shot types — đa dạng, không xoay quanh nhân vật ────────
    # ~6 cảnh nhân vật (close_up/medium/back_view) + ~14 cảnh môi trường/vật thể/không khí
    N_THUMBS = 20
    SHOT_PLAN = [
        "wide",        # 01 — Toàn cảnh bối cảnh truyện
        "atmospheric", # 02 — Mood / ánh sáng thuần môi trường
        "close_up",    # 03 — Mặt nhân vật (face only)
        "detail",      # 04 — Vật thể biểu tượng
        "back_view",   # 05 — Nhân vật từ sau lưng nhìn vào bối cảnh
        "medium",      # 06 — Ngực trở lên + môi trường
        "wide",        # 07 — Toàn cảnh 2 (góc khác, ban đêm)
        "atmospheric", # 08 — Mood 2 (mưa / nến / sương)
        "close_up",    # 09 — Mặt nhân vật cảnh 2
        "detail",      # 10 — Vật thể 2
        "back_view",   # 11 — Nhân vật từ sau lưng 2
        "wide",        # 12 — Toàn cảnh 3 (nội thất hoành tráng)
        "atmospheric", # 13 — Mood 3 (hoàng hôn / ánh nến)
        "medium",      # 14 — Nhân vật + bối cảnh 2
        "detail",      # 15 — Vật thể 3
        "wide",        # 16 — Toàn cảnh 4 (thiên nhiên / đêm)
        "close_up",    # 17 — Mặt nhân vật cảnh 3
        "atmospheric", # 18 — Mood 4 (sương mù / tuyết)
        "back_view",   # 19 — Nhân vật từ sau lưng 3
        "detail",      # 20 — Vật thể 4
    ]

    # ── Trích xuất setting + action từ câu tiếng Việt → Ollama hiểu tốt hơn ──
    _VI_SETTING = [
        (['phòng ngủ', 'giường'], 'bedroom interior'),
        (['phòng khách', 'phòng chờ'], 'living room interior'),
        (['nhà bếp', 'bếp'], 'kitchen interior'),
        (['văn phòng', 'công ty', 'công sở'], 'office interior'),
        (['bệnh viện', 'phòng bệnh', 'cấp cứu'], 'hospital corridor'),
        (['sân vườn', 'vườn hoa', 'vườn'], 'garden courtyard'),
        (['sân thượng', 'mái nhà'], 'rooftop'),
        (['quán cà phê', 'quán trà', 'quán ăn'], 'café restaurant interior'),
        (['đường phố', 'vỉa hè', 'con đường'], 'city street'),
        (['công viên'], 'park outdoor'),
        (['sân bay', 'ga tàu', 'bến xe'], 'transit station'),
        (['bờ sông', 'sông', 'bến'], 'riverside'),
        (['biển', 'bãi biển'], 'seaside beach'),
        (['rừng', 'núi', 'đồi'], 'forest mountain'),
        (['cung điện', 'hoàng cung', 'hoàng thành'], 'imperial palace'),
        (['hậu cung', 'tẩm cung'], 'imperial inner chamber'),
        (['đại sảnh', 'sảnh đường'], 'grand hall'),
        (['ngục', 'địa lao', 'lao ngục'], 'dungeon prison'),
        (['chợ', 'phiên chợ', 'chợ phiên'], 'market street'),
        (['quán rượu', 'tửu quán'], 'ancient tavern inn'),
        (['đình', 'đền', 'chùa', 'miếu'], 'temple shrine'),
        (['đêm', 'ban đêm'], 'at night'),
        (['bình minh', 'rạng sáng'], 'at dawn'),
        (['hoàng hôn', 'chiều tà'], 'at sunset'),
        (['mưa', 'cơn mưa'], 'in the rain'),
        (['tuyết', 'băng giá'], 'in the snow'),
        (['sương mù', 'sương'], 'in the mist fog'),
    ]
    _VI_EMOTION = [
        (['khóc', 'nước mắt', 'lệ rơi', 'rơi lệ'], 'crying tearful'),
        (['tức giận', 'giận dữ', 'phẫn nộ'], 'angry furious'),
        (['sợ hãi', 'hoảng loạn', 'hoảng sợ'], 'fearful terrified'),
        (['buồn', 'đau lòng', 'đau khổ', 'đau đớn'], 'sorrowful pained'),
        (['hạnh phúc', 'mỉm cười', 'cười vui'], 'joyful happy'),
        (['ngạc nhiên', 'bất ngờ', 'choáng váng'], 'shocked surprised'),
        (['kiên định', 'quyết tâm', 'mạnh mẽ'], 'determined fierce'),
        (['hoài niệm', 'hoài nhớ', 'nhớ về'], 'nostalgic longing'),
        (['lo lắng', 'lo âu', 'bất an'], 'anxious worried'),
        (['cô đơn', 'trống vắng', 'lẻ loi'], 'lonely isolated'),
        (['tuyệt vọng', 'vô vọng'], 'desperate hopeless'),
        (['hy vọng', 'mong chờ'], 'hopeful expectant'),
    ]

    def _extract_vi_scene(text: str):
        """Trích setting + emotion từ câu tiếng Việt → (setting_en, action_en)."""
        lower = text.lower()
        setting_en, action_en = '', ''
        for keywords, label in _VI_SETTING:
            if any(k in lower for k in keywords):
                setting_en = label
                break
        for keywords, label in _VI_EMOTION:
            if any(k in lower for k in keywords):
                action_en = label
                break
        return setting_en, action_en

    # ── Góc + cảm xúc xoay vòng cho close_up — tránh nhân vật trùng nhau ──
    _CLOSE_UP_VARIANTS = [
        "face looking slightly left, melancholic teary eyes, soft rim light",
        "three-quarter profile view, shocked parted lips, wide eyes",
        "face looking downward, sorrowful closed eyes, tears on cheek",
        "direct frontal gaze at camera, fierce determined expression, strong jaw",
        "side profile facing right, distant longing gaze into empty space",
        "face tilted slightly upward, hopeful tearful eyes, gentle smile",
        "over-the-shoulder angle, fearful glance backward, tense posture",
        "low angle looking up, prideful cold expression, chin slightly raised",
        "face half in shadow half lit, conflicted bitter expression",
        "extreme close-up eyes only, red-rimmed from crying, glistening",
    ]

    # ── Chọn 20 câu trải đều trong truyện ─────────────────────────
    def _pick_visual_sentence(ch):
        """Ưu tiên câu có hành động / mô tả không gian / dài > 40 ký tự."""
        content = ch.get('content', '')
        _VISUAL_WORDS = ('phòng', 'đứng', 'nhìn', 'bước', 'ngồi', 'ánh', 'sáng',
                         'tối', 'cửa', 'bàn', 'mắt', 'tay', 'nước', 'gió', 'trời',
                         'palace', 'room', 'light', 'dark', 'stood', 'walked')
        lines = [l.strip() for l in content.splitlines() if len(l.strip()) > 40]
        for line in lines:
            if any(w in line.lower() for w in _VISUAL_WORDS):
                return line[:250]
        return lines[0][:250] if lines else content[:250]

    n = len(chapters)
    positions = (
        [int(i * (n - 1) / (N_THUMBS - 1)) for i in range(N_THUMBS)]
        if n >= N_THUMBS
        else list(range(n))
    )
    selected_chapters = [chapters[p] for p in positions]
    while len(selected_chapters) < N_THUMBS:
        selected_chapters.append(chapters[len(selected_chapters) % n])

    # ── Tạo 20 thumbnail ──────────────────────────────────────────
    era_label = {"co-trang": "CỔ TRANG", "hien-dai": "HIỆN ĐẠI", "thap-nien": "THẬP NIÊN"}.get(era, era.upper())
    print(f"\n🖼️  Tạo {N_THUMBS} thumbnail 16:9 [{era_label}] → {thumbs_dir}")

    close_up_count = 0
    for idx, (ch, shot_type) in enumerate(zip(selected_chapters, SHOT_PLAN), start=1):
        fname    = f"thumb_{idx:02d}_{shot_type}.jpg"
        out_path = os.path.join(thumbs_dir, fname)
        if os.path.exists(out_path):
            if shot_type == 'close_up':
                close_up_count += 1
            print(f"  ⏭️  Thumb {idx:02d} đã có — bỏ qua")
            continue

        sentence = _pick_visual_sentence(ch) + f", {_ANATOMY_HINT}"
        ch_num   = ch.get('number', '?')
        # Seed khác biệt lớn cho mỗi thumbnail — đặc biệt ảnh có nhân vật
        # Dùng hash riêng per index để FLUX tạo gương mặt hoàn toàn khác nhau
        if shot_type in ('close_up', 'medium', 'action', 'two_shot'):
            # Seed hoàn toàn ngẫu nhiên per nhân vật — tránh gương mặt giống nhau
            seed = int(hashlib.md5(f"{title}_face_{idx}_{shot_type}".encode()).hexdigest()[:8], 16) % (2**31)
        else:
            seed = (base_seed + idx * 1009) % (2**31)

        # Trích setting/emotion từ câu tiếng Việt
        vi_setting, vi_action = _extract_vi_scene(sentence)

        # Mỗi close_up dùng góc + cảm xúc khác nhau — tránh nhân vật trùng nhau
        if shot_type == 'close_up':
            close_up_action = _CLOSE_UP_VARIANTS[close_up_count % len(_CLOSE_UP_VARIANTS)]
            # Gộp emotion từ story (nếu có) vào variant
            if vi_action:
                close_up_action = f"{vi_action}, {close_up_action}"
            close_up_count += 1
        else:
            close_up_action = vi_action

        try:
            image, _ = sentence_to_image(
                sentence, headers,
                ratio=THUMB_RATIO,
                genre=genre,
                era=era,
                decade=decade,
                character_desc="",  # Để trống — beauty pool tự chọn nhân vật đa dạng cho mỗi thumbnail
                action=close_up_action,
                setting=vi_setting,
                seed=seed,
                shot_type=shot_type,
                scene_index=idx - 1,
            )
            image.save(out_path, "JPEG", quality=95)
            print(f"  ✅ {idx:02d}/{N_THUMBS} [{shot_type:12s}] Ch.{ch_num} → {fname}")
            print(f"      {sentence[:90]}...")
        except Exception as e:
            print(f"  ❌ {idx:02d} [{shot_type}] lỗi: {e}")


def _generate_shorts_with_confirm(title, author, genres_str, chapters, docx_paths, auto=False):
    """
    Hỏi người dùng trước khi chạy Shorts pipeline:
      novel chapters → hook story (400-600 chữ) + ảnh từng scene (FLUX.1-schnell)
    auto=True: bỏ qua confirm (dùng khi có flag --shorts).
    """
    import sys
    from shorts_pipeline import run_shorts_pipeline

    if not auto and sys.stdin.isatty():
        choice = input("\n📱 Bạn có muốn tạo nội dung Shorts (hook story + ảnh) không? [Y/n]: ").strip().lower()
        if choice not in ('', 'y', 'yes'):
            print("⏭️  Bỏ qua — Shorts chưa được tạo.")
            return

    if not chapters:
        print("⚠️  Không có chương nào để tạo Shorts.")
        return

    # Thư mục output: cùng thư mục DOCX hoặc tạo theo slug
    if docx_paths:
        base_dir = os.path.dirname(docx_paths[0])
    else:
        from docx_exporter import _slugify
        base_dir = os.path.join(_TODAY_DIR, _slugify(title))
    output_dir = os.path.join(base_dir, 'shorts')

    # ── Hỏi era trước khi chạy shorts ──────────────────────────
    import sys as _sys
    _GENRE_ERA_S = {
        "co-trang": "co-trang", "cung-dinh": "co-trang", "tien-hiep": "co-trang",
        "huyen-huyen": "co-trang", "vo-hiep": "co-trang", "lich-su": "co-trang",
        "xuyen-khong": "co-trang", "xuyen-thanh": "co-trang",
        "ngon-tinh": "hien-dai", "hien-dai": "hien-dai", "do-thi": "hien-dai",
        "hai-huoc": "hien-dai", "trong-sinh": "hien-dai", "dam-my": "hien-dai",
    }
    _gf = genres_str.split(',')[0].strip() if genres_str else ""
    _default_era = _GENRE_ERA_S.get(_gf, "co-trang")
    if not auto:
        _default_era, _default_decade = _ask_era(_default_era, "")
    else:
        _default_decade = ""

    result = run_shorts_pipeline(
        title=title,
        author=author,
        genres_str=genres_str,
        chapters=chapters,
        output_dir=output_dir,
        hf_token=HF_API_TOKEN,
        ratio=HF_IMAGE_RATIO,
        era_override=_default_era,
        decade_override=_default_decade,
    )

    if result:
        print(f"\n✅ Shorts pipeline hoàn tất:")
        print(f"   Hook story: {result.get('hook_story_path', '')}")
        print(f"   Scenes:     {result.get('scenes_path', '')}")
        print(f"   Ảnh:        {result.get('images_dir', '')}")

        # Tạo Shorts SEO (TikTok + YouTube Shorts) ngay sau khi có hook story
        try:
            from seo_analyzer import analyze_shorts_seo
            from docx_exporter import _slugify
            from config import SITE_URL, DOCX_CHANNEL_NAME
            slug = _slugify(title)
            novel_url = f"{SITE_URL.rstrip('/')}/truyen/{slug}"
            hook_story_path = result.get('hook_story_path', '')
            if hook_story_path and os.path.exists(hook_story_path):
                with open(hook_story_path, encoding='utf-8') as f:
                    hook_story = f.read()
                seo_path = analyze_shorts_seo(
                    title=title,
                    genres=genres_str,
                    hook_story=hook_story,
                    shorts_dir=output_dir,
                    channel_name=DOCX_CHANNEL_NAME,
                    novel_url=novel_url,
                )
                if seo_path:
                    print(f"   Shorts SEO: {seo_path}")
        except Exception as e:
            print(f"⚠️  Shorts SEO lỗi: {e}")


# Logging
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(LOG_DIR, f'crawl_{datetime.now():%Y%m%d}.log'),
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger(__name__)


def map_genres(raw_genres):
    genres, tags = [], []
    for rg in raw_genres:
        mapped = GENRE_MAP.get(rg.strip().lower())
        if mapped and mapped not in genres:
            genres.append(mapped)
        else:
            tags.append(rg.strip())
    return ','.join(genres or ['ngon-tinh']), ','.join(tags)


def extract_chapter_number(url, index):
    m = re.search(r'chuong[- ]?(\d+)', url) or re.search(r'chapter[- ]?(\d+)', url)
    return int(m.group(1)) if m else index + 1


def _filter_chapters(chapter_urls, chapter_filter):
    """Lọc danh sách URL theo số chương chỉ định. chapter_filter là set số nguyên."""
    if not chapter_filter:
        return chapter_urls
    result = []
    for i, ch_url in enumerate(chapter_urls):
        ch_num = extract_chapter_number(ch_url, i)
        if ch_num in chapter_filter:
            result.append((i, ch_url, ch_num))
    return result


def crawl_novel_api(url, source_name=DEFAULT_SOURCE, max_chapters=0, chapter_filter=None):
    """Crawl 1 truyện → rewrite → POST lên API (IMPORT_MODE='api')."""
    from api_client import import_novel
    src = get_source(source_name)
    stats = {'novels_new': 0, 'chapters_new': 0}

    info = src.get_novel_info(url)
    if not info or not info.get('title'):
        logger.warning(f"  ⚠️ Không lấy được info: {url}")
        return stats

    title  = info['title']
    author = info.get('author', 'Đang cập nhật')
    desc   = sanitize_description(info.get('description', ''))

    chapter_urls = src.get_chapter_urls(url)
    if not chapter_urls:
        logger.warning("  ⚠️ Không có chương")
        return stats

    logger.info(f"  📖 {title} — {len(chapter_urls)} chương")

    # Rewrite title & description
    if sys.stdin.isatty():
        ans = input(f"  ✍️  Bạn có muốn rewrite title và description không? [Y/n] ").strip().lower()
        do_meta_rewrite = ans in ('', 'y', 'yes')
    else:
        do_meta_rewrite = True  # chế độ tự động: luôn rewrite

    if do_meta_rewrite:
        try:
            title, desc = rewrite_novel_meta(title, desc)
        except Exception as e:
            logger.warning(f"  ⚠️ Rewrite meta error: {e}")

    genres_raw = info.get('genres_raw', [])
    genres_str, tags_str = map_genres(genres_raw) if genres_raw else ('ngon-tinh', '')

    if chapter_filter:
        indexed = _filter_chapters(chapter_urls, chapter_filter)
        logger.info(f"  🎯 Lọc theo chương: {sorted(chapter_filter)} — tìm được {len(indexed)} chương")
    else:
        raw = chapter_urls[:max_chapters] if max_chapters > 0 else chapter_urls
        indexed = [(i, ch_url, extract_chapter_number(ch_url, i)) for i, ch_url in enumerate(raw)]

    chapters = []
    consecutive_empty = 0

    for i, ch_url, ch_num in indexed:
        content = src.get_chapter_content(ch_url)
        time.sleep(REQUEST_DELAY)

        if not content or len(content) < 50:
            consecutive_empty += 1
            logger.warning(f"    ⚠️ Ch.{ch_num}: quá ngắn, bỏ qua ({consecutive_empty} liên tiếp)")
            if consecutive_empty >= 3:
                logger.warning(f"    🛑 Dừng — {consecutive_empty} chương liên tiếp không có nội dung")
                break
            continue

        consecutive_empty = 0

        if getattr(src, 'needs_translation', False):
            try:
                from rewriter import split_paragraphs
                content = split_paragraphs(content)
            except Exception:
                pass
        else:
            try:
                content = rewrite_chapter(content, novel_title=title)
            except Exception as e:
                logger.warning(f"    ⚠️ Rewrite error: {e}")

        chapters.append({'number': ch_num, 'title': f'Chương {ch_num}', 'content': content})
        logger.info(f"    ✅ Ch.{ch_num} ({len(content)} ký tự)")

    if not chapters:
        logger.warning("  ⚠️ Không có chương hợp lệ")
        return stats

    # DOCX export (API mode)
    docx_paths = []
    if DOCX_EXPORT_ENABLED:
        docx_paths = _export_docx_with_confirm(title, author, chapters)
        # if SRT_EXPORT_ENABLED:
        #     _export_srt_with_confirm(docx_paths)
        _analyze_seo_with_confirm(title, author, genres_str, chapters, docx_paths, auto=auto_seo)
    _generate_images_with_confirm(title, genres_str, chapters, docx_paths, auto=auto_images)
    _generate_shorts_with_confirm(title, author, genres_str, chapters, docx_paths, auto=auto_shorts)

    novel_data = {
        'title':       title,
        'author':      author,
        'description': desc,
        'genres':      genres_str,
        'tags':        tags_str,
        'status':      info.get('status', 'completed'),
        'source_url':  url.rstrip('/'),
        'cover_image': info.get('cover_image', ''),
    }

    try:
        result = import_novel(novel_data, chapters)
        note = result.get('note', '')
        if note == 'novel_resumed':
            new_ch = result.get('inserted', 0)
            stats['chapters_new'] = new_ch
            if new_ch:
                logger.info(f"  📗 Tiếp tục: {title} — +{new_ch} chương mới")
            else:
                logger.info(f"  📗 Đã đầy đủ: {title} — không có chương mới")
        else:
            stats['novels_new']   = 1
            stats['chapters_new'] = result.get('inserted', 0)
            logger.info(f"  ✅ Upload: {title} — {stats['chapters_new']} chương mới")
    except RuntimeError as e:
        logger.error(str(e))

    return stats


def crawl_novel(url, source_name=DEFAULT_SOURCE, max_chapters=0, conn=None, chapter_filter=None):
    """Crawl 1 truyện → rewrite → lưu DB (IMPORT_MODE='local')."""
    if IMPORT_MODE == 'api':
        return crawl_novel_api(url, source_name, max_chapters, chapter_filter=chapter_filter)

    src = get_source(source_name)
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    stats = {'novels_new': 0, 'chapters_new': 0}

    info = src.get_novel_info(url)
    if not info or not info.get('title'):
        logger.warning(f"  ⚠️ Không lấy được info: {url}")
        if own_conn:
            conn.close()
        return stats

    title = info['title']
    author = info.get('author', 'Đang cập nhật')
    desc = sanitize_description(info.get('description', ''))

    genres_raw = info.get('genres_raw', [])
    genres_str, _ = map_genres(genres_raw) if genres_raw else ('ngon-tinh', '')

    chapter_urls = src.get_chapter_urls(url)
    if not chapter_urls:
        logger.warning("  ⚠️ Không có chương")
        if own_conn:
            conn.close()
        return stats

    logger.info(f"  📖 {title} — {len(chapter_urls)} chương")

    # Lookup bằng sourceUrl trước (tránh mất tìm khi title đã bị rewrite)
    existing_novel_id = novel_exists(conn, source_url=url, slug=slugify(title), title=title)

    # Rewrite title & description (chỉ khi thêm mới, không phải resume)
    if not existing_novel_id:
        if sys.stdin.isatty():
            ans = input(f"  ✍️  Bạn có muốn rewrite title và description không? [Y/n] ").strip().lower()
            do_meta_rewrite = ans in ('', 'y', 'yes')
        else:
            do_meta_rewrite = True  # chế độ tự động: luôn rewrite

        if do_meta_rewrite:
            original_title = title
            try:
                title, desc = rewrite_novel_meta(title, desc)
            except Exception as e:
                logger.warning(f"  ⚠️ Rewrite meta error: {e}")
                title = original_title

    if existing_novel_id:
        novel_id = existing_novel_id
        logger.info(f"  📗 Đã có trong DB: {title} — tiếp tục từ chương còn thiếu")
    else:
        novel_id, slug = insert_novel(
            conn, title=title, author=author, description=desc,
            genres=genres_str, status=info.get('status', 'completed'),
            source_url=url,
        )
        logger.info(f"  ✅ Thêm mới: {title}")
        stats['novels_new'] = 1

    if chapter_filter:
        indexed = _filter_chapters(chapter_urls, chapter_filter)
        logger.info(f"  🎯 Lọc theo chương: {sorted(chapter_filter)} — tìm được {len(indexed)} chương")
    else:
        raw = chapter_urls[:max_chapters] if max_chapters > 0 else chapter_urls
        indexed = [(i, ch_url, extract_chapter_number(ch_url, i)) for i, ch_url in enumerate(raw)]

    chapters_for_docx = []
    consecutive_empty = 0

    for i, ch_url, ch_num in indexed:
        if chapter_exists(conn, novel_id, ch_num):
            consecutive_empty = 0
            continue

        content = src.get_chapter_content(ch_url)
        time.sleep(REQUEST_DELAY)

        if not content or len(content) < 50:
            consecutive_empty += 1
            logger.warning(f"    ⚠️ Ch.{ch_num}: quá ngắn, bỏ qua ({consecutive_empty} liên tiếp)")
            if consecutive_empty >= 3:
                logger.warning(f"    🛑 Dừng — {consecutive_empty} chương liên tiếp không có nội dung")
                break
            continue

        consecutive_empty = 0

        if getattr(src, 'needs_translation', False):
            # Content already translated inside get_chapter_content()
            # Just fix paragraph formatting
            try:
                from rewriter import split_paragraphs
                content = split_paragraphs(content)
            except Exception:
                pass
        else:
            try:
                content = rewrite_chapter(content, novel_title=title)
            except Exception as e:
                logger.warning(f"    ⚠️ Rewrite error: {e}")

        insert_chapter(conn, novel_id, ch_num, f"Chương {ch_num}", content,
                       chapter_index=i, total_chapters=len(chapter_urls))
        stats['chapters_new'] += 1
        logger.info(f"    ✅ Ch.{ch_num} ({len(content)} ký tự)")

        if DOCX_EXPORT_ENABLED:
            chapters_for_docx.append({'number': ch_num,
                                      'title': f'Chương {ch_num}',
                                      'content': content})

    # DOCX export (local mode)
    docx_paths = []
    if DOCX_EXPORT_ENABLED and chapters_for_docx:
        docx_paths = _export_docx_with_confirm(title, author, chapters_for_docx)
        # if SRT_EXPORT_ENABLED:
        #     _export_srt_with_confirm(docx_paths)
        _analyze_seo_with_confirm(title, author, genres_str, chapters_for_docx, docx_paths, auto=auto_seo)
    if chapters_for_docx:
        _generate_images_with_confirm(title, genres_str, chapters_for_docx, docx_paths, auto=auto_images)
        _generate_shorts_with_confirm(title, author, genres_str, chapters_for_docx, docx_paths, auto=auto_shorts)

    if own_conn:
        conn.close()
    return stats


def preflight_check_rewriter():
    """Kiểm tra rewriter trước khi crawl. Dừng nếu không khả dụng."""
    ok, msg = check_rewriter()
    if ok:
        logger.info(f"✅ Rewriter: {msg}")
    else:
        logger.error(f"❌ Rewriter không khả dụng: {msg}")
        logger.error("   Hủy crawl để tránh lãng phí tài nguyên. Sửa config.py rồi thử lại.")
        sys.exit(1)


def run_auto(source_name=DEFAULT_SOURCE, count=1, max_chapters=0):
    """Random truyện mới từ nguồn đã chọn."""
    src = get_source(source_name)
    logger.info(f"\n🏯 Crawler — {datetime.now():%Y-%m-%d %H:%M}")
    logger.info(f"   Nguồn: {src.label}  |  Số truyện: {count}  |  Mode: {IMPORT_MODE.upper()}")

    novels = src.get_novel_urls()
    if not novels:
        logger.warning("⚠️ Không tìm thấy truyện")
        return

    total   = {'novels_new': 0, 'chapters_new': 0}
    crawled = 0

    if IMPORT_MODE == 'api':
        # API mode: server handles dedup; just shuffle and try up to `count`
        random.shuffle(novels)
        for url, title in novels:
            if crawled >= count:
                break
            logger.info(f"\n📖 [{crawled+1}/{count}] {title}")
            logger.info(f"   {url}")
            s = crawl_novel_api(url, source_name=source_name, max_chapters=max_chapters)
            total['novels_new']   += s['novels_new']
            total['chapters_new'] += s['chapters_new']
            if s['novels_new'] > 0:
                crawled += 1
        logger.info(f"\n{'='*40}")
        logger.info(f"📊 +{total['novels_new']} truyện, +{total['chapters_new']} chương")
        logger.info(f"{'='*40}\n")
        return

    # Local mode: pre-filter using local DB
    try:
        conn = get_connection()
        before = get_stats(conn)
        logger.info(f"📊 DB: {before['novels']} truyện, {before['chapters']} chương")
    except Exception as e:
        logger.error(f"❌ DB error: {e}")
        return

    existing_slugs  = get_all_novel_slugs(conn)
    existing_titles = {t.lower() for t in get_all_novel_titles(conn)}

    new_novels = [
        (url, title) for url, title in novels
        if slugify(title) not in existing_slugs
        and title.lower().strip() not in existing_titles
    ]
    logger.info(f"🆕 {len(new_novels)} truyện mới (sau lọc trùng)")

    if not new_novels:
        logger.info("📭 Tất cả đã có trong DB")
        conn.close()
        return

    random.shuffle(new_novels)

    for url, title in new_novels:
        if crawled >= count:
            break
        logger.info(f"\n📖 [{crawled+1}/{count}] {title}")
        logger.info(f"   {url}")
        s = crawl_novel(url, source_name=source_name, max_chapters=max_chapters, conn=conn)
        total['novels_new']   += s['novels_new']
        total['chapters_new'] += s['chapters_new']
        if s['novels_new'] > 0:
            crawled += 1

    after = get_stats(conn)
    conn.close()
    logger.info(f"\n{'='*40}")
    logger.info(f"📊 +{total['novels_new']} truyện, +{total['chapters_new']} chương")
    logger.info(f"   DB: {after['novels']} truyện, {after['chapters']} chương")
    logger.info(f"{'='*40}\n")


def run_interactive(max_chapters=0, chapter_filter=None):
    """Chế độ tương tác: chọn nguồn → chọn truyện."""
    print("\n" + "="*50)
    print("🏯 Crawler — Chế độ tương tác")
    print("="*50)

    # 1. Chọn nguồn
    source_list = list(SOURCES.items())
    print("\n📡 Chọn nguồn:")
    for i, (key, src) in enumerate(source_list, 1):
        print(f"  [{i}] {src.label}")
    print(f"  [Enter] Mặc định: {DEFAULT_SOURCE}")

    choice = input("\n> ").strip()
    if choice == '':
        source_name = DEFAULT_SOURCE
    elif choice.isdigit() and 1 <= int(choice) <= len(source_list):
        source_name = source_list[int(choice) - 1][0]
    elif choice in SOURCES:
        source_name = choice
    else:
        print(f"❌ Lựa chọn không hợp lệ, dùng mặc định: {DEFAULT_SOURCE}")
        source_name = DEFAULT_SOURCE

    src = get_source(source_name)
    print(f"\n✅ Nguồn: {src.label}")

    # 2. Lấy danh sách truyện
    print("\n⏳ Đang lấy danh sách truyện...")
    novels = src.get_novel_urls(max_count=50)
    if not novels:
        print("❌ Không lấy được danh sách truyện")
        return

    # Lọc trùng với DB (chỉ khi local mode)
    if IMPORT_MODE == 'local':
        conn = get_connection()
        existing_slugs  = get_all_novel_slugs(conn)
        existing_titles = {t.lower() for t in get_all_novel_titles(conn)}
        new_novels = [
            (url, title) for url, title in novels
            if slugify(title) not in existing_slugs
            and title.lower().strip() not in existing_titles
        ]
        print(f"\n📚 {len(new_novels)} truyện chưa có trong DB:\n")
    else:
        conn = None
        new_novels = novels
        print(f"\n📚 {len(new_novels)} truyện (API mode — server sẽ kiểm tra trùng):\n")

    for i, (url, title) in enumerate(new_novels, 1):
        print(f"  [{i:2d}] {title}")

    # 3. Chọn truyện
    print("\n💡 Nhập số thứ tự truyện muốn tải (VD: 1 3 5), hoặc Enter để ngẫu nhiên:")
    sel = input("> ").strip()

    if sel == '':
        # Ngẫu nhiên 1 truyện
        chosen = [random.choice(new_novels)]
        print(f"\n🎲 Ngẫu nhiên: {chosen[0][1]}")
    else:
        indices = []
        for part in sel.split():
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(new_novels):
                    indices.append(idx)
        if not indices:
            print("❌ Không hợp lệ, chọn ngẫu nhiên")
            chosen = [random.choice(new_novels)]
        else:
            chosen = [new_novels[i] for i in indices]

    # 4. Xác nhận và crawl
    print(f"\n📋 Sẽ tải {len(chosen)} truyện:")
    for url, title in chosen:
        print(f"  • {title}")
    print(f"  Nguồn: {src.label}")
    if max_chapters:
        print(f"  Giới hạn: {max_chapters} chương/truyện")

    confirm = input("\nXác nhận? [Y/n] ").strip().lower()
    if confirm == 'n':
        print("❌ Hủy.")
        if conn:
            conn.close()
        return

    # Ask about rewriter
    import config as _cfg
    if _cfg.REWRITE_ENABLED:
        print(f"\n✍️  Rewriter đang bật — provider: {_cfg.REWRITE_PROVIDER.upper()}")
        ans = input("   Bạn có muốn viết lại nội dung không? [Y/n] ").strip().lower()
        if ans == 'n':
            _cfg.REWRITE_ENABLED = False
            print("   ⏭️  Bỏ qua rewriter — chỉ định dạng đoạn văn\n")
        else:
            print()
            preflight_check_rewriter()
    else:
        print("\n⏭️  Rewriter đang tắt (REWRITE_ENABLED=False)\n")

    total = {'novels_new': 0, 'chapters_new': 0}
    for url, title in chosen:
        print(f"\n📖 {title}\n   {url}")
        s = crawl_novel(url, source_name=source_name, max_chapters=max_chapters, conn=conn, chapter_filter=chapter_filter)
        total['novels_new']   += s['novels_new']
        total['chapters_new'] += s['chapters_new']

    print(f"\n{'='*40}")
    print(f"📊 +{total['novels_new']} truyện, +{total['chapters_new']} chương")
    if conn:
        after = get_stats(conn)
        conn.close()
        print(f"   DB: {after['novels']} truyện, {after['chapters']} chương")
    print(f"{'='*40}\n")


def run_schedule(source_name=DEFAULT_SOURCE, count=1, max_chapters=0):
    import schedule
    logger.info(f"⏰ Hàng ngày lúc {CRAWL_SCHEDULE} — nguồn: {source_name}")
    job = lambda: run_auto(source_name=source_name, count=count, max_chapters=max_chapters)
    schedule.every().day.at(CRAWL_SCHEDULE).do(job)
    job()
    while True:
        schedule.run_pending()
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("👋 Dừng.")
            break


if __name__ == '__main__':
    p = argparse.ArgumentParser(
        description='Crawler đa nguồn — yeungontinh | truyenfull | metruyencv',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--source', type=str, default=DEFAULT_SOURCE,
                   choices=list(SOURCES.keys()),
                   help=f'Nguồn crawl (mặc định: {DEFAULT_SOURCE})')
    p.add_argument('--interactive', '-i', action='store_true',
                   help='Chế độ tương tác: chọn nguồn + truyện thủ công')
    p.add_argument('--url', type=str, help='Crawl 1 URL cụ thể')
    p.add_argument('--count', type=int, default=1, help='Số truyện/lần (mặc định: 1)')
    p.add_argument('--max-chapters', type=int, default=0, help='Giới hạn chương (0=hết)')
    p.add_argument('--chapters', type=int, nargs='+', metavar='N',
                   help='Chỉ tải các chương cụ thể (VD: --chapters 1 12 15). Dùng với --url hoặc --interactive')
    p.add_argument('--schedule', action='store_true', help='Chạy hàng ngày tự động')
    p.add_argument('--test', action='store_true', help='Test (1 truyện, 3 chương)')
    p.add_argument('--list-sources', action='store_true', help='Liệt kê các nguồn có sẵn')
    p.add_argument('--docx-build', type=str, metavar='TITLE',
                   help='Build lại DOCX từ staged chapters của truyện (theo tên truyện)')
    p.add_argument('--docx-from-db', type=str, metavar='KEYWORD',
                   help='Đọc chương từ DB rồi stage + build DOCX (dùng cho truyện download trước khi có staging)')
    # Database management
    p.add_argument('--db-list', action='store_true', help='Liệt kê tất cả truyện trong database')
    p.add_argument('--db-delete', type=str, metavar='KEYWORD',
                   help='Xóa truyện theo tên, slug, hoặc id (hỗ trợ tìm kiếm một phần)')
    p.add_argument('--db-delete-all', action='store_true', help='Xóa TOÀN BỘ truyện và chương trong database')
    # Watchlist
    p.add_argument('--watch-add', type=str, metavar='URL', help='Thêm truyện vào watchlist')
    p.add_argument('--watch-remove', type=str, metavar='URL', help='Xóa truyện khỏi watchlist')
    p.add_argument('--watch-list', action='store_true', help='Xem danh sách truyện đang theo dõi')
    p.add_argument('--watch-check', action='store_true', help='Kiểm tra chương mới cho tất cả truyện trong watchlist')
    p.add_argument('--watch-download', action='store_true', help='Download chương mới cho tất cả truyện trong watchlist')
    p.add_argument('--seo', action='store_true',
                   help='Tự động phân tích SEO sau khi crawl, không hỏi confirm')
    p.add_argument('--seo-only', type=str, metavar='KEYWORD',
                   help='Chỉ tạo lại SEO cho truyện đã có trong DB (không crawl lại)')
    p.add_argument('--images', action='store_true',
                   help='Tạo ảnh minh hoạ FLUX.1-schnell cho từng chương sau khi crawl')
    p.add_argument('--images-only', type=str, metavar='KEYWORD',
                   help='Chỉ tạo thumbnail cho truyện đã có trong DB (không crawl lại)')
    p.add_argument('--shorts', action='store_true',
                   help='Tạo nội dung TikTok/YouTube Shorts: hook story + ảnh từng scene')
    p.add_argument('--shorts-only', type=str, metavar='KEYWORD',
                   help='Chỉ tạo Shorts (hook story + ảnh) cho truyện đã có trong DB (không crawl lại)')
    p.add_argument('--from-dir', type=str, metavar='NOVEL_DIR',
                   help='Tạo Shorts/Thumbnail từ thư mục truyện đã có (chapters/*.json). Dùng kèm --shorts và/hoặc --images. VD: --from-dir docx_output/2026-03-26/ten-truyen --shorts --images')
    p.add_argument('--shorts-seo', type=str, metavar='SHORTS_DIR',
                   help='Tạo lại Shorts SEO (TikTok + YouTube Shorts) từ hook_story.txt đã có, không crawl lại. Truyền đường dẫn thư mục shorts/')
    args = p.parse_args()

    chapter_filter = set(args.chapters) if args.chapters else None
    auto_seo    = args.seo     # True nếu có flag --seo
    auto_images = args.images  # True nếu có flag --images
    auto_shorts = args.shorts  # True nếu có flag --shorts

    # ── SEO only — tạo lại SEO cho truyện đã có trong DB ──────────
    # ── Shorts SEO from existing hook_story.txt ──────────────────
    if args.shorts_seo:
        import json as _json
        from seo_analyzer import analyze_shorts_seo
        from docx_exporter import _slugify
        from config import SITE_URL, DOCX_CHANNEL_NAME

        shorts_dir = os.path.abspath(args.shorts_seo)
        hook_path  = os.path.join(shorts_dir, 'hook_story.txt')
        scenes_path = os.path.join(shorts_dir, 'scenes.json')

        if not os.path.exists(hook_path):
            print(f"❌ Không tìm thấy hook_story.txt trong: {shorts_dir}")
            sys.exit(1)

        with open(hook_path, encoding='utf-8') as f:
            hook_story = f.read()

        # Đọc title và genres từ scenes.json nếu có
        title  = os.path.basename(os.path.dirname(shorts_dir))  # fallback: tên thư mục cha
        genres = 'ngon-tinh'
        if os.path.exists(scenes_path):
            try:
                with open(scenes_path, encoding='utf-8') as f:
                    sdata = _json.load(f)
                title  = sdata.get('title', title)
                genres = sdata.get('genres', genres)
            except Exception:
                pass

        slug      = _slugify(title)
        novel_url = f"{SITE_URL.rstrip('/')}/truyen/{slug}"

        print(f"📱 Tạo Shorts SEO cho: {title}")
        out = analyze_shorts_seo(
            title=title,
            genres=genres,
            hook_story=hook_story,
            shorts_dir=shorts_dir,
            channel_name=DOCX_CHANNEL_NAME,
            novel_url=novel_url,
        )
        if out:
            print(f"✅ Đã lưu: {out}")
        sys.exit(0)

    if args.seo_only:
        from db_helper import get_connection, get_novel_with_chapters
        from docx_exporter import _slugify

        conn = get_connection()
        novel, chapters = get_novel_with_chapters(conn, args.seo_only)
        conn.close()

        if not novel:
            print(f"❌ Không tìm thấy truyện khớp với: '{args.seo_only}'")
            sys.exit(1)

        print(f"📖 Tạo SEO cho: {novel['title']}")
        genres_str = novel.get('genres', '')
        ch_list = [{'content': c.get('content', '')} for c in chapters]
        # Tìm thư mục truyện (cũ flat hoặc mới theo ngày)
        existing_dir = _find_novel_dir(novel['title'])
        output_dir = existing_dir or os.path.join(_TODAY_DIR, _slugify(novel['title']))
        _analyze_seo_with_confirm(novel['title'], novel['author'], genres_str, ch_list, [], auto=True)
        sys.exit(0)

    # ── Images only (từ DB, không crawl lại) ─────────────────────
    if args.images_only:
        from db_helper import get_connection, get_novel_with_chapters

        conn = get_connection()
        novel, chapters = get_novel_with_chapters(conn, args.images_only)
        conn.close()

        if not novel:
            print(f"❌ Không tìm thấy truyện khớp với: '{args.images_only}'")
            sys.exit(1)

        title      = novel['title']
        genres_str = novel.get('genres', '')
        ch_list    = [dict(c) for c in chapters]
        novel_dir  = _find_novel_dir(title)
        docx_paths = []
        if novel_dir:
            docx_paths = [
                os.path.join(novel_dir, f)
                for f in os.listdir(novel_dir)
                if f.endswith('.docx')
            ]

        print(f"🖼️  Tạo thumbnail cho: {title}  ({len(ch_list)} chương)")
        _generate_images_with_confirm(title, genres_str, ch_list, docx_paths, auto=True)
        sys.exit(0)

    # ── Shorts only (từ DB, không crawl lại) ─────────────────────
    if args.shorts_only:
        from db_helper import get_connection, get_novel_with_chapters

        conn = get_connection()
        novel, chapters = get_novel_with_chapters(conn, args.shorts_only)
        conn.close()

        if not novel:
            print(f"❌ Không tìm thấy truyện khớp với: '{args.shorts_only}'")
            sys.exit(1)

        title      = novel['title']
        author     = novel.get('author', '')
        genres_str = novel.get('genres', '')
        ch_list    = [dict(c) for c in chapters]
        novel_dir  = _find_novel_dir(title)
        docx_paths = []
        if novel_dir:
            docx_paths = [
                os.path.join(novel_dir, f)
                for f in os.listdir(novel_dir)
                if f.endswith('.docx')
            ]

        print(f"📱 Tạo Shorts cho: {title}  ({len(ch_list)} chương)")
        _generate_shorts_with_confirm(title, author, genres_str, ch_list, docx_paths, auto=True)
        sys.exit(0)

    # ── From directory (chapters/*.json, không cần DB) ───────────
    if args.from_dir:
        import json as _json
        import glob as _glob
        import re as _re

        novel_dir = os.path.abspath(args.from_dir)
        if not os.path.isdir(novel_dir):
            print(f"❌ Không tìm thấy thư mục: {novel_dir}")
            sys.exit(1)

        # Đọc chapters từ chapters/*.json
        ch_files = sorted(_glob.glob(os.path.join(novel_dir, 'chapters', '*.json')))
        if not ch_files:
            print(f"❌ Không tìm thấy file JSON trong: {novel_dir}/chapters/")
            sys.exit(1)

        ch_list = []
        for f in ch_files:
            with open(f, encoding='utf-8') as fp:
                ch_list.append(_json.load(fp))

        # Đọc metadata từ seo.txt (nếu có)
        title      = ''
        author     = ''
        genres_str = ''
        seo_path   = os.path.join(novel_dir, 'seo.txt')
        if os.path.exists(seo_path):
            with open(seo_path, encoding='utf-8') as fp:
                for line in fp:
                    line = line.strip()
                    if not title and line and not line.startswith('=') and not line.startswith('#'):
                        title = line
                    m = _re.search(r'The loai[:\s]+([^\s|]+)', line, _re.IGNORECASE)
                    if m:
                        genres_str = m.group(1).strip()
                    m = _re.search(r'Tac gia[:\s]+([^|]+)', line, _re.IGNORECASE)
                    if m:
                        author = m.group(1).strip()

        # Fallback: lấy title từ tên thư mục
        if not title:
            title = os.path.basename(novel_dir).replace('-', ' ').title()

        # Tìm file DOCX trong thư mục (nếu có)
        docx_paths = [
            f for f in os.listdir(novel_dir) if f.endswith('.docx') and not f.startswith('~$')
        ]
        docx_paths = [os.path.join(novel_dir, f) for f in docx_paths]

        print(f"📂 Thư mục:  {novel_dir}")
        print(f"📚 Tiêu đề:  {title}")
        print(f"📖 Chương:   {len(ch_list)}  |  Thể loại: {genres_str or '(chưa rõ)'}")

        if not auto_shorts and not auto_images:
            print("⚠️  Thêm --shorts và/hoặc --images để chọn loại nội dung cần tạo.")
            sys.exit(0)

        if auto_images:
            _generate_images_with_confirm(title, genres_str, ch_list, docx_paths, auto=True)
        if auto_shorts:
            _generate_shorts_with_confirm(title, author, genres_str, ch_list, docx_paths, auto=True)
        sys.exit(0)

    # ── DOCX from DB command ──────────────────────────────────────
    if args.docx_from_db:
        from db_helper import get_connection, get_novel_with_chapters
        from docx_exporter import stage_chapters, build_docx_from_staged

        conn   = get_connection()
        novel, chapters = get_novel_with_chapters(conn, args.docx_from_db)
        conn.close()

        if not novel:
            print(f"❌ Không tìm thấy truyện khớp với: '{args.docx_from_db}'")
            sys.exit(1)

        title  = novel['title']
        author = novel['author']
        print(f"\n📚 '{title}' — {len(chapters)} chương trong DB")

        if not chapters:
            print("⚠️  Truyện chưa có chương nào.")
            sys.exit(1)

        print(f"   Chương {chapters[0]['number']} → {chapters[-1]['number']}")
        confirm = input("Stage + build DOCX? [Y/n] ").strip().lower()
        if confirm == 'n':
            print("❌ Hủy.")
            sys.exit(0)

        stage_chapters(title, chapters, _TODAY_DIR)
        out_paths = build_docx_from_staged(title, author, _TODAY_DIR, DOCX_CHANNEL_NAME)
        if out_paths:
            print(f"✅ Đã build {len(out_paths)} file DOCX:")
            for p in out_paths:
                print(f"   {p}")
        sys.exit(0)
    # ─────────────────────────────────────────────────────────────

    # ── DOCX build command ────────────────────────────────────────
    if args.docx_build:
        from docx_exporter import build_docx_from_staged, load_staged_chapters
        title = args.docx_build
        # Tìm thư mục chứa staged chapters (cũ flat hoặc mới theo ngày)
        novel_dir = _find_novel_dir(title)
        search_dir = os.path.dirname(novel_dir) if novel_dir else _TODAY_DIR
        chapters = load_staged_chapters(title, search_dir)
        if not chapters:
            print(f"❌ Không tìm thấy staged chapters cho '{title}'")
            print(f"   Đã tìm trong: {DOCX_OUTPUT_DIR} (cũ) và các thư mục ngày con")
            sys.exit(1)
        print(f"\n📚 '{title}' — {len(chapters)} chương staged (ch.{chapters[0]['number']} → ch.{chapters[-1]['number']})")
        out_paths = build_docx_from_staged(title, '', search_dir, DOCX_CHANNEL_NAME)
        if out_paths:
            print(f"✅ Đã build {len(out_paths)} file DOCX:")
            for p in out_paths:
                print(f"   {p}")
            # if SRT_EXPORT_ENABLED:
            #     _export_srt_with_confirm(out_paths)
        sys.exit(0)
    # ─────────────────────────────────────────────────────────────

    # ── Database management commands ─────────────────────────────
    if args.db_list:
        from db_helper import get_connection, get_all_novels, get_stats
        conn = get_connection()
        novels = get_all_novels(conn)
        stats  = get_stats(conn)
        conn.close()
        if not novels:
            print("📭 Database trống.")
        else:
            print(f"\n{'─'*80}")
            print(f"{'#':<5} {'Tiêu đề':<35} {'Tác giả':<18} {'Chương':<8} {'Views':<10} {'Trạng thái'}")
            print(f"{'─'*80}")
            for i, n in enumerate(novels, 1):
                status_icon = '✅' if n['publishStatus'] == 'published' else '⏳'
                title  = (n['title'] or '')[:34]
                author = (n['author'] or '')[:17]
                print(f"{i:<5} {title:<35} {author:<18} {n['chapterCount']:<8} {n['viewCount']:<10} {status_icon} {n['publishStatus']}")
            print(f"{'─'*80}")
            print(f"Tổng: {stats['novels']} truyện | {stats['chapters']} chương\n")
        sys.exit(0)

    if args.db_delete:
        from db_helper import get_connection, find_novel, delete_novel
        conn = get_connection()
        matches = find_novel(conn, args.db_delete)
        if not matches:
            print(f"❌ Không tìm thấy truyện khớp với: '{args.db_delete}'")
            conn.close()
            sys.exit(1)

        print(f"\n🔍 Tìm thấy {len(matches)} truyện:\n")
        for i, n in enumerate(matches, 1):
            print(f"  [{i}] {n['title']}")
            print(f"       slug: {n['slug']} | id: {n['id']} | {n['chapterCount']} chương")

        if len(matches) == 1:
            choice = 1
        else:
            sel = input("\nNhập số thứ tự muốn xóa (Enter để hủy): ").strip()
            if not sel.isdigit() or not (1 <= int(sel) <= len(matches)):
                print("❌ Hủy.")
                conn.close()
                sys.exit(0)
            choice = int(sel)

        target = matches[choice - 1]
        confirm = input(f"\n⚠️  Xóa '{target['title']}' ({target['chapterCount']} chương)? [y/N] ").strip().lower()
        if confirm != 'y':
            print("❌ Hủy.")
            conn.close()
            sys.exit(0)

        delete_novel(conn, target['id'])
        conn.close()
        print(f"🗑️  Đã xóa: {target['title']}")
        sys.exit(0)

    if args.db_delete_all:
        from db_helper import get_connection, get_stats, delete_all_novels
        conn = get_connection()
        stats = get_stats(conn)
        print(f"\n⚠️  Sắp xóa TOÀN BỘ {stats['novels']} truyện và {stats['chapters']} chương!")
        confirm1 = input("Nhập 'XOAHET' để xác nhận: ").strip()
        if confirm1 != 'XOAHET':
            print("❌ Hủy.")
            conn.close()
            sys.exit(0)
        delete_all_novels(conn)
        conn.close()
        print(f"🗑️  Đã xóa toàn bộ {stats['novels']} truyện và {stats['chapters']} chương.")
        sys.exit(0)
    # ─────────────────────────────────────────────────────────────

    # ── Watchlist commands ────────────────────────────────────────
    if args.watch_add:
        from watchlist import watch_add
        watch_add(args.watch_add, source_name=args.source)
        sys.exit(0)

    if args.watch_remove:
        from watchlist import watch_remove
        watch_remove(args.watch_remove)
        sys.exit(0)

    if args.watch_list:
        from watchlist import watch_list
        watch_list()
        sys.exit(0)

    if args.watch_check:
        from watchlist import watch_check
        watch_check()
        sys.exit(0)

    if args.watch_download:
        from watchlist import watch_check, watch_download, mark_downloaded
        # Auto-check first to get fresh data
        updated = watch_check()
        if not updated:
            sys.exit(0)
        targets = watch_download()
        if not targets:
            sys.exit(0)

        import config as _cfg
        if _cfg.REWRITE_ENABLED:
            ans = input(f"\n✍️  Rewriter đang bật. Viết lại nội dung? [Y/n] ").strip().lower()
            if ans == 'n':
                _cfg.REWRITE_ENABLED = False

        for entry in targets:
            url          = entry['url']
            source_name  = entry['source']
            new_chapters = entry['new_chapters']
            ch_filter    = set(new_chapters)

            logger.info(f"\n📥 {entry['title']} — tải chương {new_chapters}")
            if IMPORT_MODE == 'api':
                crawl_novel_api(url, source_name=source_name, chapter_filter=ch_filter)
            else:
                conn = get_connection()
                crawl_novel(url, source_name=source_name, conn=conn, chapter_filter=ch_filter)
                conn.close()

            mark_downloaded(url, new_chapters)

        sys.exit(0)
    # ─────────────────────────────────────────────────────────────

    if args.list_sources:
        from sources import registry
        print("\n📡 Nguồn có sẵn:")
        for key, src in SOURCES.items():
            domains = registry.domains_for(key)
            print(f"  --source {key:<18} {src.label}")
            print(f"  {'':18} domains: {', '.join(domains)}")
        sys.exit(0)

    if args.test:
        args.max_chapters = 3
        logger.info("🧪 TEST — 1 truyện, 3 chương")

    if args.interactive:
        run_interactive(max_chapters=args.max_chapters, chapter_filter=chapter_filter)
    elif args.url:
        # Auto-detect source from URL domain; fall back to --source flag
        try:
            detected = get_source_for_url(args.url)
            source_name = detected.name
            logger.info(f"🔍 Auto-detect nguồn: {detected.label}")
        except ValueError:
            source_name = args.source
            logger.info(f"🔍 Dùng nguồn chỉ định: {source_name}")

        # Ask user whether to use rewriter
        import config as _cfg
        if _cfg.REWRITE_ENABLED:
            print(f"\n✍️  Rewriter đang bật — provider: {_cfg.REWRITE_PROVIDER.upper()}")
            ans = input("   Bạn có muốn viết lại nội dung không? [Y/n] ").strip().lower()
            if ans == 'n':
                _cfg.REWRITE_ENABLED = False
                print("   ⏭️  Bỏ qua rewriter — chỉ định dạng đoạn văn\n")
            else:
                print()
                preflight_check_rewriter()
        else:
            print("\n⏭️  Rewriter đang tắt (REWRITE_ENABLED=False)\n")

        if chapter_filter:
            logger.info(f"🎯 Chỉ tải chương: {sorted(chapter_filter)}")

        if IMPORT_MODE == 'api':
            crawl_novel_api(args.url, source_name=source_name,
                            max_chapters=args.max_chapters, chapter_filter=chapter_filter)
        else:
            conn = get_connection()
            crawl_novel(args.url, source_name=source_name,
                        max_chapters=args.max_chapters, conn=conn, chapter_filter=chapter_filter)
            conn.close()
    elif args.schedule:
        run_schedule(source_name=args.source, count=args.count,
                     max_chapters=args.max_chapters)
    else:
        run_auto(source_name=args.source, count=args.count,
                 max_chapters=args.max_chapters)
