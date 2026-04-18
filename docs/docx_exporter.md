# DOCX Exporter — Xuất file Word

Module: `docx_exporter.py`

Xuất truyện đã viết lại thành file `.docx` để dùng làm TTS hoặc đọc offline.

## Sử dụng

Sau khi tải, crawler tự hỏi có muốn xuất DOCX không. Hoặc xuất thủ công:

```bash
# Xuất DOCX cho truyện đã có trong database
python run.py --docx-build "tên truyện"

# Tìm theo từ khoá
python run.py --docx-from-db "ly hon"
```

## Output

```
docx_output/2026-03-25/ten-truyen/ten-truyen.docx
```

## Cấu hình

```env
DOCX_EXPORT_ENABLED=true
DOCX_CHANNEL_NAME=Hồng Trần Truyện Audio
```
