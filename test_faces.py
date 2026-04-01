"""
Test nhanh: tạo 5 ảnh close_up để kiểm tra gương mặt khác nhau.
Chạy: cd crawler && python test_faces.py
"""
import os, hashlib
from image_generator import sentence_to_image, _BEAUTY_CHARS

# Token
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
if not HF_API_TOKEN:
    from config import HF_API_TOKEN

if not HF_API_TOKEN:
    print("❌ HF_API_TOKEN chưa được cấu hình")
    exit(1)

headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
out_dir = os.path.join(os.path.dirname(__file__), "_test_faces")
os.makedirs(out_dir, exist_ok=True)

title = "test-truyen"
era = "co-trang"  # Đổi thành "hien-dai" để test hiện đại

print(f"🎭 Beauty pool [{era}]: {len(_BEAUTY_CHARS[era])} nhân vật")
for i, desc in enumerate(_BEAUTY_CHARS[era]):
    print(f"   {i:2d}. {desc[:80]}...")

print(f"\n🖼️  Tạo 5 ảnh close_up → {out_dir}/")
for idx in range(5):
    seed = int(hashlib.md5(f"{title}_face_{idx}_close_up".encode()).hexdigest()[:8], 16) % (2**31)
    print(f"\n  [{idx+1}/5] scene_index={idx}, seed={seed}")
    print(f"   Nhân vật: {_BEAUTY_CHARS[era][idx % len(_BEAUTY_CHARS[era])][:70]}...")

    image, prompt = sentence_to_image(
        sentence="ancient palace scene",
        headers=headers,
        ratio="16:9",
        genre="co-trang",
        era=era,
        character_desc="",
        seed=seed,
        shot_type="close_up",
        scene_index=idx,
    )
    out_path = os.path.join(out_dir, f"face_{idx+1}.jpg")
    image.save(out_path, "JPEG", quality=95)
    print(f"   ✅ → {out_path}")
    print(f"   Prompt: {prompt[:120]}...")

print(f"\n🎉 Done! Mở thư mục {out_dir}/ để so sánh 5 gương mặt.")
