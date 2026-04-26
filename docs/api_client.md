# API Client — POST truyện mới lên pi4 thay vì ghi local DB

Module: `api_client.py`

Khi `IMPORT_MODE="api"`, crawler không ghi `prisma/dev.db` local mà POST trực tiếp lên endpoint `/api/admin/import` trên pi4.

## Khi nào dùng

| Mode | Dùng khi | Endpoint |
|------|----------|----------|
| `IMPORT_MODE="local"` *(default)* | Crawler chạy trên cùng máy host pi4 hoặc bạn muốn chỉ ghi local trước khi sync | — (ghi thẳng `prisma/dev.db`) |
| `IMPORT_MODE="api"` | Crawler chạy trên máy khác (không có DB pi4 local) | `POST /api/admin/import` |

⚠️ Khác với `wrapper_sync.py`:
- `api_client.import_novel()` → `/api/admin/import` — **tạo novel + chapter mới** (toàn bộ content)
- `wrapper_sync.py` → `/api/admin/wrappers` — **update 6 cột wrapper** cho novel/chapter đã tồn tại

Cả 2 dùng chung token `IMPORT_SECRET`.

## Cấu hình

`crawler/.env`:

```bash
IMPORT_MODE="api"                            # bật chế độ API
API_BASE_URL="http://192.168.1.50:3000"      # IP LAN pi4
IMPORT_SECRET="a3f8b2c9...f9a0"               # TRÙNG pi4 .env.local
```

Ngược về local mode: `IMPORT_MODE="local"` (hoặc xóa biến).

## Cách hoạt động

```
┌────────── Máy crawler ──────────┐       ┌────────── PI4 ──────────┐
│                                 │       │                         │
│  python run.py --url "..."      │       │  /api/admin/import      │
│         │                       │       │     │                   │
│         ├─ scrape + rewrite     │       │     ├─ tạo Novel        │
│         ├─ tạo cover/SEO/...    │ HTTP  │     ├─ insert Chapter   │
│         └─ import_novel(data)   │──────▶│     │   (skip duplicate)│
│                                 │ POST  │     └─ trả {inserted}   │
└─────────────────────────────────┘       └─────────────────────────┘
```

## Endpoint `POST /api/admin/import`

**Headers**:
- `Content-Type: application/json`
- `X-Import-Secret: <IMPORT_SECRET>`

**Body**:
```json
{
  "novel": {
    "title": "Ten Truyen",
    "author": "Tac Gia",
    "description": "...",
    "genres": "ngon-tinh",
    "tags": "tropes,...",
    "status": "completed",
    "source_url": "https://nguon.com/ten-truyen",
    "cover_image": "/abs/path/cover.jpg | https://... | ''"
  },
  "chapters": [
    {"number": 1, "title": "Chương 1", "content": "..."},
    {"number": 2, "title": "Chương 2", "content": "..."}
  ],
  "replace_chapters": false
}
```

**`replace_chapters`** (optional, default `false`):
- `false` (RESUME): SKIP chapter có cùng `(novelId, number)`, chỉ thêm chapter mới.
- `true` (REPLACE): DELETE TẤT CẢ chapter của novel trước khi INSERT từ payload.
  Bắt buộc dùng sau khi split/merge ở local vì chapter cũ và mới có cùng `number` nhưng content khác.

**Response** — schema phụ thuộc behavior pi4:
- Tạo mới: `{success, novel_id, slug, inserted, skipped, deleted: 0}`
- Resume: `{..., note: "novel_resumed", inserted: N, skipped: M}`
- Replace: `{..., note: "novel_replaced", inserted: N, deleted: M}`

## Mã nguồn

`import_novel(novel_data, chapters, *, replace_chapters=False)` → `dict`:
- Raise `RuntimeError` khi: thiếu env, 401, 400, timeout (>120s), network error, JSON invalid.
- Timeout cố định 120s — chương dài hoặc batch lớn có thể fail. Hạ `--max-chapters` hoặc tăng timeout trong code.

```python
from api_client import import_novel

# Resume mode (default) — chỉ thêm chapter mới
result = import_novel(novel_data, chapters)

# Replace mode — sau split/merge, đè toàn bộ chapter pi4
result = import_novel(novel_data, chapters, replace_chapters=True)
print(result['deleted'], result['inserted'])
```

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `❌ Xác thực thất bại (401)` | `IMPORT_SECRET` lệch | So với pi4 `.env.local`, phải giống hệt |
| `❌ Không kết nối được tới ...` | pi4 listen 127.0.0.1, firewall, IP sai | Xem [cach_3_http_sync.md §6](cach_3_http_sync.md#6-troubleshoot) |
| `❌ Timeout (>120s)` | Quá nhiều chương 1 lần | Giảm `--max-chapters`, hoặc chạy nhiều mẻ |
| `❌ Dữ liệu không hợp lệ (400)` | Field thiếu hoặc sai type | Check log payload đầu vào |

## Tham khảo

- [wrapper_sync.md](wrapper_sync.md) — endpoint `/api/admin/wrappers` (update wrapper)
- [cach_3_http_sync.md](cach_3_http_sync.md) — tổng quan HTTP sync
- [api_client.py](../api_client.py) — source
