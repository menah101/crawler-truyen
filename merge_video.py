#!/usr/bin/env python3
"""
merge_video.py — Ghép ảnh + MP3 → video MP4.

Hai mode:

  shorts — Ghép ảnh scenes (8-10 cảnh) với MP3 TTS ngắn
           Mỗi scene chiếm: tổng_MP3 / số_scene (chia đều)
           Input : <novel>/shorts/scenes.json + images/ + *.mp3
           Output: <novel>/shorts/<tên_truyện>_shorts.mp4

  long   — Ghép thumbnail (20 ảnh) với MP3 dài (audio truyện đầy đủ)
           Mỗi thumbnail hiển thị 15s (hoặc --per-image), lặp vòng đến hết MP3
           Input : <novel>/thumbnails/*.jpg + <novel>/long/*.mp3
           Output: <novel>/long/<tên_truyện>_long.mp4

Cách dùng:
  python merge_video.py shorts docx_output/2026-03-25/ten-truyen/shorts
  python merge_video.py shorts docx_output/2026-03-25/ten-truyen/shorts --fade

  python merge_video.py long docx_output/2026-03-25/ten-truyen
  python merge_video.py long docx_output/2026-03-25/ten-truyen --per-image 12

Yêu cầu: ffmpeg (brew install ffmpeg)
"""

import os
import sys
import json
import math
import re
import argparse
import subprocess
import tempfile


# ─────────────────────────────────────────────────────────────────
# Tiện ích chung
# ─────────────────────────────────────────────────────────────────

def _check_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"❌ '{tool}' chưa được cài. Chạy: brew install ffmpeg")
            sys.exit(1)


def _get_audio_duration(mp3_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         mp3_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        print(f"❌ Không đọc được thời lượng: {mp3_path}")
        sys.exit(1)


def _find_mp3(directory: str) -> str | None:
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".mp3"):
            return os.path.join(directory, f)
    return None


def _probe_image_size(img_path: str) -> tuple[int, int]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", img_path],
        capture_output=True, text=True,
    )
    try:
        w, h = map(int, probe.stdout.strip().split(","))
        return w, h
    except Exception:
        return 0, 0


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_]+', '-', text).strip('-')[:60]


def _calc_output_size(w_orig: int, h_orig: int, target_w: int) -> tuple[int, int]:
    """Scale giữ tỷ lệ, chiều rộng = target_w, làm tròn lên bội số 2."""
    if w_orig == 0:
        return target_w, target_w * 16 // 9
    out_w = target_w
    out_h = int(out_w * h_orig / w_orig)
    if out_h % 2 != 0:
        out_h += 1
    return out_w, out_h


FPS        = 24     # framerate cố định cho toàn bộ output
_ZOOM_RANGE = 0.25  # 25%: đủ lớn để pixel/frame > 1 → mượt; đủ nhỏ để trông tự nhiên
_ZOOM_MAX   = 1.0 + _ZOOM_RANGE   # 1.25


def _build_scale_filter(out_w: int, out_h: int, scale: int = 1) -> str:
    w, h = out_w * scale, out_h * scale
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )


def _z_expr_clip(zoom: str, frames: int, idx: int) -> str:
    """
    Zoom expression cho xfade mode — `on` reset về 0 mỗi clip.

    Dùng easing cosine  (1−cos(π·t))/2  thay cho linear:
      - Bắt đầu chậm → tăng tốc → kết thúc chậm (smooth start/end)
      - Tránh cảm giác máy móc của linear
    Zoom range 25%: tại 1080p/24fps mỗi frame dịch ~2px → mượt, không giật.
    """
    t        = f"on/{frames}"
    ease     = f"(1-cos(PI*{t}))/2"
    expr_in  = f"1.0+{_ZOOM_RANGE}*{ease}"          # 1.0 → 1.25
    expr_out = f"{_ZOOM_MAX}-{_ZOOM_RANGE}*{ease}"  # 1.25 → 1.0
    if zoom == 'in':
        return expr_in
    if zoom == 'out':
        return expr_out
    return expr_in if idx % 2 == 0 else expr_out


