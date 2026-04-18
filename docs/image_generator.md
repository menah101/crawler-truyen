# Image Generator — Tạo ảnh thumbnail

Module: `image_generator.py`, `hf_image.py`

Tạo **30 ảnh thumbnail** tỷ lệ **16:9** (1344×768, chuẩn YouTube) bằng FLUX.1-schnell — mỗi ảnh khác nhau về góc chụp và nội dung, bám sát nội dung truyện.

## Sử dụng

```bash
# Kết hợp khi tải
python run.py --url "https://..." --images

# Tạo lại thumbnail cho truyện đã có trong database
python run.py --images-only "hanh phuc do toi tu tao"

# Tạo lại (xoá ảnh cũ trước nếu muốn)
rm docx_output/.../thumbnails/*.jpg
python run.py --url "https://..." --images
```

## Nhận diện thể loại

AI tự nhận diện thể loại để tạo đúng phong cách:

| Thể loại | Phong cách hình ảnh |
|----------|---------------------|
| **CỔ TRANG** | Hanfu, cung điện, ánh nến vàng, sương mù cổ phong |
| **HIỆN ĐẠI** | Trang phục hiện đại, căn hộ, văn phòng, thành phố |
| **THẬP NIÊN** | Thời trang retro 60s–2000s, phim cũ Kodachrome |

## Phân bổ góc chụp (30 ảnh)

| Góc chụp | Số lượng | Mô tả |
|----------|----------|-------|
| `wide` | 6 | Toàn cảnh, bối cảnh hoành tráng |
| `atmospheric` | 6 | Ánh sáng + không khí gợi cảm xúc |
| `close_up` | 6 | Mặt nhân vật, biểu cảm mạnh |
| `detail` | 4 | Vật thể biểu tượng (thư, trang sức...) |
| `action` | 4 | Cảnh chuyển động, góc nghiêng |
| `medium` | 3 | Nửa thân + môi trường |
| `two_shot` | 1 | Hai nhân vật đối diện |

## Output

```
docx_output/2026-03-25/ten-truyen/thumbnails/
  thumb_01_wide.jpg
  thumb_02_atmospheric.jpg
  ...
  thumb_30_close_up.jpg
```

## Cấu hình

```env
HF_API_TOKEN=hf_...        # HuggingFace token
HF_IMAGE_RATIO=16:9        # 16:9 (YouTube) | 9:16 (Shorts)
```
