import requests
import io
from PIL import Image

# HuggingFace Image API — FLUX.1-schnell
API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

# ── Kích thước chuẩn (bội số 64, tối ưu cho FLUX) ────────────────
SIZES = {
    "9:16":  (768,  1344),   # YouTube Shorts / TikTok / Reels
    "16:9":  (1344, 768),    # YouTube Thumbnail
    "1:1":   (1024, 1024),   # Square (Instagram)
    "19:6":  (1216, 384),    # Cinematic wide thumbnail (Facebook / Web banner)
}

# ── Negative concepts (viết trong prompt chính vì FLUX không có neg_prompt) ──
NEGATIVE_PREFIX = (
    "safe for work, family friendly, fully clothed characters, "
    "no nudity, no bare skin, no revealing clothing, no cleavage, no exposed body, "
    "no adult content, no sexual content, no suggestive poses, no intimate scenes, "
    "no violence, no gore, no blood, no disturbing imagery, "
    "complete image fully framed, no cropping, no cut-off body parts, "
    "perfect anatomy, correct human body, exactly two arms, two hands, "
    "no extra limbs, no missing limbs, no deformed hands, no extra fingers, "
    "no floating body parts, no merged bodies, "
    "no facial hair on female characters, no beard on woman, smooth feminine face, "
    "natural neck posture, head balanced on shoulders, no twisted neck, no broken neck, "
)

# ── Từ khoá NSFW để lọc ──────────────────────────────────────────
NSFW_KEYWORDS = [
    "nude", "nudity", "naked", "sex", "sexual", "erotic", "porn",
    "breast", "nipples", "genitals", "nsfw", "lingerie", "topless", "seductive",
    "bare skin", "exposed skin", "undressed", "revealing outfit", "cleavage",
    "sensual", "provocative", "explicit", "intimate pose", "undress",
    "shirtless", "bikini", "underwear",
]


def is_safe_prompt(prompt: str) -> bool:
    low = prompt.lower()
    return not any(w in low for w in NSFW_KEYWORDS)


# ─────────────────────────────────────────────────────────────────
# ERA VISUAL PROFILES — 3 loại truyện khác nhau hoàn toàn về
# trang phục, bối cảnh, ánh sáng, style ảnh
# ─────────────────────────────────────────────────────────────────

