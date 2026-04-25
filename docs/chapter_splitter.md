# Chapter Splitter — Tách chương cho thin novels

Module: `chapter_splitter.py`

Tăng số chương cho truyện < `MIN_CHAPTERS` (mặc định 5) bằng cách tách mỗi chương thành nhiều mảnh tại scene break tự nhiên — **giữ nguyên 100% nội dung**, không rewrite.

## Khi nào dùng

`audit_indexable.py` báo "Thin novels (< 5 chương)" → có 2 lựa chọn:
1. **Hide** (`publishStatus='pending'`) — đơn giản, mất catalog.
2. **Tách chương** (module này) — giữ catalog, qua ngưỡng AdSense.

Module chỉ phù hợp khi **chương gốc đủ dài**: ngưỡng `MIN_WORDS_PER_PIECE = 400` từ/mảnh — tổng từ của truyện phải ≥ `target × 400`. Truyện không đủ → script tự skip.

## Dùng

```bash
cd crawler

# Preview trước (không ghi DB, không backup)
python chapter_splitter.py --slug "ten truyen" --target 10 --dry-run

# Apply 1 truyện — auto-backup DB
python chapter_splitter.py --slug "ten truyen" --target 10

# Apply tất cả thin novels (< 5 chương) về target 10
python chapter_splitter.py --all-thin --target 10

# Test 5 truyện đầu trước
python chapter_splitter.py --all-thin --target 10 --max-novels 5 --dry-run
```

### Options

| Flag | Default | Ý nghĩa |
|------|---------|---------|
| `--slug KEYWORD` | — | Split chương 1 truyện |
| `--all-thin` | — | Loop mọi novel `published` có < `min-chapters` chương |
| `--retitle-fallbacks` | — | Tìm chapter có title `Phần N` và đặt title có nghĩa qua LLM (chỉ UPDATE title, không động content) |
| `--target N` | `10` | Số chương sau split |
| `--min-chapters N` | `5` | Ngưỡng filter cho `--all-thin` |
| `--max-novels N` | `0` | Giới hạn số truyện khi `--all-thin` (0 = hết) |
| `--dry-run` | — | Preview, không ghi DB |
| `--sleep N` | `1.0` | Delay giữa các LLM call (giây) |
| `--no-backup` | — | Bỏ qua backup DB (cẩn thận!) |

## Cách hoạt động

```
┌── chương gốc 4000 từ, 60 đoạn ──┐
│                                  │
│  [Đoạn 1] ...                    │
│  [Đoạn 2] ...                    │   gọi LLM:
│  ...                             │   "tìm 2 vị trí cắt
│  [Đoạn 60]                       │    để tách 3 mảnh"
└──────────────────────────────────┘
              │
              ▼
   LLM trả: {"splits": [22, 41], "titles": ["Cuộc gặp", "Hồi tưởng", "Đối mặt"]}
              │
              ▼
┌── 3 mảnh, mỗi mảnh ~1300 từ ────┐
│  Phần 1: đoạn 1-22  (1450 từ)   │
│  Phần 2: đoạn 23-41 (1300 từ)   │
│  Phần 3: đoạn 42-60 (1250 từ)   │
└──────────────────────────────────┘
```

### 5 bước nội bộ

1. **Backup DB** → `prisma/dev.db.split-bak.<timestamp>` (skip với `--no-backup`).
2. **Compute split plan** — phân bổ số mảnh cho mỗi chương theo tỷ lệ wordCount, đảm bảo:
   - Mỗi mảnh ≥ `MIN_WORDS_PER_PIECE` (400 từ)
   - Tổng số mảnh = `target`
   - Chương quá ngắn (< 800 từ) giữ nguyên
3. **LLM tìm split points** — với mỗi chương cần split, gọi LLM với prompt:
   ```
   Cắt {n_pieces} phần tại scene break.
   Trả JSON {"splits": [paragraph_indices], "titles": [tên phần]}
   KHÔNG sửa nội dung.
   ```
4. **Apply split** — theo split points, tạo list `[(title, content), ...]`.
5. **Sanity check + DB write** — kiểm tra `sum(new wordCount) ≈ old wordCount` (lệch < 2% mới ghi). Trong 1 transaction:
   - `DELETE FROM Chapter WHERE novelId=?`
   - `INSERT` chapter mới renumber 1..N

## Sanity check (quan trọng)

```python
old_total = sum(_count_words(c["content"]) for c in old_chapters)
new_total = sum(_count_words(c[1]) for c in new_chapters)
assert abs(old_total - new_total) <= old_total * 0.02
```

Nếu LLM lén "rewrite" thay vì chỉ "split", sanity check sẽ fail và script dừng — DB không bị thay đổi.

## Fallback an toàn

LLM có thể fail (provider sai config, JSON parse lỗi, ...). Script auto-fallback:

| Tình huống | Fallback | Ảnh hưởng |
|------------|----------|-----------|
| LLM trả invalid JSON | Chia đều paragraphs | Title generic `Phần 1/2/3`, content vẫn đúng |
| Chương < 2*n_pieces đoạn | Giữ nguyên không split | Số chương cuối < target |
| Chương < `MIN_WORDS_TO_SPLIT` | Giữ nguyên | Như trên |
| Tổng từ < target × 400 | Skip cả truyện | Báo "too_short" |
| 429 rate limit | Retry 3 lần (backoff 30s/60s) → fallback chia đều | Title generic, content vẫn đúng |

