# Chapter Merger — Gộp chương ngắn vào chương kế trước/sau

Module: `chapter_merger.py`

Đối ngược với `chapter_splitter.py`: ghép chương quá ngắn (< MIN_WORDS, mặc định 300) vào chương liền kề để qua ngưỡng audit AdSense (`audit_indexable.py` nhóm #5 — Chapter < 300 từ).

## Khi nào dùng

`audit_indexable.py` báo "Chapter ngắn (< 300 từ): N" → 3 lựa chọn:
1. **Merge** với chương kế trước/sau (module này) — giữ 100% content
2. Hide chapter (`publishStatus='pending'`) — tạo gap khó chịu
3. LLM expand — đắt + risk bịa nội dung

Module này dùng cho lựa chọn 1.

## Dùng

### Auto mode (khuyên dùng)

Scan toàn DB, gộp mọi chương ngắn:

```bash
cd crawler

# Dry-run xem sẽ merge những gì
python chapter_merger.py --auto-merge-short --dry-run

# Apply
python chapter_merger.py --auto-merge-short

# Đặt ngưỡng riêng
python chapter_merger.py --auto-merge-short --min-words 400

# Test 5 truyện đầu trước
python chapter_merger.py --auto-merge-short --max-novels 5
```

### Manual mode

```bash
# Merge ch.5 vào ch.4 (gộp content ch.5 vào ch.4, xoá ch.5)
python chapter_merger.py --slug "ten-truyen" --merge-into-prev 5

# Merge ch.1 vào ch.2 (dùng khi chương 1 quá ngắn)
python chapter_merger.py --slug "ten-truyen" --merge-into-next 1
```

### Options

| Flag | Default | Ý nghĩa |
|------|---------|---------|
| `--merge-into-prev N` | — | Gộp ch.N vào ch.N-1, cần `--slug` |
| `--merge-into-next N` | — | Gộp ch.N vào ch.N+1, cần `--slug` |
| `--auto-merge-short` | — | Scan toàn DB, gộp mọi chương `< min-words` |
| `--slug KEYWORD` | — | Slug/title (cần với manual mode) |
| `--min-words N` | `300` | Ngưỡng chương ngắn |
| `--max-novels N` | `0` | Giới hạn số truyện khi auto |
| `--no-renumber` | — | Giữ gap số chương thay vì renumber 1..N |
| `--dry-run` | — | Preview, không ghi DB |
| `--no-backup` | — | Bỏ qua backup DB (cẩn thận) |

## Cách hoạt động

```
┌── 5 chương ──────────────┐       ┌── 4 chương sau merge ──┐
│  ch.1: 600 từ            │       │  ch.1: 600 từ          │
│  ch.2: 700 từ            │  ──▶  │  ch.2: 700 từ          │
│  ch.3: 800 từ            │       │  ch.3: 800 từ          │
│  ch.4: 500 từ            │       │  ch.4: 670 từ ←────┐   │
│  ch.5: 170 từ ← short    │       └────────────────────│───┘
└──────────────────────────┘                            │
                                          merge: ch.5 + ch.4 = 670 từ
```

### 4 bước nội bộ

1. **Backup DB** → `prisma/dev.db.merge-bak.<timestamp>` (skip với `--no-backup`)
2. **Detect chương ngắn**: `SELECT * FROM Chapter WHERE wordCount < min_words AND publishStatus='published'`
3. **Merge per pair**: 
   - Source ở TRƯỚC target (vd ch.1→ch.2): `target.content = source + "\n\n" + target`
   - Source ở SAU target (vd ch.5→ch.4): `target.content = target + "\n\n" + source`
   - UPDATE target, DELETE source, recalc wordCount
4. **Renumber**: sau khi merge xong cho 1 novel, đổi số chương 1..N để lấp gap

### Quyết định prev hay next trong auto mode

- Chương 1 quá ngắn → merge vào ch.2 (`merge-into-next`)
- Chương khác → merge vào chương trước (`merge-into-prev`)
- Multiple short trong cùng truyện → sort giảm dần, merge từ cuối lên (tránh xung đột number trong vòng lặp)

## Ưu tiên thứ tự với splitter

```bash
# 1. Split thin novels (ít chương → nhiều chương)
python chapter_splitter.py --all-thin --target 10

# 2. Splitter có thể tạo chương dưới 300 từ (hiếm, chỉ khi LLM tách lệch)
python audit_indexable.py | grep "Chapter ngắn"

# 3. Merge để fix
python chapter_merger.py --auto-merge-short

# 4. Wrap §1 cho chương mới (auto-skip chương đã wrap)
python run.py --wrap-all
```

## Rủi ro & dữ liệu mất

UPDATE target + DELETE source — ảnh hưởng:

| Field | Hành vi |
|-------|---------|
| `Chapter.content` | Của target được nối thêm content của source |
| `Chapter.wordCount` | Tự cập nhật |
| `Chapter.title` | Giữ title của target (source title bị mất) |
| `Chapter.summary`, `highlight`, `nextPreview` | Giữ của target — **không nối** từ source |
| `Chapter.audioUrl` | Source.audioUrl mất reference (file S3 vẫn còn) — log warning |
| `Chapter.viewCount` | Của target giữ nguyên — source.viewCount mất |
| `ReadingProgress.chapterNumber` | Sau renumber có thể trỏ chương khác — UI sẽ thấy progress chuyển |
| Bookmark/Comment/Rating | KHÔNG ảnh hưởng (đều ở Novel level) |

⚠️ Sau khi merge xong, **nên re-wrap §1** cho target chapter (vì content đã thay đổi):
```bash
python run.py --wrap-slug "ten-truyen" --wrap-redo
```

## Hoàn tác

Backup tự tạo trước mỗi run:

```bash
ls -t ../prisma/dev.db.merge-bak.* | head -3

# Restore
cp ../prisma/dev.db.merge-bak.<timestamp> ../prisma/dev.db
```

## Workflow đầy đủ

```bash
# 1. Audit
python audit_indexable.py

# 2. Merge chương ngắn (dry-run trước)
python chapter_merger.py --auto-merge-short --dry-run
python chapter_merger.py --auto-merge-short

# 3. Wrap lại §1 cho target chapters đã merge
# Cách 1: ép wrap toàn site (skip chương không thay đổi nhờ skip_existing)
python run.py --wrap-all --wrap-redo

# Cách 2: chỉ wrap những chương vừa merge (1 giờ qua) — tiết kiệm hơn
sqlite3 ../prisma/dev.db "
  SELECT DISTINCT n.slug FROM Chapter c JOIN Novel n ON n.id=c.novelId
  WHERE c.updatedAt > strftime('%s','now','-1 hour') * 1000
" | while read slug; do
  python run.py --wrap-slug "$slug" --wrap-redo
done

# 4. Audit lại để confirm
python audit_indexable.py | grep "Chapter ngắn"   # phải là 0

# 5. Sync pi4
python run.py --sync-wrappers
```

## Tham khảo

- [chapter_splitter.md](chapter_splitter.md) — đối ngược (split chương dài)
- [audit.md](audit.md) — phát hiện chương ngắn (nhóm #5)
- [chapter_wrapper.md](chapter_wrapper.md) — re-wrap §1 sau merge
- [chapter_merger.py](../chapter_merger.py) — source
