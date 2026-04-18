# Cover Generator — Tạo ảnh bìa AI

Module: `cover_generator.py`

Tự động tạo ảnh bìa cho truyện bằng AI + FLUX.1-schnell khi nguồn không có ảnh bìa.

## Quy trình

1. AI phân tích truyện (mô tả + 3 chương đầu) → xác định nhân vật, xung đột, cao trào
2. Tạo 3 prompt theo 3 thể loại: **Hiện đại** / **Thập niên** / **Cổ trang**
3. Tự chọn prompt phù hợp với genre
4. FLUX.1-schnell tạo ảnh **9:16 dọc** (768×1344)
5. Nén JPEG < 200KB

## Sử dụng

```bash
# Tự động khi crawl (nếu nguồn không có cover)
python run.py --url "URL" --seo --images --shorts

# Tạo cover cho truyện đã có trong DB
python run.py --cover-only "tên truyện"

# Tạo cover từ thư mục chapters/*.json (không cần DB)
python run.py --cover-from-dir docx_output/2026-04-08/ten-truyen/chapters

# Tắt cover generation
COVER_ENABLED=false python run.py --url "URL"
```

## Phong cách & bố cục

- **Phong cách châu Á** — C-drama, K-drama, manhwa, donghua
- **Nhân vật Á Đông** — mắt hạnh nhân, da trắng ngần, tóc đen

| Kiểu bố cục | Mô tả |
|---|---|
| Chân dung cảm xúc | Close-up gương mặt, cảm xúc mãnh liệt |
| Đối đầu | 2 nhân vật đối mặt, ánh mắt căng thẳng |
| Lưng quay | Bóng dáng cô đơn bước đi trong bối cảnh rộng |
| Ôm ấp / bảo vệ | Khoảnh khắc thân mật, bám víu tuyệt vọng |
| Cô đơn giữa cảnh rộng | Nhân vật nhỏ bé giữa cung điện / thành phố |
| Bí ẩn | Nửa sáng nửa tối, gương mặt bị che khuất |
| Phản bội | Foreground đau đớn + background lạnh lùng |
| Hồi ức | Hiện tại mờ ảo lồng ghép quá khứ hạnh phúc |
| Nguy hiểm | Tình huống căng thẳng (mưa bão, lửa, vực thẳm) |

## AI fallback

1. **Gemini** (GEMINI_API_KEY) — nhanh, chất lượng tốt
2. **HuggingFace** (HF_API_TOKEN + Llama) — fallback khi Gemini hết quota
3. **Prompt mặc định** — random từ pool đa dạng bố cục

## Cấu hình

```env
COVER_ENABLED=true          # Bật/tắt (mặc định: bật)
HF_API_TOKEN=hf_...         # Dùng chung với thumbnail
```

Output: `docx_output/YYYY-MM-DD/ten-truyen/cover.jpg`