### Fix title generic sau khi split — `--retitle-fallbacks`

Nếu sau khi split có chương title `Phần 1/2/3` (do LLM fail), chạy retitle để LLM đặt lại title có nghĩa cho từng chương:

```bash
# Tự động tìm + retitle mọi chapter có title 'Phần N'
python chapter_splitter.py --retitle-fallbacks --sleep 1
```

Khác với split: chỉ UPDATE field `title` (không đụng content). Mỗi chương 1 LLM call ngắn (~50 token output), rẻ.

### Fallback paragraph cho content dính liền

Nếu content gốc không có `\n\n` paragraph break (1 block dài), `_split_paragraphs` thử 4 cấp:
1. `content.split("\n\n")` — chuẩn
2. `content.split("\n")` — xuống dòng đơn
3. `rewriter.split_paragraphs()` — regex chèn break tại đối thoại đóng + chữ hoa
4. Split theo câu (`.!?`) gộp ~5 câu/đoạn — last resort

Cấp 3-4 chỉ kích hoạt khi content > `MIN_WORDS_TO_SPLIT` (800 từ) và cấp trước cho < 5 paragraphs.

## ⚠️ Cấu hình LLM

`chapter_splitter.py` dùng `REWRITE_PROVIDER` (KHÔNG phải `WRAP_PROVIDER`) — vì split + retitle là task mechanical, dùng Gemini cho rẻ. Chỉ chấp nhận:
- `REWRITE_PROVIDER = "gemini"` + `GEMINI_API_KEY`
- `REWRITE_PROVIDER = "anthropic"` + `ANTHROPIC_API_KEY`
- Còn lại fallthrough về Ollama (`OLLAMA_BASE_URL`)

⚠️ **`"deepseek" | "groq" | "huggingface"` không hoạt động** — tự động fallback Ollama. Nếu Ollama local không chạy hoặc model không trả JSON đúng (gemma3 hay fail), splitter sẽ chia đều với title generic.

**Khuyến nghị**: dùng `gemini` (rẻ, ~$0.0006/chương) trước khi chạy `--all-thin`:

```bash
# crawler/.env
GEMINI_API_KEY=AIza...
```
```python
# crawler/config.py
REWRITE_PROVIDER = "gemini"
```

## Rủi ro & dữ liệu mất

DELETE + INSERT chapters mới đồng nghĩa:

| Field | Hành vi |
|-------|---------|
| `Chapter.viewCount` | Reset về 0 |
| `Chapter.audioUrl`, `audioDuration` | Mất reference (file S3 vẫn còn) |
| `Chapter.summary`, `highlight`, `nextPreview` | Mất — phải re-wrap §1 sau khi split |
| `Bookmark`, `Comment`, `Rating` | KHÔNG ảnh hưởng (đều ở Novel level, không trỏ Chapter) |
| `ReadingProgress.chapterNumber` | Vẫn pointer hợp lệ nhưng nội dung khác |

Audio: nếu có 14/449 chương (3% trong test data) đã upload audio, các chương split sẽ mất link — script log warning rõ ràng.

## Workflow đầy đủ sau split

```bash
# 1. Audit hiện trạng
python audit_indexable.py     # in 130 thin novels

# 2. Preview với 1 truyện trước
python chapter_splitter.py --slug "ly-hon" --target 10 --dry-run

# 3. Apply tất cả (có backup tự động)
python chapter_splitter.py --all-thin --target 10

# 4. Fix các chapter có title fallback "Phần N" (do LLM fail giữa chừng)
python chapter_splitter.py --retitle-fallbacks --sleep 1

# 5. Audit lại — số "Thin novels" phải gần 0
python audit_indexable.py

# 6. Wrap §1 cho chương mới (chương split chưa có summary/highlight/nextPreview)
python run.py --wrap-all

# 7. Đẩy lên pi4
python run.py --sync-wrappers
```

## Hoàn tác

Có 2 lớp backup:

```bash
# Lớp 1: file backup auto-tạo trước split
ls ../prisma/dev.db.split-bak.*

# Restore
cp ../prisma/dev.db.split-bak.<timestamp> ../prisma/dev.db
```

```bash
# Lớp 2: snapshot pi4 (nếu sync_from_pi4.sh đã chạy)
ls ../prisma/dev.db.prev
cp ../prisma/dev.db.prev ../prisma/dev.db
```

## Chi phí ước tính

| Item | Số lượng | Token | Cost (Gemini Flash) | Cost (Haiku 4.5) |
|------|----------|-------|---------------------|------------------|
| 1 chương 4000 từ | 1 LLM call | ~6K input + 50 output | $0.0006 | $0.005 |
| 130 thin novels × ~3.5 chương | 455 LLM call | ~3M token | **~$0.30** | **~$2.5** |

Sau split, wrap §1 cho ~1300 chương mới (130 × 10) sẽ tốn:
- Gemini: ~$0.50
- Haiku: ~$4

Tổng AdSense recovery cho 130 thin novels: **$0.80 (Gemini)** hoặc **$6.5 (Haiku)**.

## Tham khảo

- [audit.md](audit.md) — phát hiện thin novels
- [chapter_wrapper.md](chapter_wrapper.md) — wrap §1 sau khi split
- [adsense_recovery.md](adsense_recovery.md) — playbook tổng
- [chapter_splitter.py](../chapter_splitter.py) — source