ERA_PROFILES = {

    # ── Cổ trang: Trung Hoa phong kiến ───────────────────────────
    "co-trang": {
        "system": (
            "You are a visual director specializing in ancient Chinese drama (古装) "
            "story videos for YouTube Shorts and TikTok. "
            "Output ONLY the English image prompt. No explanation. No quotes."
        ),
        "brand_suffix": (
            "ancient Chinese hanfu drama style, "
            "cinematic lighting with warm gold and deep shadow, "
            "rich colors with dark moody atmosphere, "
            "ultra detailed silk fabric texture, traditional hair ornaments, "
            "soft bokeh background, film grain, 8K resolution, "
            "complete scene fully framed, no cropped limbs, "
            "perfect anatomy, two arms, fully clothed hanfu, "
            "no text, no watermark, no blur"
        ),
        "genre_hints": {
            "co-trang": [
                "grand imperial court hall with jade columns and silk drapes, red lanterns",
                "moonlit stone courtyard with ancient well and willow tree",
                "mountain cliff pavilion above sea of clouds at sunset",
                "snow-covered ancient Chinese village rooftops at dusk",
                "underground dungeon with torch-lit stone corridors",
                "crowded ancient market street at dusk with lantern light",
                "wooden bridge over misty river with fireflies at night",
                "ancient battlefield with banners and smoke at dawn",
            ],
            "ngon-tinh": [
                "candlelit bedchamber with gauze curtains and rose petals",
                "moonlit lotus pond with stone bridge and weeping willows",
                "hidden courtyard garden with blooming peach blossoms",
                "riverside pavilion in spring rain, lanterns reflecting on water",
                "rooftop terrace under full moon with incense smoke",
                "scholar's study room filled with scrolls and candle glow",
                "snow garden at night with red plum blossoms",
                "ancient Chinese tea house at golden hour",
            ],
            "cung-dinh": [
                "imperial throne room with golden dragon pillars and red carpet",
                "empress's private garden with peacocks and chrysanthemums",
                "palace rooftop at midnight under crescent moon",
                "royal banquet hall with hundreds of lanterns and silk drapes",
                "imperial treasury vault glowing with jade and gold artifacts",
                "emperor's study with maps hanging and candle-lit scrolls",
                "secret tunnel beneath the palace, torchlight on stone walls",
                "execution courtyard at grey dawn, mist on cold stone",
            ],
            "tien-hiep": [
                "floating mountain temple above clouds with waterfalls",
                "ancient shrine deep in misty bamboo forest",
                "spirit realm with glowing energy rivers and floating rocks",
                "ancient cave with glowing crystals and rune inscriptions",
                "battle arena on a cloud island during thunderstorm",
                "ancient Chinese forest at night with glowing firefly spirits",
                "volcano crater with ancient altar and lava glow",
                "underwater palace with bioluminescent coral and fish spirits",
            ],
            "huyen-huyen": [
                "mystical ancient forest with glowing runes on tree bark",
                "demon realm with black mist and floating obsidian pillars",
                "ancient Chinese magic duel arena with lightning and fire",
                "spirit marketplace at night with glowing ghost lanterns",
                "cursed ancient manor overgrown with dark vines",
                "celestial palace above clouds with golden light beams",
                "underworld gate with skull carvings and blue fire torches",
                "ancient crossroads at midnight with magic circle glowing",
            ],
            "xuyen-khong": [
                "ancient Chinese market street at dusk, oil lamps lit",
                "traditional inn courtyard with horses and lanterns",
                "ancient city gate at dawn with arriving travelers",
                "countryside road through rice fields in summer",
                "ancient Chinese harbor with wooden ships at sunset",
                "mountain pass in autumn with red maple leaves",
                "ancient kitchen with clay stoves and hanging herbs",
                "village festival at night with dragon dance and fireworks",
            ],
            "trong-sinh": [
                "ancient Chinese courtyard with cherry blossoms falling",
                "moonlit garden with stone bench and tears",
                "old family mansion at dusk, gates closing",
                "riverbank farewell scene at golden sunset",
                "ancient Chinese hospital room with herbal medicine",
                "memorial hall with white flowers and incense",
                "rainy ancient alley with oil-paper umbrella",
                "wedding preparation chamber with red silk and mirrors",
            ],
            "dam-my": [
                "ancient Chinese scholarly study with bamboo and ink",
                "mountain retreat with two silhouettes and pine trees",
                "elegant wine pavilion overlooking valley at sunset",
                "secret garden with white magnolia blooms at dawn",
                "ancient library tower with thousands of scrolls",
                "lakeside dock at night under starlit sky",
                "martial arts training ground at dawn with mist",
                "ancient chess pavilion on hilltop in autumn",
            ],
        },
        "character_guide": (
            "Character wears HANFU (ancient Chinese robe): specify color (crimson/jade green/"
            "ivory/midnight blue/gold), sleeve style (wide/layered), hair in traditional "
            "updo with hairpin (簪子), or flowing with ribbon. Include key accessories."
        ),
        "lighting_options": [
            "warm candlelight glow", "moonlight through lattice window",
            "golden sunset backlight", "misty morning diffused light",
            "red lantern warm light", "dramatic chiaroscuro shadow",
        ],
    },

    # ── Hiện đại: Đương đại (2000s → nay) ────────────────────────
    "hien-dai": {
        "system": (
            "You are a visual director specializing in modern Asian drama (现代剧/phim hiện đại) "
            "story videos for YouTube Shorts and TikTok. "
            "Characters wear contemporary clothes. Settings are modern urban environments. "
            "Style: photorealistic, like a high-quality C-drama or Vietnamese drama series. "
            "Output ONLY the English image prompt. No explanation. No quotes."
        ),
        "brand_suffix": (
            "modern Asian drama style, photorealistic, "
            "contemporary urban setting, professional cinematography, "
            "shallow depth of field, natural color grading, "
            "cinematic lighting, ultra detailed, 8K resolution, "
            "complete scene fully framed, no cropped limbs, "
            "perfect anatomy, two arms, fully clothed, "
            "no text, no watermark, no blur"
        ),
        "genre_hints": {
            "ngon-tinh": [
                "luxury apartment living room at night with city lights outside",
                "rainy café window seat with blurred city street",
                "hospital rooftop garden at golden hour",
                "modern wedding venue decorated with white flowers",
                "airport departure terminal with farewell crowd",
                "seaside cliff walkway at sunset",
                "upscale restaurant private dining room, candlelit",
                "modern bedroom at 3am with single lamp on",
            ],
            "do-thi": [
                "glass skyscraper office interior at night, city below",
                "underground subway station at rush hour",
                "night market street food stalls with neon signs",
                "corporate boardroom with floor-to-ceiling windows",
                "luxury hotel lobby with marble floors",
                "convenience store at midnight, harsh fluorescent light",
                "construction site at sunset with golden dust",
                "rooftop bar overlooking city skyline at dusk",
            ],
            "co-trang": [
                "modern city park with cherry blossoms",
                "contemporary drama apartment at dusk",
                "urban riverside walkway at golden hour",
                "modern museum atrium with skylights",
                "quiet suburban street on a rainy evening",
                "modern home kitchen at warm evening light",
                "university campus garden in autumn",
                "modern shopping mall empty corridor at night",
            ],
            "xuyen-khong": [
                "ancient-meets-modern architecture clash, dramatic contrast",
                "modern city street with ancient temple visible behind",
                "traditional Vietnamese home interior, nostalgic",
                "modern hospital room with old photo on wall",
                "contemporary apartment with traditional decor details",
                "modern library with ancient artifact display",
                "downtown street contrasting old and new buildings",
                "modern home altar room at candle-lit evening",
            ],
            "trong-sinh": [
                "modern hospital corridor at 3am, fluorescent shadows",
                "contemporary funeral hall with white flowers",
                "modern apartment living room after argument, scattered items",
                "rainy night street with one umbrella and streetlamps",
                "modern court hallway, cold marble and tension",
                "home driveway at dawn, suitcase by the door",
                "modern café alone at corner table, cold coffee",
                "contemporary wedding hall, empty before ceremony",
            ],
            "dam-my": [
                "modern apartment shared living space, evening light",
                "gym or training studio late at night",
                "contemporary rooftop with string lights at night",
                "modern art studio with paintings and scattered brushes",
                "late-night convenience store with two figures",
                "modern karaoke room, dim colorful lights",
                "outdoor basketball court at dusk",
                "modern office kitchen, early morning quiet",
            ],
            "hai-huoc": [
                "bright cheerful modern café with pastel decor",
                "chaotic modern apartment kitchen mid-cooking disaster",
                "sunny campus courtyard with students",
                "busy modern supermarket, colorful and lively",
                "cheerful flower market on a sunny morning",
                "modern office pantry with coworkers chatting",
                "colorful street festival with food vendors",
                "bright modern gym with morning sunlight",
            ],
        },
        "character_guide": (
            "Character wears MODERN CONTEMPORARY CLOTHES: specify outfit type "
            "(casual jeans+top, office blazer, dress, hospital scrubs, etc.), "
            "modern hairstyle (straight/wavy/ponytail), and any key accessories "
            "(glasses, watch, bag). NO hanfu, NO ancient clothing."
        ),
        "lighting_options": [
            "natural window light", "golden hour sunlight", "city neon at night",
            "soft indoor LED lighting", "overcast day soft light",
            "dramatic office fluorescent", "warm café ambient light",
        ],
    },

    # ── Hiện đại thập niên: Retro (thập niên 60–2000) ────────────
    "thap-nien": {
        "system": (
            "You are a visual director specializing in retro Vietnamese/Chinese era drama "
            "story videos for YouTube Shorts and TikTok. "
            "Characters wear era-specific vintage clothing (1960s–2000s). "
            "Settings are vintage/retro environments from a specific historical decade. "
            "Style: vintage film photography aesthetic, nostalgic warm tones. "
            "Output ONLY the English image prompt. No explanation. No quotes."
        ),
        "brand_suffix": (
            "retro Vietnamese/Chinese drama style, vintage film photography, "
            "nostalgic warm tones, Kodachrome color grading, "
            "film grain texture, soft vignette, "
            "authentic period-accurate details, 8K resolution, "
            "complete scene fully framed, no cropped limbs, "
            "perfect anatomy, two arms, fully clothed period costume, "
            "no text, no watermark, no blur"
        ),
        "genre_hints": {
            "default": [
                "vintage Vietnamese street scene with old shophouses and bicycles",
                "rural countryside with bamboo fence and rice paddies",
                "old market alley with hanging lanterns and wooden stalls",
                "period home interior with wooden furniture and kerosene lamp",
                "vintage river dock at dawn with wooden boats",
                "old school courtyard with frangipani tree in bloom",
                "wartime train station with crowds and steam",
                "village communal house at festival evening with lanterns",
            ],
            "60s": [
                "1960s Vietnamese town street with black bicycles and áo dài women",
                "old shop house interior with wooden counter and goods",
                "1960s rural home with clay stove and earthen floor",
                "wartime refugee camp with tents and bare trees",
                "1960s Chinese commune courtyard with red banners",
                "old Vietnamese market with produce and conical hats",
                "1960s school classroom with wooden desks and chalk board",
                "riverside 1960s setting with sampan boats at sunset",
            ],
            "70s": [
                "1970s Vietnamese countryside with bamboo house and banana trees",
                "post-war village reconstruction scene at dawn",
                "1970s cooperative farm with workers in fields",
                "old Vietnamese kitchen with clay pots and wood fire",
                "1970s river market with wooden boats and morning mist",
                "rural commune meeting hall, simple wooden interior",
                "1970s provincial town street with few bicycles",
                "old forest path with sunlight through bamboo grove",
            ],
            "80s": [
                "1980s Vietnamese market alley with perm-haired vendors",
                "old apartment block stairwell with peeling paint",
                "1980s TV shop with black-and-white screens in window",
                "retro Vietnamese home with plastic flowers and thermos",
                "1980s Chinese city street with Liberation trucks and bicycles",
                "old cinema entrance with handpainted movie posters",
                "period hair salon with retro mirrors and equipment",
                "1980s night market lit by kerosene lamps",
            ],
            "90s": [
                "1990s Vietnamese street with early motorbikes and VHS rental shop",
                "90s karaoke room with disco ball and velvet curtains",
                "90s internet café with old CRT monitors",
                "vintage 90s Vietnamese home with tile floors and lace curtains",
                "90s bus station with crowds and handwritten schedules",
                "old 90s hospital corridor with pale green walls",
                "90s school canteen with long wooden tables",
                "90s street food cart at night market with neon signs",
            ],
            "2000s": [
                "early 2000s Vietnamese café with flip phones on table",
                "Y2K era bedroom with pop-star posters and CD tower",
                "2000s shopping center with tiled floors and early fashion",
                "old Nokia-era phone booth on a city corner",
                "early 2000s university campus with concrete buildings",
                "2000s era wedding photo studio with velvet backdrop",
                "early internet café with bulky desktop computers",
                "2000s night market with early LED signs and crowds",
            ],
        },
        "character_guide": (
            "Character wears ERA-SPECIFIC VINTAGE CLOTHES: identify the decade first, then specify "
            "period-accurate outfit (e.g., 1980s: perm hair, retro blouse, flared pants; "
            "1970s: áo bà ba, simple rural dress; 1990s: 90s fashion trends). "
            "NO modern clothes, NO hanfu. Include era-accurate hairstyle and accessories."
        ),
        "lighting_options": [
            "warm Kodachrome film tones", "soft vintage yellow lighting",
            "kerosene lamp warm glow", "natural daylight with film grain",
            "overcast vintage soft light", "sunset golden retro tones",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────
# SHOT TYPES — kiểu cảnh quay điều hướng loại hình ảnh được tạo
# ─────────────────────────────────────────────────────────────────

SHOT_TYPES = {
    # Cận cảnh cảm xúc — CHỈ mặt và cổ, không tay không thân
    "close_up": {
        "composition_9:16":  "extreme tight portrait, face and neck only, chin to crown, NO shoulders NO hands NO body, bokeh background",
        "composition_16:9":  "tight face portrait, face on left third, cropped at collarbone, NO hands visible, bokeh right side",
        "composition_19:6":  "extreme close-up banner, face from chin to crown, left third, NO body below neck",
        "use_character":     True,
        "instructions": (
            "SHOT: Emotional close-up — FACE AND NECK ONLY\n"
            "- Frame TIGHTLY: from chin to top of head, cropped at collarbone\n"
            "- ABSOLUTELY NO hands, NO shoulders, NO body below neck in frame\n"
            "- Show intense emotion through: eyes, brow, parted lips, tears, jaw tension\n"
            "- Shallow depth of field, soft bokeh background\n"
            "- Do NOT mention hands or arms in the prompt\n"
        ),
    },
    # Trung cảnh — bán thân, tay ở tư thế an toàn
    "medium": {
        "composition_9:16":  "medium portrait, waist-up framing, character and environment balanced",
        "composition_16:9":  "medium wide shot, character waist-up on left third, environment fills right",
        "composition_19:6":  "cinematic medium shot, character waist-up on left third, sweeping environment",
        "use_character":     True,
        "instructions": (
            "SHOT: Medium shot — waist-up, hands completely hidden\n"
            "- Show character from waist up\n"
            "- HANDS MUST BE COMPLETELY HIDDEN — use one of these only:\n"
            "  * hands deep in pockets (jacket/coat/trousers pockets)\n"
            "  * hands tucked fully inside sleeves (hanfu wide sleeves)\n"
            "  * arms hanging straight down at sides, wrists/hands below frame\n"
            "  * character turned 3/4 angle so one arm hidden behind body\n"
            "- NEVER describe: arms crossed, hands clasped, hands touching anything\n"
            "- NEVER mention fingers, wrists, palms, knuckles\n"
            "- Environment visible and meaningful behind the character\n"
        ),
    },
    # Toàn cảnh — môi trường là chủ thể, nhân vật chỉ là bóng nhỏ hoặc không có
    "wide": {
        "composition_9:16":  "wide establishing shot, grand environment fills frame, lone tiny silhouette in far distance",
        "composition_16:9":  "epic wide shot, vast landscape or grand interior dominates, character tiny speck in distance",
        "composition_19:6":  "panoramic epic wide, sweeping environment dominates 95% of frame, tiny silhouette only",
        "use_character":     False,
        "instructions": (
            "SHOT: Wide establishing — environment is the HERO, no anatomy needed\n"
            "- Character is a tiny dark silhouette in the far distance OR completely absent\n"
            "- NO face, NO hands, NO body details — just a small shape\n"
            "- Focus entirely on: grand architecture, sweeping landscape, dramatic sky, epic scale\n"
            "- 90%+ of frame is environment\n"
        ),
    },
    # Nhân vật nhìn từ sau lưng — tránh hoàn toàn anatomy mặt và tay
    "back_view": {
        "composition_9:16":  "character seen entirely from behind, back to camera, facing into grand environment",
        "composition_16:9":  "back view of character, seen from behind, looking out into landscape or dramatic space",
        "composition_19:6":  "wide back-view shot, character from behind facing vast environment, silhouette-like",
        "use_character":     True,
        "instructions": (
            "SHOT: Back view — character seen from BEHIND only\n"
            "- We see ONLY the character's back — NO face, NO hands, NO front of body\n"
            "- Character faces AWAY from camera into the environment\n"
            "- CLOTHING MUST FULLY COVER the back: long-sleeved robe, jacket, coat, hanfu, "
            "  tunic — NO strapless, NO backless, NO off-shoulder, NO bare skin on back\n"
            "- Show hair and FULLY COVERED back of clothing\n"
            "- Grand environment visible ahead of them\n"
            "- Safe anatomy: no face, no hands needed\n"
        ),
    },
    # Cận cảnh vật thể biểu tượng — không nhân vật, không anatomy
    "detail": {
        "composition_9:16":  "extreme macro close-up of symbolic object, no face no hands no person, rich texture",
        "composition_16:9":  "detail shot, one symbolic object centered, rich texture, moody dramatic lighting",
        "composition_19:6":  "wide detail shot, symbolic object across frame, cinematic texture, no person",
        "use_character":     False,
        "instructions": (
            "SHOT: Detail / symbolic object — NO person, NO anatomy at all\n"
            "- ONE meaningful OBJECT fills the frame: burning letter, jade pendant, cold tea cup,\n"
            "  folded paper, torn fabric, phone screen with message, antique mirror, wilted flower\n"
            "- ABSOLUTELY no face, no hands, no body parts\n"
            "- Extreme close-up macro feel, rich texture, cinematic lighting\n"
            "- The object alone tells the emotional story\n"
        ),
    },
    # Cảnh không khí — môi trường thuần túy, không nhân vật
    "atmospheric": {
        "composition_9:16":  "pure atmospheric mood, NO person at all, dramatic environment and light only",
        "composition_16:9":  "cinematic atmosphere, empty moody environment, dramatic light and shadow, no person",
        "composition_19:6":  "atmospheric panorama, dramatic sky and environment, absolutely no person, cinematic",
        "use_character":     False,
        "instructions": (
            "SHOT: Pure atmosphere — NO person, NO anatomy whatsoever\n"
            "- EMPTY environment only: rain streaking a window, candle flame flickering,\n"
            "  fog rolling through an alley, empty chair by a door, moonlight on still water,\n"
            "  golden light through curtains, storm clouds over a rooftop, snow on a garden\n"
            "- NO silhouette, NO shadow of person — purely environment and light\n"
            "- Heavy cinematic mood, painterly quality\n"
        ),
    },
    # Cảnh hành động — chuyển động, tay ở tư thế tự nhiên khi di chuyển
    "action": {
        "composition_9:16":  "dynamic action, character walking or turning, seen from behind or side, flowing fabric",
        "composition_16:9":  "action shot, character in motion seen from behind or side, diagonal energy, motion blur",
        "composition_19:6":  "wide action, character walking away into environment, arms naturally swinging at sides",
        "use_character":     True,
        "instructions": (
            "SHOT: Action / movement — natural motion, safe anatomy\n"
            "- Character is WALKING, TURNING, or RUNNING — seen from BEHIND or SIDE angle\n"
            "- Arms swing naturally at sides during walking — simple straight arms, no detailed hands\n"
            "- Use motion blur on arms to avoid needing detailed anatomy\n"
            "- Flowing hair, billowing fabric, dust convey motion\n"
            "- Do NOT describe hands reaching, grabbing, or pointing\n"
        ),
    },
    # Cảnh hai nhân vật — waist-up, tay ở tư thế an toàn
    "two_shot": {
        "composition_9:16":  "two figures facing each other, waist-up framing, emotional space between them",
        "composition_16:9":  "two-shot, both characters waist-up, left and right thirds, space between them",
        "composition_19:6":  "wide two-shot, two figures waist-up at opposite ends, dramatic space between",
        "use_character":     True,
        "instructions": (
            "SHOT: Two characters — waist-up, safe hand poses\n"
            "- TWO people in frame, both waist-up\n"
            "- SAFE poses: arms crossed | hands clasped in front | arms at sides relaxed\n"
            "- The space and emotion BETWEEN them is the subject\n"
            "- Do NOT describe hand gestures, touching, or reaching toward each other\n"
        ),
    },
}

# Rotation đảm bảo 6-8 scene có đa dạng loại cảnh
# Ưu tiên shot an toàn về anatomy: back_view, atmospheric, wide, detail
_SHOT_ROTATION = ["medium", "close_up", "back_view", "atmospheric", "detail", "wide", "back_view", "close_up"]

# Override dựa theo cảm xúc
_EMOTION_SHOT_OVERRIDE = {
    "shock":    "close_up",
    "fear":     "atmospheric",
    "love":     "two_shot",
    "betrayal": "detail",
    "hope":     "wide",
    "anger":    "action",
    "sadness":  "atmospheric",
    "panic":    "action",
    "joy":      "wide",
}


# ─────────────────────────────────────────────────────────────────
# BEAUTY POOLS — mô tả gái xinh theo era, dùng cho prompt_raw
# ─────────────────────────────────────────────────────────────────

_BEAUTY_CHARS = {
    "co-trang": [
        "gorgeous Chinese beauty, porcelain skin, almond eyes, deep crimson lips, elaborate gold hairpin in black updo",
        "enchanting hanfu girl, bright tearful eyes, cherry lips, pale flawless skin, jade flower hairpin, delicate presence",
        "stunning ancient empress, sharp phoenix eyes, bold red lips, luminous ivory skin, phoenix crown with gold and pearl",
        "captivating palace lady in ivory hanfu with silver embroidery, gentle doe eyes, soft pink lips, silver moon hairpin",
        "mesmerizing court beauty, deep knowing eyes, subtle smile, obsidian hair in loose bun, midnight blue hanfu",
        "noble young princess, innocent bright eyes, coral lips, flawless complexion, pearl-studded hairpin, graceful",
        "ethereal celestial maiden, luminous skin, serene silver eyes, white flower crown, transcendent otherworldly beauty",
        "fierce warrior princess, intense dark eyes, bold lips, battle-worn yet breathtaking, armored hanfu silhouette",
        "mysterious beauty behind gauze veil, smoldering eyes visible, gold-threaded silk hanfu, alluring mystique",
        "tender handmaiden beauty, shy downcast eyes, soft blush cheeks, simple elegant hairpin, innocent charm",
    ],
    "hien-dai": [
        "stunning Vietnamese beauty, flawless dewy skin, full glossy lips, bright expressive eyes, sleek straight black hair",
        "gorgeous modern Asian woman, sophisticated smoky eye makeup, nude lips, radiant complexion, silky hair in waves",
        "captivating young woman, bold red lips, dramatic lashes, luminous glass skin, chic bob haircut",
        "beautiful Korean-style beauty, soft gradient lips, puppy eyes, honey glow skin, pastel outfit, trendy style",
        "striking modern woman, editorial sharp liner makeup, matte lips, high cheekbones, power blazer and sleek ponytail",
        "fresh natural beauty, minimal makeup, bright clear eyes, oversized cream sweater, effortlessly attractive",
        "glamorous urban woman, full glam makeup, statement earrings, satin blouse, polished and confident",
        "indie aesthetic beauty, artistic makeup, eclectic outfit, soft dreamy eyes, unique personal style",
        "sophisticated office woman, tailored suit, subtle elegant makeup, sharp intelligent eyes, professional poise",
        "bohemian free spirit, flowing dress, natural dewy skin, flower accessory in hair, warm and radiant",
    ],
    "thap-nien": {
        "60s": [
            "elegant 1960s Vietnamese beauty in áo dài, refined winged liner makeup, pearl earrings, graceful and composed",
            "classic 1960s beauty, vintage updo with flowers, bold cat-eye makeup, cheongsam neckline, timeless elegance",
            "1960s Vietnamese girl, simple floral áo dài, delicate natural beauty, period-accurate refined charm",
        ],
        "70s": [
            "charming 1970s Asian beauty, natural 70s makeup, bohemian floral dress, feathered hair, warm nostalgic charm",
            "1970s Vietnamese girl in áo bà ba, simple beautiful face, fresh natural makeup, countryside warmth",
            "seventies beauty, earth-tone outfit, natural afro-inspired voluminous hair, warm sun-kissed skin",
        ],
        "80s": [
            "iconic 1980s Vietnamese beauty, permed voluminous hair, bold colorful makeup, retro blouse with ruffles",
            "1980s Chinese girl, perm hairdo, bright eyeshadow, retro shoulder-pad outfit, full of era energy",
            "eighties glam beauty, big teased hair, neon accent makeup, bold fashion, vivacious and expressive",
        ],
        "90s": [
            "quintessential 1990s Asian beauty, thin 90s eyebrows, glossy lips, butterfly clips in straight hair",
            "1990s Vietnamese girl, blunt-cut bob, natural 90s makeup, simple elegant dress, nostalgic warmth",
            "nineties style beauty, frosted lip gloss, dark outlined lips, spaghetti strap dress, 90s attitude",
        ],
        "2000s": [
            "Y2K era beauty, glossy lip gloss, shimmer eyeshadow, flat-ironed hair, early 2000s fashion",
            "early 2000s Asian girl, butterfly clips, sparkly accessories, low-rise outfit, Y2K vibes",
            "2000s Vietnamese girl, chunky highlights in hair, glittery makeup, trendy early-aughts look",
        ],
        "default": [
            "vintage Vietnamese beauty in retro era clothing, classic makeup of the period, timeless feminine charm",
            "nostalgic Asian beauty, vintage fashion, period-appropriate makeup, warm film photograph aesthetic",
        ],
    },
}

_BEAUTY_SCENES = {
    "co-trang": [
        "moonlit imperial garden with blooming peonies and silk lanterns, ethereal romantic atmosphere",
        "misty mountain pavilion above clouds at dawn, ancient stone steps and pine trees, serene majesty",
        "candlelit palace chamber with gold silk drapes and jade ornaments, rich warm glow",
        "snow-dusted plum blossom garden at dusk, red petals falling on stone path, melancholic beauty",
        "grand imperial hall with dragon pillars and red lacquer, opulent golden light beams",
        "secret lotus pond at night with glowing fireflies and stone bridge reflection, mystical calm",
        "ancient library tower with thousands of scrolls and warm amber lantern light, scholarly elegance",
        "rooftop pavilion under full moon with incense smoke curling upward, peaceful and poetic",
        "waterfall valley with mist and ancient temple partially hidden in bamboo, spiritual beauty",
        "frozen winter lake reflecting moonlight, bare willow branches, solitary red lantern on dock",
    ],
    "hien-dai": [
        "luxury penthouse with floor-to-ceiling city view at night, elegant minimalist decor",
        "rooftop garden with string lights and city skyline at golden hour, romantic urban setting",
        "upscale café corner with soft warm light, fresh flowers on marble table, refined ambiance",
        "rain-soaked city street at night with neon reflections on wet pavement, cinematic mood",
        "modern minimalist bedroom with sheer white curtains and soft morning light",
        "sleek glass office tower lobby with marble floors, polished sophisticated atmosphere",
        "beachside cliffwalk at sunset with golden light shimmering on calm water",
        "cozy bookshop with warm wooden shelves and reading lamps, intellectual warmth",
        "empty rooftop pool at night reflecting city lights, cool blue luxury atmosphere",
        "flower market at golden hour, colorful blooms overflowing, warm cheerful light",
    ],
    "thap-nien": [
        "vintage Vietnamese street with old shophouses and flickering lanterns, warm nostalgic glow",
        "1990s karaoke room with velvet curtains and disco ball, retro colorful haze",
        "old riverside dock at dawn with wooden boats and morning mist, timeless quiet beauty",
        "vintage tea house with wooden furniture and kerosene lamp warm glow, sepia tones",
        "1970s rural countryside with bamboo fence and golden rice paddies, pastoral tranquility",
        "1980s night market with handpainted signs and incandescent bulbs, vibrant retro energy",
        "early 2000s internet café, blue CRT monitor glow, nostalgic late-night atmosphere",
        "classic photo studio with velvet backdrop and vintage studio lights, elegant timeless",
        "old Vietnamese cinema entrance with handpainted posters, warm evening light",
        "period home interior with tiled floor, lace curtains and family photos on wall",
    ],
}


def pick_shot_type(scene_index: int, total_scenes: int, emotion: str = "") -> str:
    """
    Chọn shot type cho scene dựa trên vị trí và cảm xúc.
    - Scene đầu luôn là medium (establishing)
    - Scene cuối luôn là close_up (ending impact)
    - Các scene giữa: emotion override ưu tiên, nếu không thì theo rotation
    """
    if scene_index == 0:
        return "medium"
    if scene_index == total_scenes - 1:
        return "close_up"
    # Emotion override cho scene giữa
    if emotion and emotion.lower() in _EMOTION_SHOT_OVERRIDE:
        override = _EMOTION_SHOT_OVERRIDE[emotion.lower()]
        # Nếu scene trước đã dùng loại này, vẫn dùng (emotion quan trọng hơn variety)
        return override
    # Fallback rotation
    return _SHOT_ROTATION[scene_index % len(_SHOT_ROTATION)]


def create_prompt(
    sentence: str = "",   # noqa: unused — beauty pool không dùng sentence
    ratio: str = "9:16",
    genre: str = "co-trang",
    era: str = "co-trang",
    decade: str = "",
    character_desc: str = "",
    action: str = "",     # noqa: unused — beauty pool không dùng action
    setting: str = "",    # noqa: unused — beauty pool không dùng setting
    shot_type: str = "medium",
    scene_index: int = 0,
) -> str:
    """
    Tạo FLUX image prompt dựa trên beauty pool (không bám câu truyện).

    Args:
        sentence:       Không dùng (giữ để tương thích với caller cũ)
        ratio:          "9:16" | "16:9" | "1:1" | "19:6"
        genre:          Thể loại (co-trang, ngon-tinh, ...)
        era:            "co-trang" | "hien-dai" | "thap-nien"
        decade:         Thập niên khi era="thap-nien" (vd: "80s", "90s")
        character_desc: Mô tả nhân vật cố định — giữ đồng nhất qua các scene
        action:         Hành động cụ thể của scene
        setting:        Bối cảnh không gian của scene
        shot_type:      Loại cảnh quay — xem SHOT_TYPES dict
        scene_index:    Vị trí scene (0-based) — dùng để rotate setting_hint đa dạng
    """
    # Lấy profile theo era
    profile = ERA_PROFILES.get(era, ERA_PROFILES["co-trang"])
    brand_suffix = profile["brand_suffix"]
    genre_hints  = profile["genre_hints"]
    # Shot type config
    shot = SHOT_TYPES.get(shot_type, SHOT_TYPES["medium"])
    # Map ratio → composition key
    if ratio == "9:16":
        composition = shot["composition_9:16"]
    elif ratio == "19:6":
        composition = shot["composition_19:6"]
    else:
        composition = shot["composition_16:9"]

    use_character = shot["use_character"]

    # Genre/setting hint — pick từ list theo scene_index để đa dạng bối cảnh
    if era == "thap-nien":
        hints = genre_hints.get(decade or "default", genre_hints["default"])
    else:
        hints = genre_hints.get(genre, next(iter(genre_hints.values())))
    setting_hint = hints[scene_index % len(hints)] if isinstance(hints, list) else hints

    # Character anchor — chỉ dùng khi shot type cần nhân vật
    char_anchor = f"SAME CHARACTER: {character_desc}. " if (character_desc and use_character) else ""

    # Chọn lighting phù hợp với cảm xúc từ profile
    lighting_opts = profile.get("lighting_options", ["dramatic cinematic lighting"])
    lighting = lighting_opts[scene_index % len(lighting_opts)]

    # ── Beauty pool: chọn theo era + scene_index để đa dạng qua 20 thumbnail ──
    if use_character:
        if era == "thap-nien":
            dec = decade or "default"
            char_pool = _BEAUTY_CHARS["thap-nien"].get(dec, _BEAUTY_CHARS["thap-nien"]["default"])
        else:
            char_pool = _BEAUTY_CHARS.get(era, _BEAUTY_CHARS["co-trang"])
        beauty_desc = char_pool[scene_index % len(char_pool)]
        # Nếu character_desc được truyền vào (từ scenes.json), ưu tiên dùng nhưng
        # thêm beauty desc để FLUX hiểu rõ hơn về nhan sắc
        char = beauty_desc if not character_desc else f"{character_desc}, {beauty_desc}"
        prompt_raw = f"{char}, {setting_hint}, {lighting}, {composition}"
    else:
        scene_pool = _BEAUTY_SCENES.get(era, _BEAUTY_SCENES["co-trang"])
        scene_desc = scene_pool[scene_index % len(scene_pool)]
        prompt_raw = f"{scene_desc}, {lighting}, {composition}"

    # Đặt character anchor ở đầu nếu cần và chưa có
    if char_anchor and char_anchor.lower()[:30] not in prompt_raw.lower():
        prompt_raw = char_anchor + prompt_raw

    # Loại bỏ từ khoá gây lỗi anatomy khỏi prompt_raw
    _ARM_WORDS = ["reaching out", "reaching forward", "pointing finger",
                  "grabbing", "outstretched arm", "extended arm",
                  "three arms", "extra arm", "multiple arms"]
    for bad in _ARM_WORDS:
        prompt_raw = prompt_raw.replace(bad, "")

    # Suffix anatomy theo shot type — cứng, không thể bị Ollama override
    _ANATOMY_SUFFIX = {
        "close_up":   "face and neck portrait only, cropped at collarbone, NO arms NO hands NO shoulders visible, natural neck posture",
        "medium":     "hands completely out of frame hidden in pockets or sleeves, NO fingers NO palms NO wrists visible, natural neck and head alignment",
        "back_view":  "seen from behind only, fully covered back clothing, NO bare skin on back, NO face NO hands visible",
        "action":     "character as flowing silhouette, arms blurred by motion, no detailed limbs",
        "two_shot":   "both figures chest-up only, hands hidden in pockets or sleeves, NO hand gestures NO fingers visible",
        "wide":       "tiny distant silhouette only, no anatomical detail whatsoever",
        "atmospheric":"EMPTY ENVIRONMENT ONLY — absolutely no person, no human, no face, no body, pure environment and light",
        "detail":     "INANIMATE OBJECT ONLY — absolutely no person, no human, no face, no hands, no body parts whatsoever",
    }
    anatomy_suffix = _ANATOMY_SUFFIX.get(shot_type, "")

    # Cho detail/atmospheric/wide: xoá toàn bộ mô tả người khỏi Ollama output
    if shot_type in ("detail", "atmospheric", "wide"):
        _PERSON_WORDS = [
            "woman", "man", "person", "people", "figure", "character", "girl", "boy",
            "she", "he", "her", "his", "face", "eye", "lip", "hair", "hand", "arm",
            "body", "portrait", "standing", "sitting", "walking", "wearing", "dressed",
            "expression", "emotion", "looking", "gazing",
        ]
        for pw in _PERSON_WORDS:
            # Thay thế toàn bộ từ khớp (kể cả dạng inflected đơn giản)
            import re
            prompt_raw = re.sub(rf'\b{re.escape(pw)}\w*\b', '', prompt_raw, flags=re.IGNORECASE)
        prompt_raw = re.sub(r'\s+', ' ', prompt_raw).strip(', ')
        # Thêm prefix cứng no-person
        prompt_raw = f"NO PERSON NO HUMAN — {prompt_raw}"

    # Ghép prefix + anatomy suffix + brand suffix theo era
    full_prompt = f"{NEGATIVE_PREFIX}{prompt_raw}, {anatomy_suffix}, {brand_suffix}"

    # NSFW fallback
    if not is_safe_prompt(full_prompt):
        if use_character:
            if era == "hien-dai":
                safe_char = character_desc or "young Asian woman in casual modern outfit"
            elif era == "thap-nien":
                safe_char = character_desc or "young woman in vintage era clothing"
            else:
                safe_char = character_desc or "young Chinese woman in elegant hanfu"
            full_prompt = (
                f"{NEGATIVE_PREFIX}{char_anchor}{safe_char}, "
                f"serene expression, {composition}, soft natural lighting, {brand_suffix}"
            )
        else:
            full_prompt = (
                f"{NEGATIVE_PREFIX}{setting_hint}, peaceful atmosphere, "
                f"{composition}, soft natural lighting, {brand_suffix}"
            )

    return full_prompt


# ─────────────────────────────────────────────────────────────────
# Image generator — gọi FLUX.1-schnell trên HuggingFace
# ─────────────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    headers: dict,
    ratio: str = "9:16",
    seed: int | None = None,
) -> Image.Image:
    """
    Generate ảnh từ FLUX.1-schnell.

    Args:
        prompt:  Text prompt đã được xử lý
        headers: {"Authorization": "Bearer hf_..."}
        ratio:   "9:16" | "16:9" | "1:1"
        seed:    Seed cố định → giữ style nhất quán giữa các scene cùng truyện

    Returns:
        PIL Image object
    """
    width, height = SIZES.get(ratio, SIZES["9:16"])

    params: dict = {
        "width":               width,
        "height":              height,
        "num_inference_steps": 8,
        "guidance_scale":      0.0,
    }
    if seed is not None:
        params["seed"] = seed

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json={"inputs": prompt, "parameters": params},
            timeout=120,
        )

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

        image = Image.open(io.BytesIO(response.content))
        return image

    except Exception as e:
        print(f"Image generation error: {e}")
        img = Image.new("RGB", (width, height), color=(13, 13, 26))  # #0D0D1A brand color
        return img


# ─────────────────────────────────────────────────────────────────
# Tiện ích: tạo ảnh nhanh từ câu truyện (all-in-one)
# ─────────────────────────────────────────────────────────────────

def sentence_to_image(
    sentence: str,
    headers: dict,
    ratio: str = "9:16",
    genre: str = "co-trang",
    era: str = "co-trang",
    decade: str = "",
    character_desc: str = "",
    action: str = "",
    setting: str = "",
    seed: int | None = None,
    shot_type: str = "medium",
    scene_index: int = 0,
) -> tuple[Image.Image, str]:
    """
    Chuyển 1 câu truyện → prompt → ảnh.

    Args:
        era:            "co-trang" | "hien-dai" | "thap-nien"
        decade:         Thập niên khi era="thap-nien" (vd: "80s", "90s")
        character_desc: Mô tả nhân vật cố định (đảm bảo đồng nhất qua mọi scene)
        action:         Hành động cụ thể của scene
        setting:        Bối cảnh không gian của scene
        seed:           Seed cố định cho toàn bộ story
        shot_type:      Loại cảnh: close_up | medium | wide | detail | atmospheric | action | two_shot
        scene_index:    Vị trí scene (0-based) — rotate setting hint để đa dạng bối cảnh

    Returns:
        (PIL Image, prompt đã dùng)
    """
    prompt = create_prompt(
        sentence, ratio=ratio, genre=genre,
        era=era, decade=decade,
        character_desc=character_desc, action=action, setting=setting,
        shot_type=shot_type, scene_index=scene_index,
    )
    image = generate_image(prompt, headers, ratio=ratio, seed=seed)
    return image, prompt
