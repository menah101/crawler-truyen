# Push Audio — đẩy MP3 chương từ local lên pi4

Module: `tts_generator.py` (sinh MP3 local) + `push_audio_to_pi4.py` (đẩy lên pi4).

Pipeline:

```
┌────────────────────────────────────────────────────────────┐
│  1. TTS local                                              │
│     python tts_generator.py <slug> --voice female          │
│       → docx_output/<date>/<slug>/audio/female/*.mp3       │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  2. Push pi4                                               │
│     python push_audio_to_pi4.py --slug <slug>              │
│       → POST /api/admin/upload-audio                       │
│         (multipart: file + slug + chapterNumber)           │
│       → pi4 upload S3 + update Chapter.audioUrl            │
└────────────────────────────────────────────────────────────┘
```

## Endpoint pi4: `/api/admin/upload-audio`

Auth: header `X-Import-Secret: <IMPORT_SECRET>` (cùng pattern với `/api/admin/import`).

Body (multipart/form-data):

| Field | Loại | Ý nghĩa |
|---|---|---|
| `file` | File MP3 (`audio/mpeg`) | Audio chương |
| `slug` | string | Slug novel trên pi4 |
| `chapterNumber` | string số nguyên | Số chương (>=1) |

Response 200:

```json
{
  "success": true,
  "chapterId": "c...",
  "slug": "ten-truyen",
  "chapterNumber": 1,
  "url": "https://bucket.s3.../chapters/<novelId>/<chapterId>.mp3?v=1735300000000",
  "duration": 432
}
```

Lỗi thường gặp:
- `401 Unauthorized` — sai `IMPORT_SECRET`.
- `404 Novel không tồn tại / Chương N của <slug> không tồn tại` — nhớ chạy `push_to_pi4.py --slug <slug>` trước.
- `413 File quá lớn` — quá 50 MB.
- `415 Chỉ chấp nhận audio/mpeg` — file không phải MP3 chuẩn.

S3 key: `chapters/<novelId>/<chapterId>.mp3` — upload lại sẽ overwrite (không sinh orphan), URL trả về có `?v=<timestamp>` để bypass cache.

## Tiền điều kiện

- Đã chạy `tts_generator.py` để có MP3 trong `docx_output/<date>/<slug>/audio/<voice>/chapter_NNNN.mp3`.
- Đã chạy `push_to_pi4.py --slug <slug>` để pi4 đã có novel + chapters tương ứng (vì endpoint locate chapter bằng `(slug, chapterNumber)`).
- `crawler/.env`: `API_BASE_URL` + `IMPORT_SECRET` đã set (giống pipeline crawl).

## Cách dùng

```bash
cd crawler

# Push 1 truyện (voice mặc định = female)
python push_audio_to_pi4.py --slug "ten-truyen"

# Voice khác
python push_audio_to_pi4.py --slug "ten-truyen" --voice male

# Push nhiều slug
python push_audio_to_pi4.py --slugs t1 t2 t3 --voice female

# Push toàn bộ slug có audio dưới 1 ngày
python push_audio_to_pi4.py --date 2026-04-27

# Force re-upload (bỏ qua marker)
python push_audio_to_pi4.py --slug "ten-truyen" --force

# Dry-run preview (không gọi API)
python push_audio_to_pi4.py --slug "ten-truyen" --dry-run
```

### Chọn ngày khi slug có ở nhiều ngày

Nếu cùng 1 slug được crawl 2 lần (2 ngày khác nhau, hiếm), script sẽ báo lỗi vì có nhiều `audio/` dirs khớp. Ép ngày:

```bash
python push_audio_to_pi4.py --slug "ten-truyen" --date-filter 2026-04-27
```

## Resume / re-upload

Sau mỗi MP3 push thành công, script ghi marker `chapter_NNNN.mp3.uploaded` (chứa URL S3) cùng thư mục. Lần chạy sau sẽ skip những file có marker.

```bash
# Chạy lần 1 — push được 5/10 chương rồi tắt
^C

# Chạy lại — tiếp từ chương 6
python push_audio_to_pi4.py --slug "ten-truyen"

# Force re-upload toàn bộ (vd: regenerate MP3)
python push_audio_to_pi4.py --slug "ten-truyen" --force
```

Re-upload **chỉ 1 chương**: xoá marker đó rồi chạy lại.

```bash
rm docx_output/2026-04-27/ten-truyen/audio/female/chapter_0003.mp3.uploaded
python push_audio_to_pi4.py --slug "ten-truyen"
```

## Workflow đề xuất (sau daily_pipeline)

```bash
cd crawler

# 1. Daily pipeline đã chạy xong → có novel + chapter trên pi4
./daily_pipeline.sh --yes

# 2. Sinh MP3 cho từng truyện (voice female mặc định)
for SLUG in ten-truyen-1 ten-truyen-2 ten-truyen-3; do
  python tts_generator.py "$SLUG" --voice female
done

# 3. Push tất cả MP3 hôm nay lên pi4
python push_audio_to_pi4.py --date $(date +%Y-%m-%d) --voice female
```

Tổng thời gian truyện 100 chương: TTS ~50-100 phút + upload ~3-5 phút (LAN).

## Hiệu năng / rate

- Default `--sleep 0.3s` giữa các upload → ~3 file/giây trên LAN.
- 1 truyện 100 chương × ~4MB → ~400 MB → ~2-3 phút trên LAN gigabit.
- Pi4 có thể là bottleneck (upload S3 từ pi4): tốc độ phụ thuộc băng thông internet của pi4. ~1-3s/file là bình thường.

## Tham khảo

- [tts.md](tts.md) — sinh MP3 bằng Edge TTS
- [daily_pipeline.md](daily_pipeline.md) — pipeline crawl + sync
- [api_client.md](api_client.md) — endpoint `/api/admin/import`
