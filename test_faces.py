"""
Test nhanh: tạo 5 ảnh close_up cho mỗi era.
Chạy: cd crawler && python test_faces.py
"""
import os, hashlib
from image_generator import sentence_to_image, _BEAUTY_CHARS

HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
if not HF_API_TOKEN:
    from config import HF_API_TOKEN

if not HF_API_TOKEN:
    print("❌ HF_API_TOKEN chưa được cấu hình")
    exit(1)

headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
out_dir = os.path.join(os.path.dirname(__file__), "_test_faces")
os.makedirs(out_dir, exist_ok=True)

ERAS = [
    ("co-trang", "", "co-trang"),
    ("hien-dai", "", "hien-dai"),
    ("thap-nien", "90s", "thap-nien"),
]

for era, decade, genre in ERAS:
    label = f"{era}{'_' + decade if decade else ''}"
    era_dir = os.path.join(out_dir, label)
    os.makedirs(era_dir, exist_ok=True)

    # Get pool size
    if era == "thap-nien":
        pool = _BEAUTY_CHARS["thap-nien"].get(decade or "default", [])
    else:
        pool = _BEAUTY_CHARS.get(era, [])
    print(f"\n{'='*60}")
    print(f"🎭 [{label.upper()}] — {len(pool)} nhân vật trong pool")
    print(f"{'='*60}")

    for idx in range(5):
        seed = int(hashlib.md5(f"test_{label}_face_{idx}".encode()).hexdigest()[:8], 16) % (2**31)
        desc = pool[idx % len(pool)][:70] if pool else "N/A"
        print(f"\n  [{idx+1}/5] seed={seed}")
        print(f"   {desc}...")

        image, prompt = sentence_to_image(
            sentence="beautiful scene",
            headers=headers,
            ratio="16:9",
            genre=genre,
            era=era,
            decade=decade,
            character_desc="",
            seed=seed,
            shot_type="close_up",
            scene_index=idx,
        )
        out_path = os.path.join(era_dir, f"face_{idx+1}.jpg")
        image.save(out_path, "JPEG", quality=95)
        print(f"   ✅ → {out_path}")

print(f"\n🎉 Done! Tổng 15 ảnh trong {out_dir}/")
print(f"   co-trang/  — 5 ảnh cổ trang mộng mơ")
print(f"   hien-dai/  — 5 ảnh hiện đại dịu dàng")
print(f"   thap-nien_90s/ — 5 ảnh thập niên 90")
