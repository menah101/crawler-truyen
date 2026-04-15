"""
seo_analyzer.py — Phân tích truyện và tạo thông tin SEO cho YouTube.

Đầu vào: tên truyện, tác giả, thể loại, nội dung vài chương đầu.
Đầu ra: file seo.txt lưu trong thư mục của truyện, bao gồm:
  - Tiêu đề YouTube (hook cảm xúc + kênh, DƯỚI 80 ký tự, KHÔNG có tên truyện)
  - Mô tả YouTube (keyword-rich, chuẩn SEO)
  - Tags / từ khoá (~500 ký tự)
  - Tóm tắt ngắn (pinned comment)
"""

import os
import logging

logger = logging.getLogger(__name__)

# Số ký tự lấy từ nội dung truyện để AI phân tích
_SAMPLE_CHARS = 3000

SEO_PROMPT_TEMPLATE = """Bạn là chuyên gia SEO YouTube hàng đầu cho kênh truyện audio tiếng Việt.
Bạn hiểu sâu thuật toán YouTube: CTR (click-through rate), watch time, keyword density, và cách rank video lên top search.

THÔNG TIN TRUYỆN:
- Tên truyện : {title}
- Tác giả    : {author}
- Thể loại   : {genres}
- Trích đoạn :
---
{sample}
---

== QUY TẮC NGÔN NGỮ — BẮT BUỘC ==
- Tất cả nội dung (tiêu đề, mô tả, tags, tóm tắt) phải viết bằng TIẾNG VIỆT CÓ DẤU.
- TUYỆT ĐỐI KHÔNG dùng tiếng Trung, tiếng Anh, hay bất kỳ ngôn ngữ nào khác.
- Nếu trích đoạn có chứa tiếng nước ngoài, hãy DỊCH SANG TIẾNG VIỆT trước khi dùng.

== QUY TẮC TUYỆT ĐỐI — TRÁNH TỪ NHẠY CẢM ==
Tất cả nội dung (tiêu đề, mô tả, tags) TUYỆT ĐỐI KHÔNG chứa các từ/cụm từ sau vì YouTube sẽ hạn chế hiển thị hoặc đánh dấu vi phạm chính sách:

TỪ GÂY DEMONETIZE/GIỚI HẠN:
- Từ nội dung bạo lực: giết, chết, máu, tàn sát, hành hạ, tra tấn, tự tử, tự sát
- Từ nội dung 18+: cảnh nóng, gợi cảm, khiêu gợi, nước đôi, tình dục, giấc ngủ, lộ hàng
- Từ chính trị/tôn giáo nhạy cảm bất kỳ
- Từ dân tộc/phân biệt đối xử

THAY THẾ BẰNG:
- "chết" → "ra đi", "từ trần", "không còn nữa", "lìa xa"
- "giết" → "hại", "loại bỏ", "tránh khỏi", "xử lý"
- "đau khổ quá mức" → "trải lòng", "vỡ lòng", "tan nát con tim"
- "cảnh nóng" → "cảm xúc sâu sắc", "khoảnh khắc đặc biệt", "chuyện động lòng"
- Tất cả hook cảm xúc phải thể hiện qua hành động/tình huống, không dùng từ trực tiếp

HÃY TẠO NỘI DUNG SEO CHUẨN YOUTUBE. Trả về CHÍNH XÁC theo định dạng sau:

=== TIÊU ĐỀ YOUTUBE ===
[Bạn là người viết tiêu đề YouTube chuyên nghiệp cho kênh truyện audio ngôn tình (drama, ngoại tình, trả thù, hối hận).
Nhiệm vụ: Viết tiêu đề sao cho người xem phải TÒ MÒ và MUỐN BẤM NGAY.

QUY TẮC BẮT BUỘC:
- KHÔNG viết kiểu kể lại nội dung — phải giữ "ẩn ý", không tiết lộ hết
- KHÔNG dài dòng, KHÔNG lan man — ngắn, sắc, có nhịp
- Phải tạo cảm xúc mạnh: đau, sốc, hối hận, bất ngờ
- Giống tiêu đề viral trên YouTube, KHÔNG giống văn viết
- Ưu tiên câu có 2 vế (trước — sau), dùng "..." để tạo tò mò
- KHÔNG có tên truyện trong tiêu đề — tên truyện chỉ xuất hiện trong mô tả và tags

FORMAT: Viết 7 tiêu đề, đánh số 1-7, mỗi cái trên 1 dòng.
- Mỗi tiêu đề 8-14 từ (phần HOOK, không tính phần 【Truyện Audio】 và | Hồng Trần Truyện Audio)
- Ít nhất 3 tiêu đề bắt đầu HOOK bằng: "Tôi...", "Đêm đó...", "Ngày tôi...", "Anh..."

Công thức bắt buộc cho MỖI tiêu đề:
【Truyện Audio】 [HOOK CẢM XÚC] | Hồng Trần Truyện Audio

Ví dụ CHUẨN (7 phong cách khác nhau):
1. 【Truyện Audio】 Tôi mang cơm đến... lại thấy anh ôm người khác | Hồng Trần Truyện Audio
2. 【Truyện Audio】 3 năm chờ đợi, đổi lại một tờ giấy ly hôn | Hồng Trần Truyện Audio
3. 【Truyện Audio】 Đêm đó anh quỳ trước cửa... nhưng tôi đã khóa rồi | Hồng Trần Truyện Audio
4. 【Truyện Audio】 Ngày tôi rời đi, anh mới biết mình đã mất gì | Hồng Trần Truyện Audio
5. 【Truyện Audio】 Anh lạnh lùng suốt 3 năm... giờ cầu xin cũng muộn | Hồng Trần Truyện Audio
6. 【Truyện Audio】 Kiếp trước bị phản bội, kiếp này tôi chọn mình trước | Hồng Trần Truyện Audio
7. 【Truyện Audio】 Cô ấy im lặng rời đi... cả nhà chồng mới sụp đổ | Hồng Trần Truyện Audio

Ví dụ kém (CẤM DÙNG):
- "Câu chuyện ngôn tình hay" ← quá chung chung, không có hook
- "Truyện ngôn tình hay nhất 2026" ← spam từ khoá
- "Ba năm im lặng rồi ly hôn vì chồng ngoại tình với..." ← kể lại nội dung, không giữ ẩn ý

Yêu cầu kỹ thuật:
- Luôn bắt đầu bằng "【Truyện Audio】" (ngoặc vuông, không thay đổi)
- HOOK lấy từ TÌNH HUỐNG CỤ THỂ trong truyện, tránh từ nhạy cảm YouTube
- Kết thúc: "| Hồng Trần Truyện Audio" (không đổi)
- Tổng mỗi tiêu đề: DƯỚI 100 ký tự (bao gồm tất cả)
- 7 tiêu đề phải KHÁC NHAU về góc nhìn và cảm xúc
- Chỉ liệt kê tiêu đề, KHÔNG giải thích]

=== MÔ TẢ YOUTUBE ===
[Cấu trúc chuẩn — QUAN TRỌNG: 2 dòng đầu hiện trước nút "Xem thêm" phải chứa từ khoá và cảm xúc:

DÒNG 1 (hook + từ khoá, tối đa 100 ký tự):
[TÌNH HUỐNG CHÍNH gây mò — lấy từ nội dung truyện] | Nghe [Tên truyện] audio miễn phí trên kênh {channel}.

DÒNG 2 (từ khoá SEO):
Truyện [thể loại] hay | [Tên truyện] full bộ | Cập nhật mới nhất 2026

ĐOẠN 1 — Tóm tắt có cảm xúc (3-4 câu):
[Mô tả nhân vật chính + mâu thuẫn + cảm xúc chính — dùng ngôn ngữ truyện audio Việt Nam, có từ khoá: tên truyện, thể loại, tình cảm/hành động nổi bật]

ĐOẠN 2 — Điểm hấp dẫn của truyện (2-3 câu):
[Nêu bật mối quan hệ nhân vật, bối cảnh, twist chính — đủ để người nghe tò mò nhưng KHÔNG spoil kết thúc]

ĐOẠN 3 — Lời kêu gọi hành động:
Like và Subscribe để nghe tiếp nhé bạn! Bật thông báo (🔔) để không bỏ lỡ chương mới. Comment tên truyện bạn muốn nghe tiếp theo!
👉 Đọc truyện đầy đủ tại: {novel_url}

HASHTAG (5 cái cuối mô tả):
#TruyenAudio #[ThểLoại] #[TênTruyện không dấu không khoảng trắng] #NgheVietNam #HongTranTruyen
]

=== TAGS (500 ký tự, YouTube dùng để phân loại) ===
[Sắp xếp theo thứ tự quan trọng:
1. Tên truyện đầy đủ có dấu, không dấu
2. Tên tác giả có dấu, không dấu
3. Thể loại chính có dấu, không dấu
4. Từ khoá chung: truyện audio, nghe truyện, truyện hay, truyện full bộ, truyện audio việt nam
5. Đặc điểm nổi bật: xuyên không, trọng sinh, nữ cường, HE, BE, ngược tâm, ngọt ngào...
6. Từ khoá trending: truyện [thể loại] hay nhất 2026, truyện [thể loại] mới nhất
Tất cả cách nhau dấu phẩy, không có #, tổng không quá 500 ký tự]

=== TÓM TẮT (dùng cho pinned comment) ===
[2-3 câu NGẮN, gợi mở nội dung, KHÔNG spoil kết thúc.
Viết có dấu, thân thiện, khiến người đọc muốn nghe ngay.]

=== TAGS DÀNH CHO WEBSITE ===
[Tags ngắn gọn dùng cho hệ thống phân loại/lọc của website (KHÁC với TAGS YouTube ở trên — không phải từ khoá SEO).
Quy tắc:
- 5-10 tag, CÁCH NHAU DẤU PHẨY (không có #, không có khoảng trắng thừa sau dấu phẩy)
- Viết TIẾNG VIỆT CÓ DẤU, chữ thường (trừ viết tắt như HE, BE, SE)
- Mỗi tag là 1 trope/đặc điểm/thể loại phụ CỤ THỂ — không dùng từ chung chung như "truyện hay", "audio"
- Ưu tiên: trope cốt truyện (trọng sinh, xuyên không, báo thù, ngược tâm, ngọt sủng, cung đấu, nữ cường, tổng tài...), kết truyện (HE/BE/SE), bối cảnh (hiện đại, cổ trang, cung đình), mối quan hệ (hôn nhân, thanh mai trúc mã, tổng tài - thư ký)
- KHÔNG lặp lại tên truyện, tên tác giả, tên thể loại đã có ở field riêng
Ví dụ: ngược tâm,HE,tổng tài,hôn nhân,báo thù,ngọt sủng,nữ cường]

CHỈ trả về 5 phần trên (TIÊU ĐỀ, MÔ TẢ, TAGS, TÓM TẮT, TAGS DÀNH CHO WEBSITE), không có giải thích hay chú thích thêm."""