def _z_expr_concat(zoom: str, fpi: int) -> str:
    """
    Zoom expression cho long video (concat demuxer).

    Vấn đề: `on` trong zoompan reset về 0 cho MỖI ảnh mới khi dùng concat demuxer.
    → Nửa chu kỳ cosine (như xfade mode) bị nhảy tại ranh giới: kết thúc ở 1.25,
      ảnh tiếp theo bắt đầu lại 1.0 → giật rõ.
    → floor(on/fpi) luôn = 0 → alternate không hoạt động.

    Fix: dùng cosine MỘT CHU KỲ ĐẦY ĐỦ (2π) — bắt đầu và kết thúc cùng giá trị
    → ranh giới hoàn toàn liền mạch, không cần track chỉ số ảnh.

      zoom_in  : 1.0 → 1.25 → 1.0  (thở vào)   — bắt đầu/kết thúc ở 1.0
      zoom_out : 1.25 → 1.0 → 1.25 (thở ra)    — bắt đầu/kết thúc ở 1.25
      alternate: giống zoom_in (alternate vô nghĩa khi on reset mỗi ảnh)
    """
    half = _ZOOM_RANGE / 2          # 0.125
    mid  = 1.0 + half               # 1.125
    expr_in  = f"{mid}-{half}*cos(2*PI*on/{fpi})"   # 1.0 → 1.25 → 1.0
    expr_out = f"{mid}+{half}*cos(2*PI*on/{fpi})"   # 1.25 → 1.0 → 1.25
    if zoom == 'out':
        return expr_out
    return expr_in  # 'in' và 'alternate' đều dùng full-cycle cosine


def _build_zoompan(z_expr: str, out_w: int, out_h: int, d: int = 1) -> str:
    """
    Zoompan filter: zoom tại trung tâm ảnh.

    Input nên được pre-scale lên 2× trước khi gọi filter này:
      iw = out_w*2, ih = out_h*2  →  mỗi frame pixel dịch gấp đôi
      →  không bị giật do sub-pixel integer rounding.

    d=1   → xfade mode (input đã là loop nhiều frame)
    d=fpi → concat mode (input chỉ decode 1 frame, zoompan tự gen đủ frame)
    """
    return (
        f"zoompan=z='{z_expr}'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={d}:s={out_w}x{out_h}:fps={FPS}"
    )


def _run_ffmpeg(cmd: list[str], concat_path: str | None = None):
    """Chạy ffmpeg, xoá file temp (nếu có), in lỗi nếu thất bại."""
    print("🎬 Đang render... (có thể mất vài phút)\n")
    # nice 10: hạ ưu tiên CPU để máy không bị nóng khi có tác vụ khác
    nice_cmd = ["nice", "-n", "10"] + cmd
    result = subprocess.run(nice_cmd, capture_output=True, text=True)
    if concat_path and os.path.exists(concat_path):
        os.unlink(concat_path)
    if result.returncode != 0:
        print("❌ ffmpeg lỗi:")
        print(result.stderr[-3000:])
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# MODE: shorts
# ─────────────────────────────────────────────────────────────────

def _load_scenes(shorts_dir: str) -> tuple[list[dict], str]:
    scenes_path = os.path.join(shorts_dir, "scenes.json")
    if not os.path.exists(scenes_path):
        print(f"❌ Không tìm thấy scenes.json trong {shorts_dir}")
        sys.exit(1)
    with open(scenes_path, encoding="utf-8") as f:
        data = json.load(f)

    valid = []
    for sc in data.get("scenes", []):
        img = sc.get("image", "")
        if img and os.path.exists(img):
            valid.append(sc)
        else:
            alt = os.path.join(shorts_dir, "images", f"scene_{sc['scene']:03d}.jpg")
            if os.path.exists(alt):
                sc["image"] = alt
                valid.append(sc)
            else:
                print(f"  ⚠️  Scene {sc['scene']}: không tìm thấy ảnh → bỏ qua")

    return valid, data.get("title", "output")


