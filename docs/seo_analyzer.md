# SEO Analyzer — Phân tích SEO YouTube

Module: `seo_analyzer.py`

Tạo tiêu đề YouTube, mô tả, hashtag, tóm tắt, tags website — dùng AI phân tích nội dung truyện.

## Sử dụng

```bash
# Kết hợp khi tải
python run.py --url "https://..." --seo

# Phân tích cho truyện đã tải
python run.py --seo-only "tên truyện"
```

## Output — file `seo.txt`

```
=== TIÊU ĐỀ YOUTUBE ===
Truyện Audio Đêm đó họ mở quan tài... | Hồng Trần Truyện Audio
Truyện Audio Tôi chứng kiến gia đình mình... | Hồng Trần Truyện Audio
...

=== MÔ TẢ YOUTUBE ===
Đêm tang lễ biến thành cơn ác mộng... | Nghe Con Cóc Vàng audio miễn phí
👉 Đọc truyện đầy đủ tại: https://hongtrantruyen.net/truyen/con-coc-vang

=== TAGS (500 ký tự, YouTube dùng để phân loại) ===
Con Cóc Vàng, ngôn tình, truyện audio, ...

=== TÓM TẮT (dùng cho pinned comment) ===
...

=== TAGS DÀNH CHO WEBSITE ===
bí ẩn gia tộc, linh vật, tham lam, ...
```

## Quy tắc tiêu đề

- Bắt đầu bằng `Truyện Audio`
- Hook cụ thể từ nội dung truyện (không chung chung)
- Kết thúc `| Hồng Trần Truyện Audio`
- Tối đa 80 ký tự
- Tạo 5-7 tiêu đề để chọn

## Quy tắc tags website

- 5-10 tags, phân cách bằng dấu phẩy
- Tiếng Việt có dấu
- Gồm: tropes, kiểu kết thúc (HE/BE/OE), bối cảnh, cảm xúc
