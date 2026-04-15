# TTS Generator — Hướng dẫn sử dụng

Chuyển nội dung truyện đã crawl thành audio MP3 bằng **Microsoft Edge TTS** (miễn phí, không cần GPU, không cần API key).

## Cài đặt

```bash
cd crawler
.venv/bin/pip install edge-tts
```

(Đã có sẵn trong [`requirements.txt`](requirements.txt) — `pip install -r requirements.txt` cũng được.)

## Giọng đọc tiếng Việt

| Key      | Voice ID                | Đặc điểm                                   |
|----------|-------------------------|--------------------------------------------|
| `female` | `vi-VN-HoaiMyNeural`    | Nữ, trong trẻo, hợp ngôn tình / hiện đại   |
| `male`   | `vi-VN-NamMinhNeural`   | Nam, trầm ấm, hợp kiếm hiệp / cổ trang     |

Edge TTS **không clone giọng** — chỉ chọn 1 trong 2 voice cố định trên.

## Cách dùng

### 1. Liệt kê truyện có sẵn

```bash
python tts_generator.py --list
```

In ra mọi novel trong `docx_output/<ngày>/<slug>/` đã có thư mục `chapters/`.

### 2. TTS toàn bộ 1 truyện (mỗi chương 1 file MP3)

Bằng slug (script tự tìm trong `docx_output/`):

```bash
python tts_generator.py lan-hen-cuoi-cung
python tts_generator.py lan-hen-cuoi-cung --voice male
python tts_generator.py lan-hen-cuoi-cung --voice female --rate -10%
```

Bằng path tuyệt đối:

```bash
python tts_generator.py /Users/Quy/.../docx_output/2026-04-15/do-an-toi-roi
```

**Output**: mỗi chương 1 file MP3, lưu vào subdir theo voice:

```
docx_output/2026-04-15/do-an-toi-roi/
└── audio/
    ├── female/
    │   ├── chapter_0001.mp3
    │   ├── chapter_0002.mp3
    │   └── …
    └── male/
        ├── chapter_0001.mp3
        └── …
```

Chạy 2 lần (1 lần `--voice female`, 1 lần `--voice male`) sẽ có cả 2 thư mục — không ghi đè lẫn nhau.

### 3. TTS 1 file đơn lẻ

Truyền thẳng path tới `.txt` hoặc `.json`:

```bash
python tts_generator.py docx_output/2026-04-15/do-an-toi-roi/chapters/0001.txt --voice female
python tts_generator.py crawler/docx_output/2026-04-15/do-an-toi-roi/shorts/hook_story.txt
```

Output đặt cùng thư mục, suffix theo voice:

```
0001.txt  →  0001.female.mp3
hook_story.txt  →  hook_story.female.mp3
```

## Tham số

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--voice {female,male}` | `female` | Chọn giọng |
| `--rate <pct>` | `-5%` | Tốc độ. Âm = chậm hơn, dương = nhanh hơn. VD `-10%`, `+5%` |
| `--list` | — | Liệt kê novel có sẵn rồi thoát |

## Định dạng chapter hỗ trợ

Trong `<novel>/chapters/`:

- **`*.json`** — format crawler đang xuất:
  ```json
  {"number": 1, "title": "Chương 1", "content": "Nội dung..."}
  ```
- **`*.txt`** — text thuần. Số chương lấy từ tên file (vd `0001.txt` → chương 1, `0023.txt` → chương 23).

Nếu cùng stem có cả `.json` và `.txt`, **`.json` được ưu tiên**.

## Resume / chạy lại

Script bỏ qua chapter nào đã có MP3 (`> 1KB`). An toàn để dừng giữa chừng:

```bash
# Chạy lần 1 — gen được 50/200 chương rồi tắt
^C

# Chạy lại cùng lệnh — tiếp từ chương 51, không gen lại 1-50
python tts_generator.py do-an-toi-roi --voice female
```

Muốn re-generate 1 chương: xoá file MP3 đó rồi chạy lại.

## Hiệu năng tham khảo

- Tốc độ: ~5,000 chars (≈1 chương ngôn tình) → MP3 ~3-5 MB → mất ~30-60s.
- Truyện 50,000 chars (~10 chương) → ~5-10 phút tổng.
- Truyện 500,000 chars (~100 chương) → ~50-100 phút (chạy nền được).

Nếu cần tăng tốc: chạy song song nhiều process trên các novel khác nhau (Edge TTS không có rate limit chặt, nhưng đừng spam quá ~10 request/giây).

## Workflow đề xuất

1. Crawl truyện như thường lệ → có `chapters/*.json`.
2. Sinh audio cả 2 voice cho user chọn:
   ```bash
   python tts_generator.py <slug> --voice female
   python tts_generator.py <slug> --voice male
   ```
3. Upload `audio/<voice>/*.mp3` lên S3 (tích hợp với hệ thống upload chapter audio đã có ở [`api_client.py`](api_client.py)).
4. Web frontend chọn voice nghe (hoặc cho user toggle).

## Troubleshooting

**"❌ edge-tts fail: No audio was received"** → text rỗng hoặc chứa ký tự lạ. Kiểm tra chapter JSON.

**MP3 nghe vỡ tiếng / ngắt nửa chừng** → text quá dài (~50k+ chars trong 1 call). Edge TTS có thể fail với input cực dài. Giải pháp: chia chương nhỏ hơn ở khâu crawl.

**Voice nói sai từ Hán Việt** → Edge TTS dựa trên Microsoft model, đôi khi đọc sai tên riêng Trung Quốc. Có thể "hint" bằng cách sửa lại trong content (vd "Giang Dật Phong" → "Giang Dật Phong" — viết tách rõ).

**Cần giọng khác / voice clone** → chuyển sang **viXTTS** (local, cần GPU, hỗ trợ clone reference voice 6-15s). Sẽ là module riêng nếu cần.