def _build_xfade_cmd(scenes: list[dict], mp3_path: str, output_path: str,
                     per_dur: float, fade_dur: float,
                     out_w: int, out_h: int,
                     zoom: str | None = None) -> list[str]:
    """
    Build ffmpeg command dùng xfade filter (crossfade mượt giữa từng scene).
    Có thể kết hợp với zoom-in / zoom-out / alternate per scene.

    Pipeline mỗi clip: [i:v] → scale → zoompan (nếu zoom) → xfade chain → [vout]
    """
    n = len(scenes)
    clip_dur = per_dur + fade_dur
    frames   = max(1, int(clip_dur * FPS))

    # Pre-scale 2× khi có zoom → zoompan làm việc trên 2× resolution
    # → mỗi frame pixel dịch gấp đôi → không bị giật sub-pixel rounding
    pre_w = out_w * 2 if zoom else out_w
    pre_h = out_h * 2 if zoom else out_h
    scale = (
        f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=decrease,"
        f"pad={pre_w}:{pre_h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={FPS}"
    )

    cmd = ["ffmpeg", "-y"]
    for sc in scenes:
        cmd += ["-loop", "1", "-t", f"{clip_dur:.4f}", "-i", sc["image"]]
    cmd += ["-i", mp3_path]
    audio_idx = n

    parts = []
    for i in range(n):
        per_clip_filter = scale
        if zoom:
            z_expr = _z_expr_clip(zoom, frames, i)
            per_clip_filter += "," + _build_zoompan(z_expr, out_w, out_h)
        parts.append(f"[{i}:v]{per_clip_filter}[s{i}]")

    if n == 1:
        parts.append("[s0]copy[vout]")
    else:
        prev = "[s0]"
        for i in range(1, n):
            offset    = max(0.01, i * per_dur - fade_dur)
            out_label = "[vout]" if i == n - 1 else f"[x{i}]"
            parts.append(
                f"{prev}[s{i}]xfade=transition=fade"
                f":duration={fade_dur:.3f}:offset={offset:.3f}{out_label}"
            )
            prev = f"[x{i}]"

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]",
        "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-threads", "2",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    return cmd


def merge_shorts(shorts_dir: str, mp3_path: str, output_path: str,
                 fade: bool = False, zoom: str | None = None,
                 target_width: int = 1080):
    """Ghép 8-10 scene images + MP3 ngắn → video Shorts/TikTok."""
    scenes, title = _load_scenes(shorts_dir)
    if not scenes:
        print("❌ Không có scene hợp lệ.")
        sys.exit(1)

    total_dur = _get_audio_duration(mp3_path)
    n         = len(scenes)
    per_dur   = total_dur / n
    fade_dur  = 0.4 if fade else 0.0

    w_orig, h_orig = _probe_image_size(scenes[0]["image"])
    if w_orig == 0:
        w_orig, h_orig = 768, 1344
    out_w, out_h = _calc_output_size(w_orig, h_orig, target_width)

    print(f"\n📊 Shorts: {title}")
    print(f"   Scenes    : {n}")
    print(f"   Audio     : {total_dur:.1f}s ({total_dur/60:.1f} phút)")
    print(f"   Mỗi scene : {per_dur:.2f}s")
    print(f"   Kích thước: {w_orig}×{h_orig} → {out_w}×{out_h}")
    print(f"   Fade      : {'xfade crossfade' if fade else 'không'}")
    print(f"   Zoom      : {zoom or 'không'}")
    print(f"   Output    : {output_path}\n")

    if fade or zoom:
        # Dùng xfade filter_complex — hỗ trợ cả fade và zoom per-scene
        cmd = _build_xfade_cmd(scenes, mp3_path, output_path,
                               per_dur, fade_dur, out_w, out_h, zoom=zoom)
        _run_ffmpeg(cmd)
    else:
        # Concat demuxer thuần — render nhanh nhất khi không cần hiệu ứng
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                        delete=False, encoding="utf-8") as f:
            concat_path = f.name
            for i, sc in enumerate(scenes):
                dur = per_dur + (0.5 if i == n - 1 else 0.0)
                f.write(f"file '{sc['image']}'\n")
                f.write(f"duration {dur:.4f}\n")
            f.write(f"file '{scenes[-1]['image']}'\n")

        vf = _build_scale_filter(out_w, out_h)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-i", mp3_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-threads", "2",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]
        _run_ffmpeg(cmd, concat_path)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"✅ Shorts video: {output_path}  ({size_mb:.1f} MB, {total_dur/60:.1f} phút)")


# ─────────────────────────────────────────────────────────────────
# MODE: long
# ─────────────────────────────────────────────────────────────────

