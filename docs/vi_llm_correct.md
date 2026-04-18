# Vietnamese LLM Correct — Sửa âm tiết tiếng Việt bị hỏng

Module: `vi_llm_correct.py`

Dùng AI để phát hiện và sửa các âm tiết tiếng Việt bị hỏng (corrupt) do quá trình crawl hoặc encode.

## Provider chain

```
Gemini (retry 2 lần) → Anthropic Haiku fallback
```

## Cách hoạt động

1. `vi_validator.py` phát hiện các âm tiết không hợp lệ theo quy tắc ngữ âm tiếng Việt
2. Gửi danh sách âm tiết hỏng + ngữ cảnh cho AI
3. AI trả về JSON mapping `{sai: đúng}`
4. Apply fixes vào text

## Cấu hình

```env
GEMINI_API_KEY=AIza...           # Provider chính
ANTHROPIC_API_KEY=sk-ant-...     # Fallback (tuỳ chọn)
```

## Chi phí ước tính (Anthropic fallback)

- Haiku: ~$0.001/chương (~1000 tokens)
- Trung bình 2-5% chương cần fallback (khi Gemini bị SAFETY block)
