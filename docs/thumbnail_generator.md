# Thumbnail Generator

Tạo thumbnail YouTube từ ảnh gốc + tiêu đề SEO.  
Tự phân tích màu ảnh để chọn bảng màu tương phản cao, phù hợp mọi loại hình nền.

## Cài đặt

```bash
pip install Pillow
```

Font hỗ trợ (ưu tiên từ trên xuống):
- Lato Black (`~/Library/Fonts/Lato-Black.ttf`)
- Roboto Condensed Bold (`~/Library/Fonts/RobotoCondensed-Bold.ttf`)
- Arial Bold
- DejaVu Sans Bold

## Sử dụng CLI

### Cơ bản

```bash
python thumbnail_generator.py <novel_dir>
```

Mặc định: lấy ảnh đầu tiên trong `thumbnails/`, đọc tiêu đề đầu tiên từ `seo.txt`, xuất ra `thumbnail_youtube.jpg`.

### Chọn tiêu đề

```bash
# Menu interactive — hiển thị danh sách, nhập số để chọn
python thumbnail_generator.py crawler/docx_output/2026-04-16/con-coc-vang

# 📋 Có 7 tiêu đề trong seo.txt:
#   1. Đêm đó họ mở quan tài... để lấy thứ không nên lấy
#   2. Tôi chứng kiến gia đình mình... biến chất sau một đêm tang lễ
#   3. Ngày ông nội ra đi, bí mật trong quan tài khiến tôi sợ hãi
#   ...
# Chọn tiêu đề (1-7, mặc định 1):

# Chọn trực tiếp bằng số (1-based)
python thumbnail_generator.py crawler/docx_output/2026-04-16/con-coc-vang --title-index 3

# Tiêu đề thủ công
python thumbnail_generator.py crawler/docx_output/2026-04-16/con-coc-vang --title "Tiêu đề tuỳ chọn"
```

### Chọn ảnh

```bash
python thumbnail_generator.py crawler/docx_output/2026-04-16/con-coc-vang --image thumb_03_close_up.jpg
```

### Tất cả options

| Option | Mô tả | Mặc định |
|--------|--------|----------|
| `novel_dir` | Thư mục novel (chứa `thumbnails/` và `seo.txt`) | *bắt buộc* |
| `--image` | Tên file ảnh trong `thumbnails/` | ảnh đầu tiên |
| `--title` | Tiêu đề thủ công (bỏ qua seo.txt) | đọc từ seo.txt |
| `--title-index` | Chọn tiêu đề theo STT (1-based) | menu interactive |
| `--output` | Tên file output | `thumbnail_youtube.jpg` |
| `--font-size` | Cỡ chữ | `62` |

## Sử dụng trong code

### Từ thư mục novel

```python
from thumbnail_generator import generate_from_novel_dir

# Mặc định: ảnh đầu tiên + tiêu đề đầu tiên từ seo.txt
generate_from_novel_dir("docx_output/2026-04-16/con-coc-vang")

# Chọn tiêu đề thứ 3
generate_from_novel_dir(
    "docx_output/2026-04-16/con-coc-vang",
    title_index=2,  # 0-based
)

# Chọn ảnh + tiêu đề thủ công
generate_from_novel_dir(
    "docx_output/2026-04-16/con-coc-vang",
    image_name="thumb_03_close_up.jpg",
    title="Tiêu đề tuỳ chọn",
)
```

### Truyền trực tiếp

```python
from thumbnail_generator import generate_thumbnail

generate_thumbnail(
    image_path="path/to/image.jpg",
    title="Dòng 1...\nDòng 2",
    output_path="output.jpg",
    font_size=56,
)
```

### Đọc danh sách tiêu đề

```python
from thumbnail_generator import extract_titles_from_seo

titles = extract_titles_from_seo("path/to/seo.txt")
# ['Đêm đó họ mở quan tài... để lấy thứ không nên lấy',
#  'Tôi chứng kiến gia đình mình... biến chất sau một đêm tang lễ',
#  ...]
```

## Cách hoạt động

### 1. Resize & crop

Ảnh gốc được scale + center crop về **1280×720** (chuẩn YouTube).

### 2. Phân tích màu tự động

Hàm `_analyze_colors` sample vùng nửa dưới ảnh (nơi text hiển thị) và tính:

- **Brightness** — perceived luminance `(0.299R + 0.587G + 0.114B)`
- **Dominant hue** — hue trung bình từ HSV
- **Saturation** — ảnh xám vs nhiều màu

Từ đó chọn bảng màu:

| Brightness | Background | Gradient | Mục đích |
|------------|-----------|----------|----------|
| < 0.3 (tối) | nhẹ 180α | 120 | Ảnh đã tối, chỉ cần bg mỏng |
| 0.3–0.55 (trung bình) | đậm 210α | 170 | Tăng tương phản vừa đủ |
| > 0.55 (sáng) | rất đậm 230α | 200 | Tương phản tối đa |

**Accent color** được chọn bổ sung (complementary) — dịch ~160° trên color wheel so với tone chính của ảnh. Nếu ảnh gần xám (saturation < 0.15), dùng mặc định vàng cam.

### 3. Vẽ text

- **Gradient tối** phủ từ 1/3 dưới ảnh lên, cường độ tuỳ brightness
- **Background box** bo góc 10px cho mỗi dòng chữ
- **Accent bar** 5px bên trái mỗi dòng
- **Text shadow** 2px offset + **text chính** màu trắng/kem
- Tiêu đề dài tự tách dòng tại `...` hoặc giữa câu

### 4. Cấu trúc thư mục đầu vào

```
novel_dir/
├── thumbnails/
│   ├── thumb_01_wide.jpg      ← ảnh gốc
│   ├── thumb_02_atmospheric.jpg
│   └── ...
├── seo.txt                     ← chứa tiêu đề YouTube
└── thumbnail_youtube.jpg       ← output
```

### 5. Format tiêu đề trong seo.txt

```
=== TIÊU ĐỀ YOUTUBE ===
Truyện Audio Đêm đó họ mở quan tài... | Hồng Trần Truyện Audio
Truyện Audio Tôi chứng kiến gia đình mình... | Hồng Trần Truyện Audio
...
```

Prefix `Truyện Audio` và suffix `| Hồng Trần Truyện Audio` được tự động loại bỏ khi render lên thumbnail.