def _load_thumbnails(novel_dir: str) -> list[str]:
    """Đọc tất cả thumbnail từ <novel>/thumbnails/ theo thứ tự."""
    thumbs_dir = os.path.join(novel_dir, "thumbnails")
    if not os.path.isdir(thumbs_dir):
        print(f"❌ Không tìm thấy thư mục thumbnails/: {thumbs_dir}")
        print("   Hãy chạy --images trước để tạo thumbnails.")
        sys.exit(1)

    images = sorted(
        os.path.join(thumbs_dir, f)
        for f in os.listdir(thumbs_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if not images:
        print(f"❌ Không có ảnh nào trong {thumbs_dir}")
        sys.exit(1)
    return images


def _find_latest_novel_dir(base: str | None = None) -> str:
    """Tìm thư mục truyện được tạo/sửa gần nhất trong docx_output/YYYY-MM-DD/<slug>/."""
    if base is None:
        base = os.path.join(os.path.dirname(__file__), "docx_output")
    if not os.path.isdir(base):
        print(f"❌ Không tìm thấy thư mục docx_output: {base}")
        sys.exit(1)

    candidates = []
    for date_dir in sorted(os.listdir(base), reverse=True):
        date_path = os.path.join(base, date_dir)
        if not os.path.isdir(date_path):
            continue
        for novel in sorted(os.listdir(date_path), reverse=True):
            novel_path = os.path.join(date_path, novel)
            if os.path.isdir(novel_path):
                candidates.append((os.path.getmtime(novel_path), novel_path))

    if not candidates:
        print("❌ Không tìm thấy truyện nào trong docx_output/")
        sys.exit(1)

    candidates.sort(reverse=True)
    return candidates[0][1]


# ─────────────────────────────────────────────────────────────────
# Overlay label
# ─────────────────────────────────────────────────────────────────

# Thư mục gốc chứa label — có 2 subfolder: short/ và long/
_LABEL_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label")
_LABEL_DIR_SHORT = os.path.join(_LABEL_BASE, "short")
_LABEL_DIR_LONG  = os.path.join(_LABEL_BASE, "long")

# Vị trí overlay — key khớp với tên file (vd: center-top.png, center-bottom.mp4)
_LABEL_POS = {
    "left-top":      {"scale": 0.20, "x": "10",                       "y": "10"},
    "top-left":      {"scale": 0.30, "x": "100",                      "y": "100"},
    "right-top":     {"scale": 0.20, "x": "main_w-overlay_w-10",      "y": "10"},
    "center-top":    {"scale": 1.00, "x": "(main_w-overlay_w)/2",     "y": "120"},
    "left-bottom":   {"scale": 0.20, "x": "10",                       "y": "main_h-overlay_h-10"},
    "right-bottom":  {"scale": 0.30, "x": "main_w-overlay_w",         "y": "main_h-overlay_h"},
    "center-bottom": {"scale": 0.60, "x": "(main_w-overlay_w)/2",     "y": "main_h-overlay_h-100"},
    "center":        {"scale": 0.50, "x": "(main_w-overlay_w)/2",     "y": "(main_h-overlay_h)/2"},
}


def overlay_label(video_path: str, label_dir: str = _LABEL_DIR_SHORT) -> bool:
    """
    Overlay PNG/MP4 labels lên video đã render.

    Files trong label_dir được đặt tên theo vị trí: center-top.png, right-top.mp4, ...
    Mỗi file tìm thấy được overlay theo đúng vị trí và tỷ lệ cấu hình trong _LABEL_POS.
    Kết quả ghi đè lên video_path gốc (qua file temp).
    Trả True nếu có ít nhất 1 label áp dụng thành công.
    """
    if not os.path.isdir(label_dir):
        print(f"⚠️  Không tìm thấy label dir: {label_dir}")
        return False

    # Tìm file label theo tên vị trí (mp4 ưu tiên hơn png)
    found: dict[str, dict] = {}
    for pos, cfg in _LABEL_POS.items():
        for ext in ("webm", "mp4", "png"):  # webm hỗ trợ alpha channel tốt nhất
            fpath = os.path.join(label_dir, f"{pos}.{ext}")
            if os.path.isfile(fpath):
                found[pos] = {"path": fpath, "cfg": cfg, "ext": ext}
                break

    if not found:
        print(f"⚠️  Không có file label nào trong {label_dir}")
        return False

    # Probe video width để tính pixel size của overlay
    vid_w, _ = _probe_image_size(video_path)
    if vid_w == 0:
        print("⚠️  Không đọc được kích thước video để tính scale label.")
        return False

    # Build inputs
    inputs: list[str] = ["-i", video_path]
    for info in found.values():
        if info["ext"] in ("mp4", "webm"):
            inputs += ["-stream_loop", "-1"]   # lặp overlay video tới hết video chính
        inputs += ["-i", info["path"]]

    # Build filter_complex: scale từng label → chồng lên lần lượt
    parts: list[str] = []
    prev = "[0:v]"
    for idx, (pos, info) in enumerate(found.items(), start=1):
        cfg     = info["cfg"]
        scale_w = max(1, int(vid_w * cfg["scale"]))
        out_v   = f"[v{idx}]"
        parts.append(f"[{idx}:v]scale={scale_w}:-1[lbl{idx}]")
        # format=auto: bật alpha blending — cần thiết cho PNG transparent và MP4 với alpha channel
        parts.append(f"{prev}[lbl{idx}]overlay={cfg['x']}:{cfg['y']}:format=auto{out_v}")
        prev = out_v

    tmp_path = video_path + ".lbl_tmp.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
        *inputs,
        "-filter_complex", ";".join(parts),
        "-map", prev,
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-threads", "2",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest", "-movflags", "+faststart",
        tmp_path,
    ]

    result = subprocess.run(["nice", "-n", "10"] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ overlay_label ffmpeg lỗi:\n{result.stderr[-2000:]}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False

    os.replace(tmp_path, video_path)
    labels = ", ".join(found.keys())
    print(f"🏷️  Label [{labels}] → {os.path.basename(video_path)}")
    return True


# ─────────────────────────────────────────────────────────────────
# Subtitle — Whisper transcribe + SRT mux
# ─────────────────────────────────────────────────────────────────

def generate_subtitle(mp3_path: str, srt_path: str, model_size: str = "tiny") -> bool:
    """
    Dùng faster-whisper (CPU, int8, beam_size=1) transcribe MP3 → .srt.
    Chạy SAU khi render video xong — không ảnh hưởng tốc độ render.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("❌ Cần cài: pip install faster-whisper")
        return False

    print(f"\n🎙️  Whisper ({model_size}) transcribe: {os.path.basename(mp3_path)}")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        mp3_path,
        language="vi",
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    print(f"   Ngôn ngữ: {info.language} ({info.language_probability:.0%})")

    def _fmt(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s   = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"

    lines, count = [], 0
    for seg in segments:
        count += 1
        lines += [str(count), f"{_fmt(seg.start)} --> {_fmt(seg.end)}", seg.text.strip(), ""]

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"   ✅ SRT: {os.path.basename(srt_path)}  ({count} dòng)")
    return True


def mux_subtitle(video_path: str, srt_path: str) -> bool:
    """
    Nhúng .srt vào MP4 bằng stream copy — không encode lại, hoàn thành trong vài giây.
    Ghi đè lên video_path gốc.
    """
    tmp_path = video_path + ".sub_tmp.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-i", video_path,
        "-i", srt_path,
        "-c", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=vie",
        "-movflags", "+faststart",
        tmp_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ mux_subtitle lỗi:\n{result.stderr[-2000:]}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False

    os.replace(tmp_path, video_path)
    print(f"💬 Subtitle → {os.path.basename(video_path)}")
    return True


def _read_novel_title(novel_dir: str) -> str:
    """Đọc tên truyện từ scenes.json (nếu có)."""
    for candidate in [
        os.path.join(novel_dir, "shorts", "scenes.json"),
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as f:
                    return json.load(f).get("title", "")
            except Exception:
                pass
    return os.path.basename(novel_dir)


def merge_long(novel_dir: str, mp3_path: str, output_path: str,
               per_image_sec: float = 15.0, fade: bool = False,
               zoom: str | None = None, target_width: int = 1920):
    """
    Ghép thumbnail (20 ảnh lặp vòng) + MP3 dài → video dạng long-form.

    - Mỗi thumbnail hiển thị per_image_sec giây
    - Sau hết 20 ảnh thì quay lại từ đầu, liên tục cho đến hết MP3
    - Zoom: dùng zoompan với mod(on, fpi) để effect reset mỗi ảnh mới
    """
    images    = _load_thumbnails(novel_dir)
    title     = _read_novel_title(novel_dir)
    total_dur = _get_audio_duration(mp3_path)
    n_imgs    = len(images)

    total_needed = math.ceil(total_dur / per_image_sec) + 1
    n_loops      = math.ceil(total_needed / n_imgs)
    looped       = [images[i % n_imgs] for i in range(total_needed)]

    w_orig, h_orig = _probe_image_size(images[0])
    if w_orig == 0:
        w_orig, h_orig = 1216, 384
    out_w, out_h = _calc_output_size(w_orig, h_orig, target_width)

    fpi = max(1, int(per_image_sec * FPS))  # frames per image

    print(f"\n📊 Long-form: {title}")
    print(f"   Thumbnails: {n_imgs} ảnh  ×  {n_loops} lần lặp")
    print(f"   Mỗi ảnh   : {per_image_sec}s  ({fpi} frames)")
    print(f"   Audio     : {total_dur:.1f}s  ({total_dur/60:.1f} phút)")
    print(f"   Tổng ảnh  : {total_needed}")
    print(f"   Kích thước: {w_orig}×{h_orig} → {out_w}×{out_h}")
    print(f"   Zoom      : {zoom or 'không'}")
    print(f"   Output    : {output_path}\n")

    if fade:
        print("  ℹ️  --fade không hỗ trợ mode long. Bỏ qua.")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                    delete=False, encoding="utf-8") as f:
        concat_path = f.name
        for i, img in enumerate(looped):
            f.write(f"file '{img}'\n")
            if i < len(looped) - 1:
                f.write(f"duration {per_image_sec:.4f}\n")

    if zoom:
        # Pre-scale 2× → zoompan làm việc trên 2× resolution → mượt hơn
        # d=fpi: concat decode 1 frame/ảnh → zoompan tự gen đủ fpi frame
        z_expr = _z_expr_concat(zoom, fpi)
        vf = _build_scale_filter(out_w, out_h, scale=2) + "," + _build_zoompan(z_expr, out_w, out_h, d=fpi)
    else:
        vf = _build_scale_filter(out_w, out_h)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_path,
        "-i", mp3_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-threads", "2",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    _run_ffmpeg(cmd, concat_path)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"✅ Long video : {output_path}  ({size_mb:.1f} MB, {total_dur/60:.1f} phút)")


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _check_ffmpeg()

    p = argparse.ArgumentParser(
        description="Ghép ảnh + MP3 → video MP4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Mode SHORTS — ghép scene images + MP3 ngắn:
  python merge_video.py shorts .../shorts
  python merge_video.py shorts .../shorts --fade
  python merge_video.py shorts .../shorts --zoom in
  python merge_video.py shorts .../shorts --zoom alternate --fade

Mode LONG — ghép thumbnail (20 ảnh lặp) + MP3 dài:
  python merge_video.py long .../ten-truyen
  python merge_video.py long .../ten-truyen --zoom in
  python merge_video.py long .../ten-truyen --zoom alternate --per-image 12

--zoom choices:
  in        : mỗi ảnh zoom in nhẹ từ 1.0 → 1.1 (Ken Burns effect)
  out       : mỗi ảnh zoom out từ 1.1 → 1.0
  alternate : xen kẽ zoom-in / zoom-out mỗi ảnh

Mode SUBTITLE — thêm subtitle vào video đã render (không render lại):
  python merge_video.py subtitle --video .../ten-truyen_shorts.mp4 --mp3 .../voice.mp3
  python merge_video.py subtitle --video .../ten-truyen_long.mp4 --mp3 .../ten-truyen.mp3 --model small
        """,
    )

    subparsers = p.add_subparsers(dest="mode", required=True)

    # ── Subcommand: shorts ─────────────────────────────────────────
    sp_shorts = subparsers.add_parser("shorts", help="Ghép scenes + MP3 ngắn")
    sp_shorts.add_argument("shorts_dir", nargs="?", default=None,
                           help="Thư mục shorts/ của truyện (bỏ trống + --latest để tự tìm)")
    sp_shorts.add_argument("--latest",  action="store_true",
                           help="Tự tìm truyện được tạo gần nhất trong docx_output/")
    sp_shorts.add_argument("--mp3",    default=None, help="File MP3 (tự tìm nếu bỏ trống)")
    sp_shorts.add_argument("--output", "-o", default=None, help="File MP4 output")
    sp_shorts.add_argument("--fade",   action="store_true", help="Crossfade mượt giữa các scene")
    sp_shorts.add_argument("--zoom",   choices=["in", "out", "alternate"], default=None,
                           help="Zoom effect: in / out / alternate (xen kẽ)")
    sp_shorts.add_argument("--width",  type=int, default=1080, help="Chiều rộng (mặc định: 1080)")
    sp_shorts.add_argument("--label",  action="store_true",
                           help="Overlay label PNG/MP4 từ thư mục label/short/ lên video sau khi render")
    sp_shorts.add_argument("--label-dir", default=_LABEL_DIR_SHORT,
                           help=f"Thư mục chứa label (mặc định: label/short/)")
    sp_shorts.add_argument("--subtitle", action="store_true",
                           help="Tạo subtitle từ MP3 bằng Whisper rồi nhúng vào video (pip install faster-whisper)")
    sp_shorts.add_argument("--whisper-model", default="tiny",
                           choices=["tiny", "small", "medium", "large"],
                           help="Model Whisper (mặc định: tiny — nhanh nhất, ít RAM nhất)")

    # ── Subcommand: long ───────────────────────────────────────────
    sp_long = subparsers.add_parser("long", help="Ghép thumbnails lặp + MP3 dài")
    sp_long.add_argument("novel_dir", nargs="?", default=None,
                         help="Thư mục gốc của truyện (bỏ trống + --latest để tự tìm truyện mới nhất)")
    sp_long.add_argument("--latest",    action="store_true",
                         help="Tự tìm truyện được tạo gần nhất trong docx_output/")
    sp_long.add_argument("--mp3",       default=None,  help="File MP3 (tự tìm trong long/ nếu bỏ trống)")
    sp_long.add_argument("--output",    "-o", default=None, help="File MP4 output")
    sp_long.add_argument("--per-image", type=float, default=15.0,
                         help="Số giây mỗi ảnh hiển thị (mặc định: 15)")
    sp_long.add_argument("--fade",      action="store_true", help="(không hỗ trợ mode long)")
    sp_long.add_argument("--zoom",      choices=["in", "out", "alternate"], default=None,
                         help="Zoom effect: in / out / alternate (xen kẽ)")
    sp_long.add_argument("--width",     type=int, default=1920,
                         help="Chiều rộng output (mặc định: 1920 cho Full HD)")
    sp_long.add_argument("--label",     action="store_true",
                         help="Overlay label PNG/MP4 từ thư mục label/long/ lên video sau khi render")
    sp_long.add_argument("--label-dir", default=_LABEL_DIR_LONG,
                         help=f"Thư mục chứa label (mặc định: label/long/)")
    sp_long.add_argument("--subtitle", action="store_true",
                         help="Tạo subtitle từ MP3 bằng Whisper rồi nhúng vào video (pip install faster-whisper)")
    sp_long.add_argument("--whisper-model", default="tiny",
                         choices=["tiny", "small", "medium", "large"],
                         help="Model Whisper (mặc định: tiny — nhanh nhất, ít RAM nhất)")

    # ── Subcommand: subtitle ───────────────────────────────────────
    sp_sub = subparsers.add_parser("subtitle", help="Thêm subtitle vào video đã render (không render lại)")
    sp_sub.add_argument("--video", required=True, help="File MP4 cần thêm subtitle")
    sp_sub.add_argument("--mp3",   required=True, help="File MP3 để Whisper transcribe")
    sp_sub.add_argument("--model", default="tiny",
                        choices=["tiny", "small", "medium", "large"],
                        help="Model Whisper (mặc định: tiny)")

    args = p.parse_args()

    # ── Xử lý mode shorts ─────────────────────────────────────────
    if args.mode == "shorts":
        if args.latest:
            novel_dir = _find_latest_novel_dir()
            shorts_dir = os.path.join(novel_dir, "shorts")
            print(f"📂 Truyện mới nhất: {novel_dir}")
        elif args.shorts_dir:
            shorts_dir = os.path.abspath(args.shorts_dir)
        else:
            print("❌ Cần truyền đường dẫn hoặc dùng --latest")
            sys.exit(1)
        if not os.path.isdir(shorts_dir):
            print(f"❌ Không tìm thấy: {shorts_dir}")
            sys.exit(1)

        mp3_path = args.mp3 or _find_mp3(shorts_dir)
        if not mp3_path:
            print(f"❌ Không tìm thấy MP3 trong {shorts_dir}  — upload .mp3 vào đây hoặc dùng --mp3")
            sys.exit(1)
        if not os.path.exists(mp3_path):
            print(f"❌ File không tồn tại: {mp3_path}")
            sys.exit(1)
        print(f"🎵 Audio: {os.path.basename(mp3_path)}")

        if args.output:
            output_path = args.output
        else:
            scenes_json = os.path.join(shorts_dir, "scenes.json")
            title = "output"
            if os.path.exists(scenes_json):
                try:
                    with open(scenes_json, encoding="utf-8") as f:
                        title = _slugify(json.load(f).get("title", "output"))
                except Exception:
                    pass
            output_path = os.path.join(shorts_dir, f"{title}_shorts.mp4")

        merge_shorts(shorts_dir, mp3_path, output_path,
                     fade=args.fade, zoom=args.zoom, target_width=args.width)

        if args.label:
            overlay_label(output_path, label_dir=args.label_dir)

        if args.subtitle:
            srt_path = output_path.replace(".mp4", ".srt")
            if generate_subtitle(mp3_path, srt_path, model_size=args.whisper_model):
                mux_subtitle(output_path, srt_path)

    # ── Xử lý mode subtitle ────────────────────────────────────────
    elif args.mode == "subtitle":
        video_path = os.path.abspath(args.video)
        mp3_path   = os.path.abspath(args.mp3)
        if not os.path.exists(video_path):
            print(f"❌ Không tìm thấy video: {video_path}")
            sys.exit(1)
        if not os.path.exists(mp3_path):
            print(f"❌ Không tìm thấy MP3: {mp3_path}")
            sys.exit(1)
        srt_path = video_path.replace(".mp4", ".srt")
        if generate_subtitle(mp3_path, srt_path, model_size=args.model):
            mux_subtitle(video_path, srt_path)

    # ── Xử lý mode long ──────────────────────────────────────────
    elif args.mode == "long":
        if args.latest:
            novel_dir = _find_latest_novel_dir()
            print(f"📂 Truyện mới nhất: {novel_dir}")
        elif args.novel_dir:
            novel_dir = os.path.abspath(args.novel_dir)
        else:
            print("❌ Cần truyền đường dẫn hoặc dùng --latest")
            sys.exit(1)
        if not os.path.isdir(novel_dir):
            print(f"❌ Không tìm thấy: {novel_dir}")
            sys.exit(1)

        # Tạo thư mục long/ nếu chưa có
        long_dir = os.path.join(novel_dir, "long")
        os.makedirs(long_dir, exist_ok=True)

        mp3_path = args.mp3 or _find_mp3(long_dir)
        if not mp3_path:
            print(f"❌ Không tìm thấy MP3 trong {long_dir}")
            print(f"   Upload file .mp3 vào {long_dir}  hoặc dùng --mp3 <file>")
            sys.exit(1)
        if not os.path.exists(mp3_path):
            print(f"❌ File không tồn tại: {mp3_path}")
            sys.exit(1)
        print(f"🎵 Audio: {os.path.basename(mp3_path)}")

        if args.output:
            output_path = args.output
        else:
            title = _slugify(_read_novel_title(novel_dir) or os.path.basename(novel_dir))
            output_path = os.path.join(long_dir, f"{title}_long.mp4")

        merge_long(novel_dir, mp3_path, output_path,
                   per_image_sec=args.per_image,
                   fade=args.fade,
                   zoom=args.zoom,
                   target_width=args.width)

        if args.label:
            overlay_label(output_path, label_dir=args.label_dir)

        if args.subtitle:
            srt_path = output_path.replace(".mp4", ".srt")
            if generate_subtitle(mp3_path, srt_path, model_size=args.whisper_model):
                mux_subtitle(output_path, srt_path)
