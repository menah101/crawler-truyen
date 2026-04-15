import logging
from PIL import Image

try:
    from hf_image import generate_flux_image
except ImportError:
    from .hf_image import generate_flux_image  # type: ignore

logger = logging.getLogger(__name__)

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
        # ── 20 cô gái cổ trang: mộng mơ, dịu dàng, mỗi người khác kiểu tóc/trang phục/biểu cảm ──
        "dreamy beautiful girl, soft glowing porcelain skin, gentle shy smile, long flowing black hair with gold butterfly hairpin, crimson silk hanfu, warm golden light, romantic ethereal mood, soft focus bokeh",
        "dreamy beautiful girl, dewy luminous skin, wistful teary doe eyes, hair in elegant high bun with dangling jade ornaments, white layered hanfu with pink gradient hem, misty moonlight atmosphere",
        "dreamy beautiful girl, flawless ivory complexion, serene closed-eye expression, loose wavy hair draped over shoulder with fresh peach blossoms, light blush pink hanfu, cherry blossom petals floating, spring breeze mood",
        "dreamy beautiful girl, radiant glass-like skin, curious bright eyes with long lashes, twin braids with red ribbon, mint green embroidered hanfu, morning sunlight through bamboo, fresh youthful innocence",
        "dreamy beautiful girl, porcelain doll face, melancholic gentle gaze, straight hair with single white magnolia behind ear, lavender purple silk hanfu, soft rain outside window, poetic solitude",
        "dreamy beautiful girl, warm honey-toned skin, playful dimpled smile, messy half-up hair with pearl chain headpiece, coral orange hanfu with gold trim, sunset glow on face, warm joyful energy",
        "dreamy beautiful girl, pale moonlit complexion, mysterious half-smile, long silver-streaked hair flowing freely, midnight blue velvet hanfu with star embroidery, starlight reflections, mystical enchantment",
        "dreamy beautiful girl, soft rosy cheeks, tender loving gaze downward, neat side-swept bangs with lotus flower crown, cream white ceremonial hanfu, candlelight warmth, gentle maternal grace",
        "dreamy beautiful girl, luminous translucent skin, determined yet gentle eyes, windswept hair with sword-shaped hairpin, deep wine red warrior hanfu, dramatic cloud backdrop, elegant strength",
        "dreamy beautiful girl, fresh dewy no-makeup look, bright surprised expression, loose natural wavy hair with wildflower wreath, sage green simple cotton hanfu, forest dappled sunlight, nature fairy vibe",
        "dreamy beautiful girl, ethereal pale skin with slight blush, peaceful sleeping expression, hair spread on pillow with scattered petals, white silk inner robe, soft dawn light, tranquil dream state",
        "dreamy beautiful girl, golden sun-kissed glow, confident graceful smile, elaborate phoenix updo with ruby pins, imperial gold and red brocade hanfu, grand hall golden light, regal elegance",
        "dreamy beautiful girl, cool-toned porcelain complexion, contemplative distant gaze, straight hair in low ponytail with ice crystal pin, frost white and silver hanfu, snow falling softly, winter serenity",
        "dreamy beautiful girl, warm amber-lit skin, shy blushing expression looking away, hair in two low buns with tassel ornaments, dusty rose embroidered hanfu, lantern festival lights, romantic shyness",
        "dreamy beautiful girl, flawless dewy skin, tearful yet smiling bittersweet expression, windblown hair with loose falling hairpin, torn pale blue hanfu, autumn leaves swirling, beautiful melancholy",
        "dreamy beautiful girl, luminous fairy-like glow, enchanted wide-eyed wonder, extra-long flowing hair past waist, sheer white celestial robes with cloud motifs, floating among clouds, otherworldly grace",
        "dreamy beautiful girl, smooth warm complexion, mischievous playful wink, hair in high ponytail with fox-tail ornament, vivid tangerine orange hanfu, cherry blossom tree shade, lively charm",
        "dreamy beautiful girl, delicate pale features, composed dignified expression, sleek center-parted hair with gold filigree crown, deep emerald green formal hanfu, throne room candles, noble poise",
        "dreamy beautiful girl, natural sun-touched skin, carefree laughing with eyes closed, messy braided pigtails with daisies, light yellow cotton hanfu, open meadow breeze, pure happiness",
        "dreamy beautiful girl, ethereal icy complexion, haunting sad beauty with single tear, straight jet-black hair over one eye, pure white mourning hanfu, moonlit garden mist, tragic elegance",
    ],
    "hien-dai": [
        # ── 20 cô gái hiện đại: mộng mơ, dịu dàng, mỗi người khác phong cách ──
        "dreamy beautiful girl, flawless glass skin, gentle smile with glossy lips, long straight black hair, elegant white blouse, soft natural window light, warm romantic atmosphere, soft focus bokeh",
        "dreamy beautiful girl, dewy luminous skin, wistful gaze out rainy window, wavy hair in loose side braid, cozy cream knit sweater, café warm lighting, melancholic beauty",
        "dreamy beautiful girl, radiant Korean-style makeup, bright aegyo smile, pastel pink bob haircut, oversized soft blazer, cherry blossom background, cute sweet energy",
        "dreamy beautiful girl, natural no-makeup glow, shy dimpled smile, messy ponytail with loose strands, oversized university hoodie, golden hour campus light, fresh innocent charm",
        "dreamy beautiful girl, porcelain skin with subtle blush, serene closed-eye expression, elegant low chignon with baby breath flowers, white lace dress, soft morning light, bridal ethereal mood",
        "dreamy beautiful girl, warm honey skin tone, confident gentle gaze, sleek straight hair with middle part, tailored camel coat, autumn street golden leaves, sophisticated warmth",
        "dreamy beautiful girl, cool-toned glass skin, mysterious half-smile, jet black hair with blunt bangs, black turtleneck, moody blue-hour city lights, chic understated elegance",
        "dreamy beautiful girl, sun-kissed freckled face, carefree laughing expression, salt-wave beach hair, white linen shirt, golden sunset seaside, warm summer freedom",
        "dreamy beautiful girl, luminous dewy complexion, thoughtful reading expression, hair in loose French twist with reading glasses, cream silk blouse, bookshop warm lamp light, intellectual grace",
        "dreamy beautiful girl, soft rosy cheeks, playful tongue-out wink, twin space buns with ribbon, pastel rainbow cardigan, colorful flower market, youthful fun energy",
        "dreamy beautiful girl, flawless matte skin, elegant side-glance, slicked-back wet-look hair, emerald green satin dress, champagne-toned ballroom light, glamorous sophistication",
        "dreamy beautiful girl, natural warm glow, tender loving smile, loose curly hair with flower crown, flowing boho maxi dress, lavender field sunset, romantic free spirit",
        "dreamy beautiful girl, clear bright complexion, surprised innocent wide eyes, short fluffy layered hair, denim jacket over white tee, blue sky rooftop, girl-next-door freshness",
        "dreamy beautiful girl, pearly luminous skin, peaceful meditative expression, long straight hair center-parted, minimal white yoga outfit, zen garden morning mist, tranquil inner peace",
        "dreamy beautiful girl, dewy highlighted cheekbones, excited happy grin, high ponytail with scrunchie, sporty pastel tracksuit, cherry blossom jogging path, energetic sweetness",
        "dreamy beautiful girl, warm candlelit skin tone, tearful emotional smile, elegant updo with pearl pins, off-shoulder burgundy velvet dress, piano room soft lighting, bittersweet romance",
        "dreamy beautiful girl, cool porcelain complexion, dreamy unfocused gaze, silver-tinted long hair, oversized vintage denim jacket, neon city rain reflections, cinematic night mood",
        "dreamy beautiful girl, glowing golden skin, bright toothy smile, thick curly hair loose and voluminous, bright yellow sundress, sunflower field noon, radiant joy and warmth",
        "dreamy beautiful girl, delicate pale features, composed polished expression, sleek bob haircut, Chanel-style tweed jacket with brooch, art gallery white walls, refined taste",
        "dreamy beautiful girl, natural healthy glow, gentle caring expression, hair in messy bun with pencil through it, paint-stained apron, art studio afternoon light, creative soft beauty",
    ],
    "thap-nien": {
        "60s": [
            "dreamy beautiful 1960s girl, soft porcelain skin, gentle shy smile, classic áo dài in pastel blue, elegant winged liner, pearl drop earrings, hair in refined updo with jasmine flowers, soft golden afternoon light",
            "dreamy beautiful 1960s girl, luminous fair complexion, wistful teary eyes, white silk áo dài with delicate embroidery, bold cat-eye makeup, vintage updo with gardenia flower, misty river morning light",
            "dreamy beautiful 1960s girl, warm ivory skin, serene closed-eye expression, simple floral áo dài in light pink, natural makeup with red lips, loose wavy hair pinned with pearl clip, golden hour garden light",
            "dreamy beautiful 1960s girl, dewy fresh face, curious bright smile, cream cheongsam-collar dress, subtle liner makeup, neat French twist hairstyle, vintage classroom soft window light",
            "dreamy beautiful 1960s girl, porcelain doll face, melancholic gentle gaze, lavender áo dài with white trim, minimal rouge makeup, hair in low chignon with silk ribbon, rainy afternoon veranda light",
            "dreamy beautiful 1960s girl, radiant glowing skin, playful dimpled laugh, yellow floral áo dài, fresh natural beauty, twin braids with small bows, bright spring market sunshine",
            "dreamy beautiful 1960s girl, pale moonlit complexion, mysterious half-smile, midnight blue áo dài with silver thread, dramatic winged liner, sleek straight hair with headband, evening lantern glow",
            "dreamy beautiful 1960s girl, soft rosy cheeks, tender loving expression, traditional white áo dài for ceremony, gentle blush makeup, elaborate updo with gold pins, temple incense smoke light",
            "dreamy beautiful 1960s girl, warm honey skin, determined yet gentle eyes, dark green áo dài with lotus pattern, bold red lip, windswept loose hair, countryside sunset golden light",
            "dreamy beautiful 1960s girl, fresh dewy no-makeup look, bright surprised expression, simple cotton áo bà ba in light blue, natural beauty, hair in single braid with wildflower, riverside morning mist",
        ],
        "70s": [
            "dreamy beautiful 1970s girl, warm sun-kissed skin, gentle carefree smile, bohemian floral maxi dress, natural 70s makeup, feathered flowing hair, golden countryside sunset light",
            "dreamy beautiful 1970s girl, soft dewy complexion, wistful distant gaze, áo bà ba in earthy brown, fresh natural face, loose wavy hair to shoulders, misty rice paddy morning light",
            "dreamy beautiful 1970s girl, honey-toned glow, serene peaceful expression, cream crochet top with flared pants, minimal makeup with glossy lips, long straight center-parted hair, warm kerosene lamp glow",
            "dreamy beautiful 1970s girl, radiant tan skin, playful laughing eyes, orange floral blouse with bell-bottoms, rosy natural blush, feathered bangs with headband, bright open-air market sunshine",
            "dreamy beautiful 1970s girl, pale delicate skin, melancholic teary look, simple white cotton dress, bare-faced natural beauty, long hair in loose low ponytail, rainy window soft grey light",
            "dreamy beautiful 1970s girl, warm amber complexion, shy blushing half-smile, sage green áo bà ba with straw hat, sun-freckled cheeks, messy windblown hair, bamboo grove dappled sunlight",
            "dreamy beautiful 1970s girl, luminous fair skin, dreamy unfocused gaze, vintage lavender peasant blouse, soft pink lip tint, flower crown in flowing hair, wildflower meadow golden hour",
            "dreamy beautiful 1970s girl, golden-lit face, confident bright smile, rust-colored wrap dress, bold 70s eye makeup, voluminous bouncy curls, disco-era warm spotlight glow",
            "dreamy beautiful 1970s girl, cool porcelain complexion, contemplative reading expression, beige knit turtleneck, wire-rim round glasses, straight hair tucked behind ears, bookshop afternoon window light",
            "dreamy beautiful 1970s girl, rosy warm skin, tearful yet smiling expression, faded blue denim jacket over white dress, no makeup natural face, windblown hair with dried flowers, riverside farewell sunset",
        ],
        "80s": [
            "dreamy beautiful 1980s girl, radiant glowing skin, confident bright smile, bold shoulder-pad blouse in electric pink, vivid colorful makeup, voluminous permed curly hair, neon sign warm glow",
            "dreamy beautiful 1980s girl, soft dewy complexion, wistful gentle gaze, pastel mint blouse with ruffled collar, bright eyeshadow and blush, big teased wavy hair, vintage TV screen blue light",
            "dreamy beautiful 1980s girl, warm honey skin, playful wink expression, red polka-dot dress with puff sleeves, bold red lips, curly permed bob with side-swept bangs, retro diner warm lighting",
            "dreamy beautiful 1980s girl, porcelain fair face, shy dimpled smile, cream lace blouse tucked into high-waist jeans, subtle rosy makeup, long straight hair with big bow clip, bedroom poster wall soft lamp",
            "dreamy beautiful 1980s girl, golden sun-kissed glow, carefree laughing expression, oversized denim jacket with patches, fresh sporty look, high ponytail with scrunchie, outdoor basketball court sunset",
            "dreamy beautiful 1980s girl, luminous pale skin, mysterious half-smile, black off-shoulder sweater with gold necklace, smoky dramatic eye makeup, voluminous side-parted waves, nightclub colored disco light",
            "dreamy beautiful 1980s girl, warm rosy cheeks, tender loving gaze, floral print dress with peter-pan collar, natural blush and lip gloss, neat bob with curled ends, family kitchen warm yellow light",
            "dreamy beautiful 1980s girl, clear bright complexion, surprised innocent wide eyes, school uniform white shirt with ribbon tie, minimal fresh makeup, twin ponytails with colorful elastics, classroom morning sunlight",
            "dreamy beautiful 1980s girl, tanned healthy glow, determined fierce expression, sporty aerobics leotard with leg warmers, bold 80s workout makeup, headband in crimped hair, gym mirror fluorescent light",
            "dreamy beautiful 1980s girl, delicate pale features, melancholic teary beauty, vintage silk cheongsam in dusty rose, classic red lip, elegant finger-wave retro hairstyle, old photo studio warm spotlight",
        ],
        "90s": [
            "dreamy beautiful 1990s girl, flawless dewy skin, gentle shy smile, simple white t-shirt with denim overalls, thin 90s eyebrows with glossy lips, straight hair with butterfly clips, café afternoon warm light",
            "dreamy beautiful 1990s girl, luminous glass skin, wistful gaze out window, pastel cardigan over slip dress, frosted pink lip gloss, blunt-cut bob with side part, rainy city street neon reflections",
            "dreamy beautiful 1990s girl, warm natural glow, bright cheerful laugh, plaid flannel shirt tied at waist, minimal grunge makeup, messy loose waves with bandana headband, school rooftop golden hour",
            "dreamy beautiful 1990s girl, porcelain complexion, serene peaceful expression, simple white áo dài modernized, natural nude makeup, long straight silky black hair, temple garden morning mist",
            "dreamy beautiful 1990s girl, honey-toned skin, playful tongue-out wink, colorful crop top with high-waist jeans, sparkly eye glitter, twin space buns with loose strands, karaoke room colorful lights",
            "dreamy beautiful 1990s girl, soft rosy face, melancholic teary half-smile, oversized boyfriend blazer, dark outlined lips 90s style, curtain bangs framing face, empty bus stop evening blue light",
            "dreamy beautiful 1990s girl, clear bright skin, curious wide-eyed look, baby blue spaghetti strap top, subtle shimmer eyeshadow, straight hair clipped with claw clip, internet café CRT monitor glow",
            "dreamy beautiful 1990s girl, golden warm complexion, confident gentle smile, black turtleneck with silver pendant, matte berry lips, sleek low ponytail, bookstore warm reading lamp",
            "dreamy beautiful 1990s girl, fresh dewy face, shy blushing expression, floral sundress with cardigan, natural no-makeup look, half-up hair with ribbon, cherry blossom park dappled sunlight",
            "dreamy beautiful 1990s girl, pale moonlit skin, dreamy distant gaze, vintage band t-shirt with choker necklace, smudged eyeliner, messy bedhead waves, bedroom string lights soft glow",
        ],
        "2000s": [
            "dreamy beautiful Y2K girl, radiant glass skin, bright excited smile, baby pink halter top with low-rise jeans, glossy lip gloss and shimmer eyeshadow, flat-ironed straight hair, shopping mall bright lights",
            "dreamy beautiful Y2K girl, luminous dewy complexion, wistful soft gaze, white camisole with butterfly embroidery, peach blush and clear gloss, loose beach waves with face-framing layers, sunset rooftop warm light",
            "dreamy beautiful Y2K girl, warm honey glow, playful peace-sign pose, colorful graphic tee with mini skirt, sparkly butterfly clips in hair, chunky highlights blonde streaks, photo booth flash light",
            "dreamy beautiful Y2K girl, porcelain fair skin, serene gentle expression, pastel velour tracksuit, soft pink monochrome makeup, sleek ponytail with tendril bangs, early morning yoga studio light",
            "dreamy beautiful Y2K girl, fresh natural face, shy dimpled smile, denim jacket covered in pins and patches, bare minimal makeup, messy side braid, indie coffee shop afternoon warmth",
            "dreamy beautiful Y2K girl, golden sun-kissed skin, carefree laughing expression, boho crochet top with flared jeans, bronzer glow and nude lip, long tousled wavy hair, music festival sunset golden haze",
            "dreamy beautiful Y2K girl, cool-toned clear skin, mysterious half-smile, black mesh top over tank top, smoky dark eye makeup, pin-straight jet black hair, nightclub UV purple light",
            "dreamy beautiful Y2K girl, soft rosy complexion, tender emotional expression, vintage band hoodie oversized, dewy no-makeup makeup, messy bun with chopstick through it, dorm room desk lamp glow",
            "dreamy beautiful Y2K girl, bright healthy glow, confident bright grin, sporty polo shirt with pleated mini skirt, fresh preppy makeup, high ponytail with ribbon, school campus cherry blossom sunshine",
            "dreamy beautiful Y2K girl, delicate pale features, tearful bittersweet beauty, silk slip dress in champagne gold, glossy teary eyes with shimmer, elegant loose curls pinned on one side, prom night warm ballroom light",
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

    # ── Beauty pool: mỗi scene chọn cô gái KHÁC NHAU từ pool ──────
    # Luôn dùng beauty pool làm nhân vật chính — đảm bảo đa dạng gương mặt.
    # character_desc (từ scenes.json) chỉ bổ sung trang phục/era, KHÔNG override khuôn mặt.
    if use_character:
        if era == "thap-nien":
            dec = decade or "default"
            char_pool = _BEAUTY_CHARS["thap-nien"].get(dec, _BEAUTY_CHARS["thap-nien"]["default"])
        else:
            char_pool = _BEAUTY_CHARS.get(era, _BEAUTY_CHARS["co-trang"])
        beauty_desc = char_pool[scene_index % len(char_pool)]
        # Beauty pool = nhân vật chính — mỗi index là một cô gái khác hoàn toàn
        char = f"{beauty_desc}, DIFFERENT UNIQUE PERSON"
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

    # Ghép prompt: nhân vật/scene ĐẶT ĐẦU TIÊN để FLUX ưu tiên,
    # negative + anatomy + brand suffix đặt sau
    if use_character:
        # Ảnh có người: character description phải ở đầu prompt để FLUX tạo gương mặt khác nhau
        full_prompt = f"{prompt_raw}, {anatomy_suffix}, {brand_suffix}, {NEGATIVE_PREFIX}"
    else:
        # Ảnh cảnh/vật: negative prefix ở đầu vẫn ok
        full_prompt = f"{NEGATIVE_PREFIX}{prompt_raw}, {anatomy_suffix}, {brand_suffix}"

    # NSFW fallback — chỉ check prompt_raw (không check NEGATIVE_PREFIX vì nó chứa "bare skin" etc.)
    if not is_safe_prompt(prompt_raw):
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
    has_character: bool = False,
) -> Image.Image:
    """
    Generate ảnh từ FLUX.1-schnell.

    Args:
        prompt:        Text prompt đã được xử lý
        headers:       {"Authorization": "Bearer hf_..."}
        ratio:         "9:16" | "16:9" | "1:1"
        seed:          Seed cố định → giữ style nhất quán giữa các scene cùng truyện
        has_character: True nếu ảnh có nhân vật → tăng inference steps để tạo gương mặt rõ nét hơn

    Returns:
        PIL Image object
    """
    width, height = SIZES.get(ratio, SIZES["9:16"])

    # Rút token từ header "Authorization: Bearer ..." để pass vào InferenceClient.
    auth = headers.get("Authorization", "") if headers else ""
    api_token = auth[7:] if auth.startswith("Bearer ") else auth

    return generate_flux_image(
        prompt,
        api_token=api_token,
        width=width,
        height=height,
        num_inference_steps=12 if has_character else 8,
        guidance_scale=3.5 if has_character else 0.0,
        seed=seed,
    )


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
    # Ảnh có nhân vật → tăng steps + guidance để FLUX tạo gương mặt rõ nét & khác biệt
    _CHARACTER_SHOTS = {"close_up", "medium", "action", "two_shot", "back_view"}
    image = generate_image(prompt, headers, ratio=ratio, seed=seed,
                           has_character=(shot_type in _CHARACTER_SHOTS))
    return image, prompt
