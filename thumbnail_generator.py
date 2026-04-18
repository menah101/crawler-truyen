"""
Tạo thumbnail YouTube từ ảnh gốc + tiêu đề SEO.
Tự phân tích màu ảnh để chọn bảng màu tương phản cao.

Usage:
    python thumbnail_generator.py <novel_dir>
    python thumbnail_generator.py crawler/docx_output/2026-04-16/con-coc-vang

    # Tuỳ chọn: chỉ định ảnh / tiêu đề thủ công
    python thumbnail_generator.py <novel_dir> --image thumb_03_close_up.jpg --title "Tiêu đề tuỳ chọn"
"""

import os
import re
import glob
import argparse
import logging

from PIL import Image, ImageDraw, ImageFont
from colorsys import rgb_to_hsv, hsv_to_rgb

logger = logging.getLogger(__name__)

# ── Layout constants ─────────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
FONT_SIZE = 62
PAD_X, PAD_Y = 32, 18
LINE_SPACING = 16
TEXT_BOTTOM_MARGIN = 50
BOX_RADIUS = 10
ACCENT_WIDTH = 5

# Font: ưu tiên Lato Black → Roboto Condensed Bold → Arial Bold → fallback
_FONT_CANDIDATES = [
    os.path.expanduser("~/Library/Fonts/Lato-Black.ttf"),
    os.path.expanduser("~/Library/Fonts/RobotoCondensed-Bold.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _find_font():
    """Tìm font bold đầu tiên có sẵn trên máy."""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "Không tìm được font bold. Cài Lato hoặc Roboto, "
        "hoặc truyền font_path vào generate_thumbnail()."
    )


# ── Color analysis ───────────────────────────────────────────────────

def _analyze_colors(img, width, height):
    """
    Phân tích vùng text (nửa dưới ảnh) để chọn bảng màu tương phản cao.

    Returns:
        dict với keys: text_color, shadow_color, bg_color, accent_color, gradient_strength
    """
    # Crop vùng nửa dưới — nơi text sẽ hiển thị
    text_region = img.crop((0, height // 2, width, height)).convert("RGB")
    pixels = list(text_region.tobytes())
    # Rebuild as (R,G,B) tuples
    pixels = [(pixels[i], pixels[i+1], pixels[i+2]) for i in range(0, len(pixels), 3)]

    # Tính trung bình R, G, B
    n = len(pixels)
    avg_r = sum(p[0] for p in pixels) / n
    avg_g = sum(p[1] for p in pixels) / n
    avg_b = sum(p[2] for p in pixels) / n

    # Brightness theo công thức perceived luminance
    brightness = (0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b) / 255.0

    # Dominant hue từ HSV
    h, s, v = rgb_to_hsv(avg_r / 255, avg_g / 255, avg_b / 255)

    # Saturation trung bình (ảnh xám vs ảnh nhiều màu)
    saturations = [rgb_to_hsv(p[0] / 255, p[1] / 255, p[2] / 255)[1] for p in pixels[::50]]
    avg_sat = sum(saturations) / len(saturations)

    logger.info(f"  Phân tích ảnh: brightness={brightness:.2f}, hue={h:.2f}, sat={avg_sat:.2f}")

    # ── Chọn accent color — màu bổ sung nổi bật ──
    if avg_sat < 0.15:
        # Ảnh gần xám → accent vàng cam nổi bật
        accent = (255, 200, 50, 255)
    else:
        # Chọn màu bổ sung (complementary) dịch 150-210° trên color wheel
        comp_h = (h + 0.45) % 1.0
        # Đẩy saturation và value lên cao để nổi bật
        ar, ag, ab = hsv_to_rgb(comp_h, max(0.7, avg_sat), 0.95)
        accent = (int(ar * 255), int(ag * 255), int(ab * 255), 255)

    # ── Chọn text color + background tuỳ brightness ──
    if brightness < 0.3:
        # Ảnh tối → text trắng ấm, bg tối nhẹ, gradient nhẹ
        text_color = (255, 250, 240, 255)
        shadow_color = (0, 0, 0, 200)
        bg_color = (15, 10, 5, 180)
        gradient_strength = 120
    elif brightness < 0.55:
        # Ảnh trung bình → text trắng sáng, bg tối đậm hơn, gradient mạnh
        text_color = (255, 255, 255, 255)
        shadow_color = (0, 0, 0, 220)
        bg_color = (10, 8, 5, 210)
        gradient_strength = 170
    else:
        # Ảnh sáng → text trắng, bg RẤT đậm để tạo tương phản, gradient mạnh nhất
        text_color = (255, 255, 255, 255)
        shadow_color = (0, 0, 0, 240)
        bg_color = (5, 5, 5, 230)
        gradient_strength = 200

    return {
        "text_color": text_color,
        "shadow_color": shadow_color,
        "bg_color": bg_color,
        "accent_color": accent,
        "gradient_strength": gradient_strength,
    }


# ── SEO helpers ──────────────────────────────────────────────────────

def extract_titles_from_seo(seo_path: str) -> list[str]:
    """
    Đọc TẤT CẢ tiêu đề trong section === TIÊU ĐỀ YOUTUBE ===,
    bỏ prefix 'Truyện Audio' và suffix '| Hồng Trần Truyện Audio'.
    Trả về list các tiêu đề.
    """
    with open(seo_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    titles = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if "TIÊU ĐỀ YOUTUBE" in stripped:
            in_section = True
            continue
        if in_section:
            if stripped.startswith("==="):
                break  # next section
            if not stripped:
                continue
            title = stripped
            # Bỏ prefix
            title = re.sub(r"^Truyện\s+Audio\s*", "", title).strip()
            # Bỏ suffix
            title = re.sub(r"\s*\|\s*Hồng Trần Truyện Audio\s*$", "", title).strip()
            if title:
                titles.append(title)

    if not titles:
        raise ValueError(f"Không tìm thấy tiêu đề YouTube trong {seo_path}")
    return titles


def extract_title_from_seo(seo_path: str, index: int = 0) -> str:
    """Lấy 1 tiêu đề theo index (mặc định: đầu tiên)."""
    titles = extract_titles_from_seo(seo_path)
    if index < 0 or index >= len(titles):
        raise IndexError(f"Chỉ có {len(titles)} tiêu đề, index {index} không hợp lệ")
    return titles[index]


def _auto_split_title(title: str, max_chars: int = 28) -> str:
    """
    Tự tách dòng nếu tiêu đề quá dài.
    Ưu tiên tách tại dấu '...' hoặc giữa câu.
    """
    if "\n" in title:
        return title

    if len(title) <= max_chars:
        return title

    # Tách tại '...' nếu có
    if "..." in title:
        parts = title.split("...", 1)
        return parts[0].strip() + "...\n" + parts[1].strip()

    # Tách gần giữa nhất tại khoảng trắng
    mid = len(title) // 2
    best = -1
    for i, ch in enumerate(title):
        if ch == " ":
            if best == -1 or abs(i - mid) < abs(best - mid):
                best = i
    if best > 0:
        return title[:best] + "\n" + title[best + 1:]

    return title


# ── Core ─────────────────────────────────────────────────────────────

def generate_thumbnail(
    image_path: str,
    title: str,
    output_path: str,
    *,
    font_path: str | None = None,
    font_size: int = FONT_SIZE,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> str:
    """
    Tạo thumbnail YouTube 1280×720 với text overlay.
    Tự phân tích màu ảnh để chọn bảng màu tương phản cao.

    Args:
        image_path: đường dẫn ảnh gốc (jpg/png)
        title:      tiêu đề hiển thị (có thể chứa \\n)
        output_path: nơi lưu file kết quả (.jpg)
        font_path:  đường dẫn font TTF (tự detect nếu None)
        font_size:  cỡ chữ (default 62)
        width:      chiều rộng output (default 1280)
        height:     chiều cao output (default 720)

    Returns:
        output_path
    """
    if font_path is None:
        font_path = _find_font()

    title = _auto_split_title(title)

    # ── Load & crop ảnh về đúng kích thước ──
    img = Image.open(image_path).convert("RGBA")
    scale = max(width / img.width, height / img.height)
    img = img.resize(
        (int(img.width * scale), int(img.height * scale)), Image.LANCZOS
    )
    left = (img.width - width) // 2
    top = (img.height - height) // 2
    img = img.crop((left, top, left + width, top + height))

    # ── Phân tích màu ảnh → chọn bảng màu tương phản ──
    colors = _analyze_colors(img, width, height)

    # ── Gradient tối phía dưới ──
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_g = ImageDraw.Draw(gradient)
    y_start = height // 3
    strength = colors["gradient_strength"]
    for y in range(y_start, height):
        alpha = int(strength * ((y - y_start) / (height - y_start)) ** 1.2)
        draw_g.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, gradient)

    # ── Vẽ text + background ──
    font = ImageFont.truetype(font_path, font_size)
    lines = title.split("\n")

    # Đo kích thước từng dòng
    line_metrics = []
    for line in lines:
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        y_offset = bbox[1]
        line_metrics.append((tw, th, y_offset))

    total_h = (
        sum(th + 2 * PAD_Y for _, th, _ in line_metrics)
        + LINE_SPACING * (len(lines) - 1)
    )
    y_cursor = height - total_h - TEXT_BOTTOM_MARGIN
    x_start = 50

    txt_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)

    for i, line in enumerate(lines):
        tw, th, y_off = line_metrics[i]

        box_x1 = x_start
        box_y1 = y_cursor
        box_x2 = x_start + tw + 2 * PAD_X
        box_y2 = y_cursor + th + 2 * PAD_Y

        # Background box
        draw.rounded_rectangle(
            [(box_x1, box_y1), (box_x2, box_y2)],
            radius=BOX_RADIUS,
            fill=colors["bg_color"],
        )

        # Accent bar bên trái
        draw.rounded_rectangle(
            [(box_x1, box_y1), (box_x1 + ACCENT_WIDTH, box_y2)],
            radius=2,
            fill=colors["accent_color"],
        )

        # Text shadow + text chính
        tx = x_start + PAD_X
        ty = y_cursor + PAD_Y - y_off
        draw.text((tx + 2, ty + 2), line, font=font, fill=colors["shadow_color"])
        draw.text((tx, ty), line, font=font, fill=colors["text_color"])

        y_cursor = box_y2 + LINE_SPACING

    img = Image.alpha_composite(img, txt_layer).convert("RGB")
    img.save(output_path, "JPEG", quality=95)
    logger.info(f"Thumbnail saved: {output_path}")
    return output_path


# ── Convenience: từ novel directory ──────────────────────────────────

def generate_from_novel_dir(
    novel_dir: str,
    *,
    image_name: str | None = None,
    title: str | None = None,
    title_index: int = 0,
    output_name: str = "thumbnail_youtube.jpg",
    **kwargs,
) -> str:
    """
    Tạo thumbnail từ thư mục novel (chứa thumbnails/ và seo.txt).

    Args:
        novel_dir:   thư mục novel (vd: docx_output/2026-04-16/con-coc-vang)
        image_name:  tên file ảnh trong thumbnails/ (None = lấy ảnh đầu tiên)
        title:       tiêu đề thủ công (None = đọc từ seo.txt)
        title_index: chọn tiêu đề theo index 0-based (default: 0)
        output_name: tên file output (default: thumbnail_youtube.jpg)
        **kwargs:    truyền thẳng vào generate_thumbnail()

    Returns:
        đường dẫn file output
    """
    thumb_dir = os.path.join(novel_dir, "thumbnails")
    seo_path = os.path.join(novel_dir, "seo.txt")

    # Chọn ảnh
    if image_name:
        image_path = os.path.join(thumb_dir, image_name)
    else:
        images = sorted(glob.glob(os.path.join(thumb_dir, "*.jpg")))
        if not images:
            images = sorted(glob.glob(os.path.join(thumb_dir, "*.png")))
        if not images:
            raise FileNotFoundError(f"Không tìm thấy ảnh trong {thumb_dir}")
        image_path = images[0]

    # Lấy tiêu đề
    if title is None:
        if not os.path.exists(seo_path):
            raise FileNotFoundError(f"Không tìm thấy {seo_path}")
        title = extract_title_from_seo(seo_path, index=title_index)

    output_path = os.path.join(novel_dir, output_name)

    logger.info(f"Image: {os.path.basename(image_path)}")
    logger.info(f"Title: {title}")

    return generate_thumbnail(image_path, title, output_path, **kwargs)


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tạo thumbnail YouTube cho truyện")
    parser.add_argument("novel_dir", help="Thư mục novel (chứa thumbnails/ và seo.txt)")
    parser.add_argument("--image", help="Tên file ảnh trong thumbnails/ (mặc định: ảnh đầu tiên)")
    parser.add_argument("--title", help="Tiêu đề thủ công (mặc định: đọc từ seo.txt)")
    parser.add_argument("--title-index", type=int, default=None,
                        help="Chọn tiêu đề theo số thứ tự (1-based). Không truyền = hiển thị menu chọn")
    parser.add_argument("--output", default="thumbnail_youtube.jpg", help="Tên file output")
    parser.add_argument("--font-size", type=int, default=FONT_SIZE, help="Cỡ chữ")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Nếu không truyền --title, hiển thị menu chọn tiêu đề
    title_index = 0
    if args.title is None:
        seo_path = os.path.join(args.novel_dir, "seo.txt")
        if os.path.exists(seo_path):
            titles = extract_titles_from_seo(seo_path)
            if args.title_index is not None:
                title_index = args.title_index - 1  # CLI 1-based → 0-based
            elif len(titles) > 1:
                print(f"\n📋 Có {len(titles)} tiêu đề trong seo.txt:\n")
                for i, t in enumerate(titles, 1):
                    print(f"  {i}. {t}")
                print()
                choice = input(f"Chọn tiêu đề (1-{len(titles)}, mặc định 1): ").strip()
                title_index = (int(choice) - 1) if choice.isdigit() and 1 <= int(choice) <= len(titles) else 0
                print()

    result = generate_from_novel_dir(
        args.novel_dir,
        image_name=args.image,
        title=args.title,
        title_index=title_index,
        output_name=args.output,
        font_size=args.font_size,
    )
    print(f"✅ {result}")


if __name__ == "__main__":
    main()
