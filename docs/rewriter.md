# Rewriter — Viết lại truyện bằng AI

Module: `rewriter.py`

Viết lại nội dung truyện để phù hợp dạng audio, giữ nguyên nội dung gốc nhưng cải thiện câu văn, tách đoạn, và sửa lỗi.

## Provider chain

Thứ tự fallback khi provider chính thất bại:

```
Primary (REWRITE_PROVIDER) → Anthropic fallback → split_paragraphs (raw)
```

Cấu hình trong `.env`:

```env
REWRITE_PROVIDER=deepseek    # gemini | anthropic | groq | deepseek | ollama
```

## Fallback Anthropic

Khi provider chính fail (vd: Gemini bị SAFETY block), tự động fallback sang Anthropic:

```env
ANTHROPIC_API_KEY=sk-ant-...    # Cần có để fallback hoạt động
ANTHROPIC_MODEL=claude-haiku-4-5-20251001  # Mặc định
```

## Xử lý lỗi

- Provider trả về `None` → fallback Anthropic
- Anthropic cũng fail → `split_paragraphs()` (chia đoạn raw, không AI)
- `corrupted_ratio()` crash → set ratio=1.0, tiếp tục xử lý