try:
    from config import GEMINI_FALLBACK_MODELS as _GEMINI_MODELS
except ImportError:
    _GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]


def _call_gemini_with_fallback(prompt: str, api_key: str, preferred: str) -> str | None:
    """Thu tat ca Gemini model theo thu tu, tu dong fallback khi 429."""
    import requests, time
    models = [preferred] + [m for m in _GEMINI_MODELS if m != preferred]
    for model in models:
        for attempt in range(2):
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}},
                    timeout=90,
                )
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)  # 10s lần 1, 20s lần 2
                    logger.warning(f"  Gemini {model}: rate limit (429), thử lại sau {wait}s...")
                    time.sleep(wait)
                    continue
                logger.warning(f"  Gemini {model}: HTTP {resp.status_code}")
                break
            except Exception as e:
                logger.warning(f"  Gemini {model}: {e}")
                break
    return None


def _call_ai(prompt: str) -> str | None:
    """Goi AI provider hien tai de sinh noi dung SEO.
    Fallback: Gemini (tat ca model) → Anthropic → Groq → Ollama.
    """
    from config import (
        REWRITE_PROVIDER,
        GEMINI_API_KEY, GEMINI_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
        DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
        GROQ_API_KEY, GROQ_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
    )
    import requests

    provider = REWRITE_PROVIDER.lower()

    try:
        if provider == 'gemini' and GEMINI_API_KEY:
            result = _call_gemini_with_fallback(prompt, GEMINI_API_KEY, GEMINI_MODEL)
            if result:
                return result
            # Gemini het quota hoan toan — fallback sang Anthropic neu co
            if ANTHROPIC_API_KEY:
                logger.warning("  Gemini het quota, thu Anthropic...")
                provider = 'anthropic'
            elif GROQ_API_KEY:
                logger.warning("  Gemini het quota, thu Groq...")
                provider = 'groq'
            else:
                return None

        if provider == 'anthropic' and ANTHROPIC_API_KEY:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": ANTHROPIC_MODEL, "max_tokens": 2048,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()

        if provider == 'deepseek' and DEEPSEEK_API_KEY:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL, "max_tokens": 2048, "temperature": 0.7,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()

        if provider == 'groq' and GROQ_API_KEY:
            from config import GROQ_FALLBACK_MODELS
            for model in [GROQ_MODEL] + GROQ_FALLBACK_MODELS:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 2048, "temperature": 0.7,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=60,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
                if resp.status_code != 429:
                    break

        if provider == 'ollama':
            resp = requests.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={"model": OLLAMA_MODEL, "max_tokens": 2048, "temperature": 0.7,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()

        if provider == 'huggingface':
            from config import HF_API_TOKEN, HF_REWRITE_MODEL, HF_REWRITE_FALLBACK_MODELS
            if HF_API_TOKEN:
                models = [HF_REWRITE_MODEL] + [m for m in HF_REWRITE_FALLBACK_MODELS if m != HF_REWRITE_MODEL]
                for model in models:
                    resp = requests.post(
                        "https://router.huggingface.co/together/v1/chat/completions",
                        headers={"Authorization": f"Bearer {HF_API_TOKEN}",
                                 "Content-Type": "application/json"},
                        json={"model": model, "max_tokens": 2048, "temperature": 0.7,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        return resp.json()["choices"][0]["message"]["content"].strip()
                    if resp.status_code != 429 and resp.status_code != 503:
                        break

    except Exception as e:
        logger.error(f"SEO AI error: {e}")

    return None


def analyze_novel_seo(
    title: str,
    author: str,
    genres: str,
    chapters: list,      # [{'content': str, ...}]
    output_dir: str,     # thư mục của truyện (đã có slug subfolder)
    channel_name: str = '',
    novel_url: str = '',
) -> str | None:
    """
    Phan tich truyen, tao SEO info va luu vao output_dir/seo.txt.

    Returns:
        Duong dan file seo.txt, hoac None neu loi.
    """
    # Lay mau noi dung tu vai chuong dau
    sample_parts = []
    total = 0
    for ch in chapters[:5]:
        content = ch.get('content', '').strip()
        if not content:
            continue
        remaining = _SAMPLE_CHARS - total
        if remaining <= 0:
            break
        chunk = content[:remaining]
        sample_parts.append(chunk)
        total += len(chunk)

    sample = '\n\n'.join(sample_parts)
    if not sample:
        logger.warning("Không có nội dung để phân tích SEO.")
        return None

    prompt = SEO_PROMPT_TEMPLATE.format(
        title=title,
        author=author,
        genres=genres or 'chua xac dinh',
        sample=sample,
        channel=channel_name or 'kenh cua ban',
        novel_url=novel_url or 'https://hongtrantruyen.net',
    )

    logger.info("  Dang phan tich SEO...")
    result = _call_ai(prompt)

    if not result:
        logger.warning("  AI không trả về kết quả SEO.")
        return None

    # ── Post-processing ────────────────────────────────────────────
    import re as _re

    # 0. Xoá ký tự Trung/Nhật/Hàn (giữ lại phần tiếng Việt trong dòng)
    _CJK_RE = _re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+')
    if _CJK_RE.search(result):
        result = _CJK_RE.sub('', result)
        # Don dep khoang trang thua sau khi xoa CJK
        result = _re.sub(r'  +', ' ', result)
        result = _re.sub(r'^ +| +$', '', result, flags=_re.MULTILINE)
        # Xoa dong trong thua
        result = _re.sub(r'\n{3,}', '\n\n', result)
        logger.info("  🈲 SEO: đã xoá ký tự Trung/Nhật/Hàn")

    # 1. Xoa phan THUMBNAIL neu AI van sinh ra (safety net)
    result = _re.sub(
        r'={3}\s*THUMBNAIL\s*={3}.*?(?=={3}|\Z)',
        '', result, flags=_re.DOTALL | _re.IGNORECASE,
    ).strip()
    result = _re.sub(
        r'##\s*THUMBNAIL\b.*?(?=##|\Z)',
        '', result, flags=_re.DOTALL | _re.IGNORECASE,
    ).strip()

    # 2. Đảm bảo tiêu đề không có tên truyện và dưới 100 ký tự (YouTube limit)
    #    Xoá phần "| TÊN_TRUYỆN" nếu có 2+ dấu "|" trong tiêu đề
    _TITLE_MAX = 100
    _SUFFIX = ' | Hồng Trần Truyện Audio'
    _PREFIX = '【Truyện Audio】'
    _MAX_HOOK = _TITLE_MAX - len(_PREFIX) - len(_SUFFIX)  # ~60 ký tự cho hook

    def _fix_title_line(text: str) -> str:
        """Fix 1 dòng tiêu đề (có hoặc không có prefix '# ' hoặc '1. ')."""
        # Trim prefix đánh số: "1. ", "2. ", "# " ...
        stripped = text
        prefix_part = ''
        if _re.match(r'^\d+\.\s+', stripped):
            m = _re.match(r'^(\d+\.\s+)', stripped)
            prefix_part = m.group(1)
            stripped = stripped[len(prefix_part):]
        elif stripped.startswith('# '):
            prefix_part = '# '
            stripped = stripped[2:]

        if _PREFIX not in stripped:
            return text

        parts = [p.strip() for p in stripped.split('|')]
        # Giữ phần đầu (hook) và phần cuối (Hồng Trần Truyện Audio)
        if len(parts) >= 3:
            stripped = parts[0] + _SUFFIX
        # Cắt ngắn nếu quá 100 ký tự — cắt tại khoảng trắng, không cắt giữa từ
        if len(stripped) > _TITLE_MAX:
            hook_end = stripped.rfind(_SUFFIX)
            if hook_end > 0:
                hook = stripped[:hook_end].rstrip('. ')
                if len(hook) > _MAX_HOOK:
                    # Tìm khoảng trắng gần nhất trước _MAX_HOOK
                    cut = hook[:_MAX_HOOK].rfind(' ')
                    if cut > len(_PREFIX):
                        hook = hook[:cut].rstrip('.,;:!? ')
                    else:
                        hook = hook[:_MAX_HOOK].rstrip()
                    hook += '...'
                stripped = hook + _SUFFIX
        return prefix_part + stripped

    lines = result.split('\n')
    lines = [_fix_title_line(l) if '【Truyện Audio】' in l else l for l in lines]
    result = '\n'.join(lines)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, 'seo.txt')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"{'=' * 60}\n")
        f.write(f"  {title}\n")
        f.write(f"  Tác giả : {author}  |  Thể loại: {genres}\n")
        if channel_name:
            f.write(f"  Kênh    : {channel_name}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(result)
        f.write("\n")

    logger.info(f"  Đã lưu SEO: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────
# Shorts SEO — TikTok + YouTube Shorts
# ─────────────────────────────────────────────────────────────────

SHORTS_SEO_PROMPT = """Bạn là chuyên gia marketing nội dung cho TikTok và YouTube Shorts, chuyên trang truyện audio Việt Nam.

== QUY TẮC NGÔN NGỮ — BẮT BUỘC ==
- Tất cả nội dung phải viết bằng TIẾNG VIỆT CÓ DẤU.
- TUYỆT ĐỐI KHÔNG dùng tiếng Trung, tiếng Anh, hay bất kỳ ngôn ngữ nào khác trong caption, title, description.
- Nếu hook story có chứa tiếng Trung/tiếng nước ngoài, hãy DỊCH SANG TIẾNG VIỆT trước khi dùng.
- Tên nhân vật giữ nguyên (phiên âm Việt), không viết bằng chữ Hán.

Dưới đây là hook story (script đọc) của video Shorts:
---
{hook_story}
---

Tên truyện: {title}
Thể loại: {genres}
Kênh: {channel}

Nhiệm vụ: Tạo SEO caption và hashtag tối ưu cho TIKTOK và YOUTUBE SHORTS. VIẾT TOÀN BỘ BẰNG TIẾNG VIỆT CÓ DẤU.

=== TIKTOK CAPTION ===
[Cấu trúc: 3 phần, tổng tối đa 2200 ký tự]

DÒNG ĐẦU (150 ký tự đầu — hiển thị trước nút "Xem thêm", QUAN TRỌNG NHẤT):
[Câu hook cực mạnh — lấy thẳng từ tình huống gây tò mò nhất trong truyện, kết thúc bằng ... hoặc ? để người ta phải bấm "Xem thêm"]
[Ví dụ: "Anh chuyển 1.5 triệu cho người khác, nhưng lại bảo vợ "anh hết tiền rồi"... Em lạnh lùng mở file ngân hàng ra xem 👇"]

NỘI DUNG (phần mở rộng sau "Xem thêm"):
[2-3 câu tóm tắt hook story — gây cảm xúc, tạo mò — KHÔNG spoil kết thúc]
[Kết thúc bằng: "Nghe toàn bộ tại {channel} 🎧"]

HASHTAG TIKTOK (10-15 cái, xen kẽ phổ biến và niche):
[Chứa hashtag phổ biến: #truyenaudio #ngontinh #truyenhay]
[Hashtag niche: #truyengaycam #truyencuoituan #audiotruyen]
[Hashtag trending nếu phù hợp: #xuhuong #fyp #foryou]

=== YOUTUBE SHORTS TITLE ===
[Tiêu đề ngắn, mạnh, tối đa 100 ký tự]
[Format: [HOOK NÉ CƯỠNG] | Tên truyện | {channel}]
[Ví dụ: "Anh chuyển hết tiền cho bạn gái cũ rồi nói "anh hết tiền" | Hạnh Phúc Do Tôi Tự Tạo | {channel}"]

=== YOUTUBE SHORTS DESCRIPTION ===
[2-3 dòng ngắn]
[Dòng 1: Hook + tên truyện]
[Dòng 2: "Nghe full tại: " + URL nếu có]
[Dòng 3: 3-5 hashtag: #Shorts #TruyenAudio #NgonTinh]

CHỈ trả về 3 phần trên theo đúng format. Không giải thích thêm."""


def analyze_shorts_seo(
    title: str,
    genres: str,
    hook_story: str,
    shorts_dir: str,
    channel_name: str = '',
    novel_url: str = '',
) -> str | None:
    """
    Tao SEO caption + hashtag cho TikTok va YouTube Shorts tu hook_story.

    Returns:
        Duong dan file seo_shorts.txt, hoac None neu loi.
    """
    if not hook_story.strip():
        logger.warning("Hook story trống — bỏ qua Shorts SEO.")
        return None

    prompt = SHORTS_SEO_PROMPT.format(
        hook_story=hook_story[:2000],   # gioi han token
        title=title,
        genres=genres or 'ngôn tình',
        channel=channel_name or 'Hồng Trần Truyện Audio',
        url=novel_url or 'https://hongtrantruyen.net',
    )

    logger.info("  Đang tạo Shorts SEO (TikTok + YouTube Shorts)...")
    result = _call_ai(prompt)

    if not result:
        logger.warning("  AI không trả về kết quả Shorts SEO.")
        return None

    # Post-processing
    import re as _re2

    # 1. Xoá ký tự Trung/Nhật/Hàn (giữ phần tiếng Việt)
    _CJK_RE = _re2.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+')
    if _CJK_RE.search(result):
        result = _CJK_RE.sub('', result)
        result = _re2.sub(r'  +', ' ', result)
        result = _re2.sub(r'^ +| +$', '', result, flags=_re2.MULTILINE)
        result = _re2.sub(r'\n{3,}', '\n\n', result)
        logger.info("  🈲 Shorts SEO: đã xoá ký tự Trung/Nhật/Hàn")

    # 2. Fix Shorts title — xoá tên truyện thừa, giới hạn 100 ký tự
    _SHORTS_SUFFIX = ' | Hồng Trần Truyện Audio'
    def _fix_shorts_title(line: str) -> str:
        # Tìm phần trong ngoặc kép hoặc ngoặc vuông
        m = _re2.search(r'["\[](.*?)["\]]', line)
        if not m:
            return line
        raw = m.group(1).strip()
        parts = [p.strip() for p in raw.split('|')]
        if len(parts) >= 3:
            # Giữ hook (phần đầu) + suffix (phần cuối), xoá tên truyện (giữa)
            raw = parts[0] + ' | ' + parts[-1]
        elif len(parts) == 2 and 'Hồng Trần' not in parts[-1]:
            # hook | tên truyện — thêm suffix
            raw = parts[0] + _SHORTS_SUFFIX
        elif len(parts) == 1:
            raw = parts[0] + _SHORTS_SUFFIX
        # Giới hạn 100 ký tự
        if len(raw) > 100:
            suffix_pos = raw.rfind(_SHORTS_SUFFIX)
            if suffix_pos > 0:
                hook = raw[:suffix_pos].rstrip('. ')
                max_hook = 100 - len(_SHORTS_SUFFIX)
                if len(hook) > max_hook:
                    cut = hook[:max_hook].rfind(' ')
                    if cut > 10:
                        hook = hook[:cut].rstrip('.,;:!? ') + '...'
                    else:
                        hook = hook[:max_hook].rstrip() + '...'
                raw = hook + _SHORTS_SUFFIX
        return raw
    lines = result.split('\n')
    in_shorts_title = False
    for i, line in enumerate(lines):
        if 'YOUTUBE SHORTS TITLE' in line.upper():
            in_shorts_title = True
            continue
        if in_shorts_title and line.strip():
            lines[i] = _fix_shorts_title(line)
            in_shorts_title = False
    result = '\n'.join(lines)

    os.makedirs(shorts_dir, exist_ok=True)
    out_path = os.path.join(shorts_dir, 'seo_shorts.txt')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"{'=' * 60}\n")
        f.write(f"  SHORTS SEO — {title}\n")
        if novel_url:
            f.write(f"  URL: {novel_url}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(result)
        f.write("\n")

    logger.info(f"  Đã lưu Shorts SEO: {out_path}")
    return out_path
