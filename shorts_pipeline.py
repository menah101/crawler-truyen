"""
Shorts Pipeline — Pipeline tạo nội dung TikTok/YouTube Shorts từ truyện.

Luồng:
  1. Chapters (truyện dài) → Hook Story (400-600 chữ) + Scenes (6-8 cảnh)
  2. Mỗi scene → ảnh FLUX.1-schnell (9:16 hoặc 16:9)
  3. Lưu ra thư mục:
       <output_dir>/
         hook_story.txt    ← đọc voice / TTS
         scenes.json       ← danh sách scenes + đường dẫn ảnh
         images/
           scene_001.jpg
           scene_002.jpg
           ...

Dùng độc lập:
  python shorts_pipeline.py --title "Tên truyện" --genre co-trang \\
      --chapters-file chapters.json --output-dir ./output/ten-truyen

Hoặc gọi từ run.py qua flag --shorts.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Image generation (dùng FLUX từ hongtran/make-video nếu có,
# fallback về inline implementation)
# ─────────────────────────────────────────────────────────────────

def _get_image_generators():
    """Tìm và import sentence_to_image + pick_shot_type từ make-video pipeline.

    Thứ tự thử:
    1. image_generator.py trong cùng thư mục crawler (copy trực tiếp)
    2. hongtran/make-video/pipeline/image_generator.py (máy dev)
    3. make-video/pipeline/image_generator.py (cùng thư mục crawler)
    4. Fallback inline

    Returns: (sentence_to_image_fn, pick_shot_type_fn)
    """
    import sys

    crawler_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Local copy trong crawler/
    if crawler_dir not in sys.path:
        sys.path.insert(0, crawler_dir)
    try:
        from image_generator import sentence_to_image, pick_shot_type
        return sentence_to_image, pick_shot_type
    except ImportError:
        pass

    # 2. hongtran/make-video (máy dev)
    hongtran_path = os.path.expanduser("~/data/hongtran/make-video")
    if os.path.isdir(hongtran_path):
        if hongtran_path not in sys.path:
            sys.path.insert(0, hongtran_path)
        try:
            from pipeline.image_generator import sentence_to_image, pick_shot_type
            return sentence_to_image, pick_shot_type
        except ImportError:
            pass

    # 3. make-video trong cùng thư mục crawler
    local_mv = os.path.join(crawler_dir, "make-video")
    if os.path.isdir(local_mv):
        if local_mv not in sys.path:
            sys.path.insert(0, local_mv)
        try:
            from pipeline.image_generator import sentence_to_image, pick_shot_type
            return sentence_to_image, pick_shot_type
        except ImportError:
            pass

    # 4. Fallback inline (pick_shot_type dùng rotation đơn giản)
    logger.warning("  ⚠️ Không tìm thấy make-video pipeline, dùng inline image generator")
    _ROTATION = ["medium", "close_up", "back_view", "atmospheric", "detail", "wide"]

    def _pick_shot_type_fallback(scene_index, total_scenes, emotion=""):  # noqa: ARG001
        if scene_index == 0:
            return "medium"
        if scene_index == total_scenes - 1:
            return "close_up"
        return _ROTATION[scene_index % len(_ROTATION)]

    return _sentence_to_image_inline, _pick_shot_type_fallback


# Giữ alias cũ để không break code khác
def _get_image_generator():
    fn, _ = _get_image_generators()
    return fn


_SAFE_BASE = (
    "safe for work, family friendly, fully clothed characters, "
    "no nudity, no bare skin, no adult content, no sexual content, no suggestive poses, "
    "complete image fully framed, no cropped limbs, "
    "perfect anatomy, correct human body, exactly two arms, two hands, "
    "no extra limbs, no missing limbs, no deformed hands, no extra fingers, no floating body parts"
)

_ERA_BRAND = {
    "co-trang":  f"ancient Chinese hanfu drama style, cinematic moody gold tones, film grain, 8K, no text, no watermark, {_SAFE_BASE}",
    "hien-dai":  f"modern Asian drama style, photorealistic, contemporary urban setting, cinematic lighting, 8K, no text, no watermark, {_SAFE_BASE}",
    "thap-nien": f"retro Vietnamese/Chinese drama, vintage film photography, nostalgic warm Kodachrome tones, film grain, 8K, no text, no watermark, {_SAFE_BASE}",
}

_ERA_DEFAULT_CHAR = {
    "co-trang":  "young Chinese woman in elegant hanfu",
    "hien-dai":  "young Asian woman in modern casual clothes",
    "thap-nien": "young woman in vintage era clothing",
}


def _sentence_to_image_inline(
    sentence, headers, ratio="9:16", era="co-trang", decade="",
    character_desc="", action="", setting="", seed=None,
    shot_type=None, scene_index=None, genre="",  # noqa: ARG001 — compat với image_generator
):
    """Inline fallback — không cần make-video."""
    import requests, io
    from PIL import Image

    SIZES = {"9:16": (768, 1344), "16:9": (1344, 768), "1:1": (1024, 1024)}
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

    brand_suffix = _ERA_BRAND.get(era, _ERA_BRAND["co-trang"])
    char_part    = character_desc or _ERA_DEFAULT_CHAR.get(era, "young woman")
    if era == "thap-nien" and decade and not character_desc:
        char_part = f"young woman in {decade} vintage fashion"
    scene_parts = ", ".join(p for p in [action, setting] if p)
    prompt = (
        f"safe for work, family friendly, fully clothed, no nudity, no adult content, "
        f"complete image fully framed, {char_part}, "
        f"{scene_parts + ', ' if scene_parts else ''}"
        f"{sentence[:150]}, {brand_suffix}"
    )

    width, height = SIZES.get(ratio, SIZES["9:16"])
    params = {"width": width, "height": height, "num_inference_steps": 4, "guidance_scale": 0.0}
    if seed is not None:
        params["seed"] = seed

    try:
        resp = requests.post(
            API_URL, headers=headers,
            json={"inputs": prompt, "parameters": params},
            timeout=120,
        )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        return Image.open(io.BytesIO(resp.content)), prompt
    except Exception as e:
        img = Image.new("RGB", (width, height), color=(13, 13, 26))
        return img, prompt


# ─────────────────────────────────────────────────────────────────
# Core pipeline
# ─────────────────────────────────────────────────────────────────

def run_shorts_pipeline(
    title: str,
    author: str,
    genres_str: str,
    chapters: list,
    output_dir: str,
    hf_token: str,
    ratio: str = "9:16",
    era_override: str = "",
    decade_override: str = "",
) -> dict:
    """
    Chạy toàn bộ pipeline: chapters → hook story + scenes + ảnh.

    Returns:
        {
            "hook_story_path": "...hook_story.txt",
            "scenes_path":     "...scenes.json",
            "images_dir":      "...images/",
            "scenes":          [...],
        }
    """
    from hook_generator import generate_hook_story

    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # ── Bước 1: Tạo hook story ──────────────────────────────────
    logger.info(f"\n📝 Tạo hook story cho: {title}")
    result = generate_hook_story(title, author, genres_str, chapters)

    hook_story = result.get("hook_story", "")
    scenes     = result.get("scenes", [])
    character      = result.get("character", {})
    character_desc = character.get("appearance", "")
    char_name      = character.get("name", "")
    era            = era_override or character.get("era", "co-trang")
    decade         = decade_override or character.get("decade", "")

    if not hook_story:
        logger.error("  ❌ Hook story trống — dừng pipeline")
        return {}

    if character_desc:
        logger.info(f"  👤 {char_name}: {character_desc[:80]}")

    # Lưu hook story
    hook_path = os.path.join(output_dir, "hook_story.txt")
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        if character_desc:
            f.write(f"[Nhân vật chính: {char_name} — {character_desc}]\n\n")
        f.write(hook_story)
    logger.info(f"  ✅ Đã lưu: {hook_path}")

    # ── Bước 2: Tạo ảnh cho từng scene ─────────────────────────
    if not hf_token:
        logger.warning("  ⚠️ HF_API_TOKEN chưa có — bỏ qua tạo ảnh")
        scenes_data = scenes
    else:
        sentence_to_image, pick_shot_type = _get_image_generators()
        headers = {"Authorization": f"Bearer {hf_token}"}
        genre   = genres_str.split(",")[0].strip() if genres_str else "co-trang"

        # Base seed từ title → mỗi scene dùng story_seed + sc_num để tạo ảnh khác nhau
        # Character desc giữ đồng nhất nhân vật; seed khác nhau tạo góc nhìn / bố cục khác
        import hashlib
        story_seed = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) % (2**31)
        logger.info(f"\n🎨 Tạo {len(scenes)} ảnh {ratio} → {images_dir}")
        if character_desc:
            logger.info(f"   Character anchor: {character_desc[:70]}")
        logger.info(f"   Base seed: {story_seed} (mỗi scene = base_seed + scene_num)")

        scenes_data = []
        total_scenes = len(scenes)

        for sc in scenes:
            sc_num   = sc["scene"]
            text     = sc["text"]
            emotion  = sc.get("emotion", "dramatic")
            action   = sc.get("action", "")
            setting  = sc.get("setting", "")
            img_name = f"scene_{sc_num:03d}.jpg"
            img_path = os.path.join(images_dir, img_name)

            shot_type = pick_shot_type(sc_num - 1, total_scenes, emotion)

            if os.path.exists(img_path):
                logger.info(f"  ⏭️  Scene {sc_num} đã có — bỏ qua")
            else:
                try:
                    # Seed khác nhau mỗi scene → bố cục / góc nhìn khác nhau
                    scene_seed = (story_seed + sc_num * 137) % (2**31)
                    image, prompt_used = sentence_to_image(
                        text, headers,
                        ratio=ratio,
                        genre=genre,
                        era=era,
                        decade=decade,
                        character_desc=character_desc,
                        action=action,
                        setting=setting,
                        seed=scene_seed,
                        shot_type=shot_type,
                        scene_index=sc_num - 1,
                    )
                    image.save(img_path, "JPEG", quality=92)
                    logger.info(f"  ✅ Scene {sc_num} [{emotion}|{shot_type}]: {img_name}")
                except Exception as e:
                    logger.error(f"  ❌ Scene {sc_num} lỗi: {e}")
                    img_path = ""

            scenes_data.append({
                **sc,
                "image": img_path if os.path.exists(img_path) else "",
            })

    # Lưu scenes.json
    scenes_path = os.path.join(output_dir, "scenes.json")
    payload = {
        "title":      title,
        "author":     author,
        "genres":     genres_str,
        "ratio":      ratio,
        "character":  character,
        "hook_story": hook_story,
        "scenes":     scenes_data,
    }
    with open(scenes_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"  ✅ Đã lưu: {scenes_path}")

    return {
        "hook_story_path": hook_path,
        "scenes_path":     scenes_path,
        "images_dir":      images_dir,
        "scenes":          scenes_data,
    }


# ─────────────────────────────────────────────────────────────────
# CLI standalone
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    p = argparse.ArgumentParser(description="Tạo hook story + ảnh từ chapters JSON")
    p.add_argument("--title",         required=True,  help="Tên truyện")
    p.add_argument("--author",        default="",     help="Tác giả")
    p.add_argument("--genre",         default="co-trang", help="Thể loại (slug)")
    p.add_argument("--chapters-file", required=True,
                   help="File JSON danh sách chapters [{number, content, ...}]")
    p.add_argument("--output-dir",    required=True,  help="Thư mục lưu kết quả")
    p.add_argument("--ratio",         default="9:16", choices=["9:16", "16:9", "1:1"])
    p.add_argument("--hf-token",      default=os.environ.get("HF_API_TOKEN", ""))
    args = p.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    with open(args.chapters_file, encoding="utf-8") as f:
        chapters = json.load(f)

    result = run_shorts_pipeline(
        title=args.title,
        author=args.author,
        genres_str=args.genre,
        chapters=chapters,
        output_dir=args.output_dir,
        hf_token=args.hf_token,
        ratio=args.ratio,
    )

    if result:
        print(f"\n✅ Xong!")
        print(f"   Hook story: {result['hook_story_path']}")
        print(f"   Scenes:     {result['scenes_path']}")
        print(f"   Ảnh:        {result['images_dir']}")
