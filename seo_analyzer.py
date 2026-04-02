"""
seo_analyzer.py — Phan tich truyen va tao thong tin SEO cho YouTube.

Dau vao: ten truyen, tac gia, the loai, noi dung vai chuong dau.
Dau ra: file seo.txt luu trong thu muc cua truyen, bao gom:
  - Tieu de YouTube (hook cam xuc + kenh, DUOI 80 ky tu, KHONG co ten truyen)
  - Mo ta YouTube (keyword-rich, chuan SEO)
  - Tags / tu khoa (~500 ky tu)
  - Tom tat ngan (pinned comment)
"""

import os
import logging

logger = logging.getLogger(__name__)

# So ky tu lay tu noi dung truyen de AI phan tich
_SAMPLE_CHARS = 3000

SEO_PROMPT_TEMPLATE = """Ban la chuyen gia SEO YouTube hang dau cho kenh truyen audio tieng Viet.
Ban hieu sau thuat toan YouTube: CTR (click-through rate), watch time, keyword density, va cach rank video len top search.

THONG TIN TRUYEN:
- Ten truyen : {title}
- Tac gia    : {author}
- The loai   : {genres}
- Trich doan :
---
{sample}
---

== QUY TAC TUYET DOI — TRANH TU NHAY CAM ==
Tat ca noi dung (tieu de, mo ta, tags) TUYET DOI KHONG chua cac tu/cum tu sau vi YouTube se han che hien thi hoac danh dau vi pham chinh sach:

TU GAY DEMON/GIOI HAN:
- Liet ke tu noi dung bao luc: giet, chet, mau, tan sat, hanh ha, tra tan, tu tu, tu sat
- Tu noi dung 18+: canh nong, goi cam, khieu goi, nuoc doi, tinh duc, giac ngu, lo hang
- Tu chinh tri/ton giao nhay cam bat ky
- Tu dan toc/phan biet doi xu

THAY THE BANG:
- "chet" → "ra di", "tu tran", "khong con nua", "la xa"
- "giet" → "hai", "loai bo", "tranh khoi", "xu ly"
- "dau kho qua muc" → "trai long", "vo long", "tan nat con tim"
- "canh nong" → "cam xuc sau sac", "moment dac biet", "chuyen dong long"
- Tat ca hook cam xuc phai the hien qua hanh dong/tinh huong, khong dung tu truc tiep

HAY TAO NOI DUNG SEO CHUAN YOUTUBE. Tra ve CHINH XAC theo dinh dang sau:

=== TIEU DE YOUTUBE ===
[Ban la nguoi viet tieu de YouTube chuyen nghiep cho kenh truyen audio ngon tinh (drama, ngoai tinh, tra thu, hoi han).
Nhiem vu: Viet tieu de sao cho nguoi xem phai TO MO va MUON BAM NGAY.

QUY TAC BAT BUOC:
- KHONG viet kieu ke lai noi dung — phai giu "an y", khong tiet lo het
- KHONG dai dong, KHONG lan man — ngan, sac, co nhip
- Phai tao cam xuc manh: dau, soc, hoi han, bat ngo
- Giong tieu de viral tren YouTube, KHONG giong van viet
- Uu tien cau co 2 ve (truoc — sau), dung "..." de tao to mo
- KHONG co ten truyen trong tieu de — ten truyen chi xuat hien trong mo ta va tags

FORMAT: Viet 7 tieu de, danh so 1-7, moi cai tren 1 dong.
- Moi tieu de 8-14 tu (phan HOOK, khong tinh phan 【Truyện Audio】 va | Hồng Trần Truyện Audio)
- It nhat 3 tieu de bat dau HOOK bang: "Tôi...", "Đêm đó...", "Ngày tôi...", "Anh..."

Cong thuc bat buoc cho MOI tieu de:
【Truyện Audio】 [HOOK CAM XUC] | Hồng Trần Truyện Audio

Vi du CHUAN (7 phong cach khac nhau):
1. 【Truyện Audio】 Tôi mang cơm đến... lại thấy anh ôm người khác | Hồng Trần Truyện Audio
2. 【Truyện Audio】 3 năm chờ đợi, đổi lại một tờ giấy ly hôn | Hồng Trần Truyện Audio
3. 【Truyện Audio】 Đêm đó anh quỳ trước cửa... nhưng tôi đã khóa rồi | Hồng Trần Truyện Audio
4. 【Truyện Audio】 Ngày tôi rời đi, anh mới biết mình đã mất gì | Hồng Trần Truyện Audio
5. 【Truyện Audio】 Anh lạnh lùng suốt 3 năm... giờ cầu xin cũng muộn | Hồng Trần Truyện Audio
6. 【Truyện Audio】 Kiếp trước bị phản bội, kiếp này tôi chọn mình trước | Hồng Trần Truyện Audio
7. 【Truyện Audio】 Cô ấy im lặng rời đi... cả nhà chồng mới sụp đổ | Hồng Trần Truyện Audio

Vi du kem (CAM DUNG):
- "Câu chuyện ngôn tình hay" ← qua chung chung, khong co hook
- "Truyện ngôn tình hay nhất 2026" ← spam tu khoa
- "Ba năm im lặng rồi ly hôn vì chồng ngoại tình với..." ← ke lai noi dung, khong giu an y

Yeu cau ky thuat:
- Luon bat dau bang "【Truyện Audio】" (ngoac vuong, khong thay doi)
- HOOK lay tu TINH HUONG CU THE trong truyen, tranh tu nhay cam YouTube
- Ket thuc: "| Hồng Trần Truyện Audio" (khong doi)
- Tong moi tieu de: DUOI 80 ky tu (bao gom tat ca)
- 7 tieu de phai KHAC NHAU ve goc nhin va cam xuc
- Chi liet ke tieu de, KHONG giai thich]

=== MO TA YOUTUBE ===
[Cau truc chuan — QUAN TRONG: 2 dong dau hien truoc nut "Xem them" phai chua tu khoa va cam xuc:

DONG 1 (hook + tu khoa, toi da 100 ky tu):
[TINH HUONG CHINH gay mo — lay tu noi dung truyen] | Nghe [Ten truyen] audio mien phi tren kenh {channel}.

DONG 2 (tu khoa SEO):
Truyen [the loai] hay | [Ten truyen] full bo | Cap nhat moi nhat 2026

DOAN 1 — Tom tat co cam xuc (3-4 cau):
[Mo ta nhan vat chinh + mau thuan + cam xuc chinh — dung ngon ngu truyen audio Viet Nam, co tu khoa: ten truyen, the loai, tinh cam/hanh dong noi bat]

DOAN 2 — Diem hap dan cua truyen (2-3 cau):
[Neu bat moi quan he nhan vat, boi canh, twist chinh — du de nguoi nghe tay mo nhung KHONG spoil ket thuc]

DOAN 3 — Call to action:
Like va Subscribe de nghe tiep nha ban! Bat thong bao (🔔) de khong bo lo chuong moi. Comment ten truyen ban muon nghe tiep theo!
👉 Doc truyen day du tai: {novel_url}

HASHTAG (5 cai cuoi mo ta):
#TruyenAudio #[TheLoai] #[TenTruyen khong dau khong khoang trang] #NgheVietNam #HongTranTruyen
]

=== TAGS (500 ky tu, YouTube dung de phan loai) ===
[Sap xep theo thu tu quan trong:
1. Ten truyen day du co dau, khong dau
2. Ten tac gia co dau, khong dau
3. The loai chinh co dau, khong dau
4. Tu khoa chung: truyện audio, nghe truyện, truyện hay, truyện full bộ, truyện audio việt nam
5. Dac diem noi bat: xuyen khong, trong sinh, nu cuong, HE, BE, nguoc tam, ngot ngao...
6. Tu khoa trending: truyen [the loai] hay nhat 2026, truyen [the loai] moi nhat
Tat ca cach nhau dau phay, khong co #, tong khong qua 500 ky tu]

=== TOM TAT (dung cho pinned comment) ===
[2-3 cau NGAN, goi mo noi dung, KHONG spoil ket thuc.
Viet co dau, than thien, khien nguoi doc muon nghe ngay.]

CHI tra ve 4 phan tren (TIEU DE, MO TA, TAGS, TOM TAT), khong co giai thich hay chu thich them."""


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
    output_dir: str,     # thu muc cua truyen (da co slug subfolder)
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
        logger.warning("Khong co noi dung de phan tich SEO.")
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
        logger.warning("  AI khong tra ve ket qua SEO.")
        return None

    # ── Post-processing ────────────────────────────────────────────
    import re as _re

    # 1. Xoa phan THUMBNAIL neu AI van sinh ra (safety net)
    result = _re.sub(
        r'={3}\s*THUMBNAIL\s*={3}.*?(?=={3}|\Z)',
        '', result, flags=_re.DOTALL | _re.IGNORECASE,
    ).strip()
    result = _re.sub(
        r'##\s*THUMBNAIL\b.*?(?=##|\Z)',
        '', result, flags=_re.DOTALL | _re.IGNORECASE,
    ).strip()

    # 2. Dam bao tieu de khong co ten truyen va duoi 80 ky tu
    #    Xoa phan "| TEN_TRUYEN" neu co 2+ dau "|" trong tieu de
    _SUFFIX = ' | Hồng Trần Truyện Audio'
    _MAX_HOOK = 80 - len('【Truyện Audio】') - len(_SUFFIX)

    def _fix_title_line(text: str) -> str:
        """Fix 1 dong tieu de (co hoac khong co prefix '# ' hoac '1. ')."""
        # Trim prefix danh so: "1. ", "2. ", "# " ...
        stripped = text
        prefix_part = ''
        if _re.match(r'^\d+\.\s+', stripped):
            m = _re.match(r'^(\d+\.\s+)', stripped)
            prefix_part = m.group(1)
            stripped = stripped[len(prefix_part):]
        elif stripped.startswith('# '):
            prefix_part = '# '
            stripped = stripped[2:]

        if '【Truyện Audio】' not in stripped:
            return text

        parts = [p.strip() for p in stripped.split('|')]
        # Giu phan dau (hook) va phan cuoi (Hồng Trần Truyện Audio)
        if len(parts) >= 3:
            stripped = parts[0] + _SUFFIX
        # Cat ngan neu qua 80 ky tu
        if len(stripped) > 80:
            hook_end = stripped.rfind(_SUFFIX)
            if hook_end > 0:
                hook = stripped[:hook_end].rstrip('. ')
                hook = hook[:_MAX_HOOK].rstrip()
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
        f.write(f"  Tac gia : {author}  |  The loai: {genres}\n")
        if channel_name:
            f.write(f"  Kenh    : {channel_name}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(result)
        f.write("\n")

    logger.info(f"  Da luu SEO: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────
# Shorts SEO — TikTok + YouTube Shorts
# ─────────────────────────────────────────────────────────────────

SHORTS_SEO_PROMPT = """Ban la chuyen gia marketing noi dung cho TikTok va YouTube Shorts, chuyen trang truyen audio Viet Nam.

Duoi day la hook story (script doc) cua video Shorts:
---
{hook_story}
---

Ten truyen: {title}
The loai: {genres}
Kenh: {channel}

Nhiem vu: Tao SEO caption va hashtag toi uu cho TIKTOK va YOUTUBE SHORTS.

=== TIKTOK CAPTION ===
[Cau truc: 3 phan, tong toi da 2200 ky tu]

DONG DAU (150 ky tu dau — hien thi truoc nut "Xem them", QUAN TRONG NHAT):
[Cau hook cuc manh — lay thang tu tinh huong gay to mo nhat trong truyen, ket thuc bang ... hoac ? de nguoi ta phai bam "Xem them"]
[Vi du: "Anh chuyen 1.5 trieu cho nguoi khac, nhung lai bao vo "anh het tien roi"... Em lanh lung mo file ngan hang ra xem 👇"]

NOI DUNG (phan mo rong sau "Xem them"):
[2-3 cau tom tat hook story — gay cam xuc, tao mo — KHONG spoil ket thuc]
[Ket thuc bang: "Nghe toan bo tai {channel} 🎧"]

HASHTAG TIKTOK (10-15 cai, xen ke pho bien va niche):
[Chua hashtag pho bien: #truyenaudio #ngontinh #truyenhay]
[Hashtag niche: #truyengaycam #truyencuoituan #audiotruyen]
[Hashtag trending neu phu hop: #xuhuong #fyp #foryou]

=== YOUTUBE SHORTS TITLE ===
[Tieu de ngan, manh, toi da 100 ky tu]
[Format: [HOOK NE CUONG] | Ten truyen | {channel}]
[Vi du: "Anh chuyen het tien cho ban gai cu roi noi "anh het tien" | Hanh Phuc Do Toi Tu Tao | {channel}"]

=== YOUTUBE SHORTS DESCRIPTION ===
[2-3 dong ngan]
[Dong 1: Hook + ten truyen]
[Dong 2: "Nghe full tai: " + URL neu co]
[Dong 3: 3-5 hashtag: #Shorts #TruyenAudio #NgonTinh]

CHI tra ve 3 phan tren theo dung format. Khong giai thich them."""


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
        logger.warning("Hook story trong — bo qua Shorts SEO.")
        return None

    prompt = SHORTS_SEO_PROMPT.format(
        hook_story=hook_story[:2000],   # gioi han token
        title=title,
        genres=genres or 'ngon tinh',
        channel=channel_name or 'Hong Tran Truyen Audio',
        url=novel_url or 'https://hongtrantruyen.net',
    )

    logger.info("  Dang tao Shorts SEO (TikTok + YouTube Shorts)...")
    result = _call_ai(prompt)

    if not result:
        logger.warning("  AI khong tra ve ket qua Shorts SEO.")
        return None

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

    logger.info(f"  Da luu Shorts SEO: {out_path}")
    return out_path
