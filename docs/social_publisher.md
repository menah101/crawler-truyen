# Social Publisher — Chia sẻ truyện lên MXH tự động

Module: `social_publisher.py`

Đăng thông tin truyện (tiêu đề, mô tả, ảnh bìa, URL, hashtag) đồng thời lên nhiều kênh MXH. Mỗi adapter kiểm tra cấu hình riêng, thiếu key thì **tự skip** không fail toàn bộ.

## Platform hỗ trợ

| Adapter | Method | Yêu cầu cấu hình | Cần cover_url public? |
|---------|--------|------------------|-----------------------|
| **Telegram** | Bot API | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | — (upload file) |
| **Discord** | Webhook | `DISCORD_WEBHOOK_URL` | — (upload file) |
| **X (Twitter)** | API v2 + OAuth 1.0a | 4 key + `pip install tweepy` | — (upload file) |
| **Facebook Page** | Graph API v19.0 | `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN` | — (upload file) |
| **Instagram** | Graph API 2-step | `INSTAGRAM_USER_ID` + FB page token | ✅ **bắt buộc** |
| **Pinterest** | API v5 | `PINTEREST_ACCESS_TOKEN`, `PINTEREST_BOARD_ID` | ✅ **bắt buộc** |

Facebook Group đăng qua **n8n workflow + Puppeteer fallback** — xem § [Facebook Group](#facebook-group-qua-n8n).

## Cấu hình `.env`

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-1001234567890      # âm cho channel/supergroup

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/.../xxx
DISCORD_USERNAME=Hồng Trần Truyện

# X (Twitter)
TWITTER_CONSUMER_KEY=
TWITTER_CONSUMER_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_TOKEN_SECRET=

# Facebook Fanpage (Graph API v19.0)
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=              # long-lived Page Token

# Instagram Business (dùng cùng Page Access Token ở trên)
INSTAGRAM_USER_ID=                       # lấy từ Graph API Explorer

# Pinterest (API v5)
PINTEREST_ACCESS_TOKEN=
PINTEREST_BOARD_ID=
```

### Setup Telegram bot (5 phút)
1. Nhắn `@BotFather` → `/newbot` → đặt tên → nhận **TOKEN**.
2. Add bot vào channel/group, cấp quyền **Post Messages**.
3. Gửi thử 1 tin, rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id`.

### Setup Discord webhook (1 phút)
Server Settings → Integrations → Webhooks → **New Webhook** → copy URL.

### Setup X developer
1. Đăng ký app tại [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard).
2. Permissions: **Read and Write**.
3. Tab **Keys and tokens** → lấy đủ 4 key.

### Setup Facebook Page token (phức tạp nhất ~15 phút)
1. Tạo Facebook App tại [developers.facebook.com/apps](https://developers.facebook.com/apps/) → type **Business**.
2. Add product **Facebook Login for Business**.
3. Vào [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
   - Chọn app → User Token → chọn Page của bạn.
   - Grant các permission: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`.
   - Copy token — nhưng đây là **short-lived** (1 giờ).
4. Đổi sang **long-lived page token** (60 ngày, tự refresh):
   ```bash
   # Bước 1: short-lived user → long-lived user
   curl "https://graph.facebook.com/v19.0/oauth/access_token?\
grant_type=fb_exchange_token&client_id=APP_ID&\
client_secret=APP_SECRET&fb_exchange_token=SHORT_USER_TOKEN"

   # Bước 2: long-lived user → long-lived page
   curl "https://graph.facebook.com/v19.0/me/accounts?access_token=LONG_USER_TOKEN"
   # Response chứa page access_token — đây là token dùng mãi
   ```
5. `FACEBOOK_PAGE_ID`: Page → About → Page ID (hoặc trong response bước 2).

### Setup Instagram (yêu cầu: đã setup FB Page ở trên)
1. IG account phải là **Business** hoặc **Creator** (settings → switch account type).
2. Link IG với FB Page: Instagram → Settings → Business → Page Connection.
3. Token FB Page cần thêm scope: `instagram_basic`, `instagram_content_publish`.
4. Lấy `INSTAGRAM_USER_ID`:
   ```bash
   curl "https://graph.facebook.com/v19.0/PAGE_ID?\
fields=instagram_business_account&access_token=PAGE_TOKEN"
   # Response: {"instagram_business_account": {"id": "17841400..."}}
   ```

### Setup Pinterest
1. Developer dashboard: [developers.pinterest.com/apps](https://developers.pinterest.com/apps/).
2. Tạo app → OAuth scopes `pins:write`, `boards:read`.
3. Generate access token qua OAuth flow (Pinterest không có "test token" như FB).
4. `BOARD_ID`: mở board trên web, URL dạng `pinterest.com/username/board-name/` — gọi `GET /v5/boards` để lấy ID.

## Dùng qua `run.py`

```bash
# Đăng lên tất cả adapter đã cấu hình
python run.py --social-publish docx_output/2026-04-19/ten-truyen

# Chỉ đăng Telegram + Discord
python run.py --social-publish docx_output/.../ten-truyen --social-only telegram,discord

# Dry run — preview không đăng thật
python run.py --social-publish docx_output/.../ten-truyen --social-dry-run
```

## Dùng standalone

```bash
# Từ thư mục truyện (tự parse seo.txt + cover)
python social_publisher.py --from-dir docx_output/2026-04-19/ten-truyen

# Custom manual
python social_publisher.py \
  --title "Âm Thanh Trong Tiếng Mưa" \
  --url "https://hongtrantruyen.net/truyen/am-thanh-trong-tieng-mua" \
  --cover cover.jpg \
  --description "Một đêm mưa, cái bóng lạ đứng trên mái nhà đối diện..." \
  --hashtags "#truyenma #audiostory"

# Chỉ một số adapter
python social_publisher.py --from-dir ... --only telegram,discord

# Không đăng thật
python social_publisher.py --from-dir ... --dry-run
```

## Dùng như module Python

```python
from social_publisher import NovelPayload, publish_to_all

payload = NovelPayload(
    title="Âm Thanh Trong Tiếng Mưa",
    url="https://hongtrantruyen.net/truyen/am-thanh-trong-tieng-mua",
    description="Một đêm mưa, cái bóng lạ đứng trên mái nhà đối diện...",
    cover_path="/path/to/cover.jpg",
    hashtags=["#truyenma", "#audiostory"],
)

results = publish_to_all(payload, only=['telegram', 'discord'])
# results = {
#   'telegram': {'ok': True, 'message_id': 42},
#   'discord':  {'ok': True},
# }
```

## Auto-detect từ seo.txt

Khi dùng `--from-dir`, publisher tự đọc `seo.txt` với các section:

```
=== TIÊU ĐỀ YOUTUBE ===
1. Âm Thanh Trong Tiếng Mưa - Tập 1
2. ...

=== MÔ TẢ ===
Một đêm mưa, cái bóng lạ...

=== HASHTAG ===
#truyenma #audiostory #hongtran
```

Quy tắc:
- **Title**: dòng đầu tiên của `TIÊU ĐỀ YOUTUBE`, tự bỏ prefix "Truyện Audio" và suffix "| ...".
- **Cover**: ưu tiên `cover.jpg` → `cover.png` → `thumbnail_youtube.jpg` → ảnh đầu tiên trong `thumbnails/`.
- **URL**: `{SITE_URL}/truyen/<slug>` — slug lấy từ tên thư mục.

## Format tự động theo platform

| Platform | Giới hạn | Cách xử lý |
|----------|----------|-----------|
| Telegram | caption 1024 | Truncate với `…` ở cuối, HTML bold title |
| Discord | embed description 4096 | Truncate, embed có title + link + image |
| X (Twitter) | tweet 280 | Ưu tiên title + URL (URL rút gọn t.co 23 ký tự) |
| Facebook Page | post 5000 | Nếu có cover → `/photos` upload; không có → `/feed` + link (auto OG preview) |
| Instagram | caption 2200, 30 hashtag | Chỉ ảnh + caption, URL để "link ở bio" |
| Pinterest | title 100, description 800 | Pin = ảnh + title + description + link |

## cover_url (quan trọng cho IG/Pinterest)

IG và Pinterest **không cho upload file trực tiếp** — bắt buộc phải có URL public HTTPS:

**Tự động lookup từ DB** (khi dùng `--from-dir`): publisher query `Novel.coverImage` theo slug:
- URL absolute (`https://...`) → dùng as-is (VD: Cloudinary).
- Path tương đối (`/images/covers/xxx.jpg`) → prefix với `SITE_URL`.
- Nếu DB không có → `cover_url` trống → IG/Pinterest skip với lỗi rõ ràng.

**Override thủ công**:
```bash
python social_publisher.py --from-dir ... \
  --cover-url "https://hongtrantruyen.net/images/covers/ten-truyen.jpg"
```

## Hành vi

- Adapter thiếu key → `skipped: True, reason: "not configured"` (không fail).
- `tweepy` chưa cài → adapter Twitter báo lỗi nhưng không crash các adapter khác.
- Upload ảnh lỗi (network, file không tồn tại) → tự fallback về text-only.
- Exit code `0` nếu tất cả OK, `1` nếu có adapter fail (dùng trong CI).

## Gợi ý workflow

```bash
# 1. Crawl + tạo nội dung
python run.py --url "URL" --seo --images

# 2. Tạo cover + thumbnail
python run.py --cover-from-dir docx_output/YYYY-MM-DD/ten-truyen
python thumbnail_generator.py docx_output/YYYY-MM-DD/ten-truyen

# 3. Đăng MXH
python run.py --social-publish docx_output/YYYY-MM-DD/ten-truyen --social-dry-run  # preview
python run.py --social-publish docx_output/YYYY-MM-DD/ten-truyen                    # đăng thật
```

## Ví dụ end-to-end

Kịch bản: crawl 1 truyện mới, rewrite, tạo cover, import DB, publish trên web, để watcher tự đăng MXH.

### Bước 0 — Cấu hình 1 lần

```bash
cd crawler
cp .env.example .env
# Mở .env điền: TELEGRAM_BOT_TOKEN, DISCORD_WEBHOOK_URL, TWITTER_*, FACEBOOK_*, INSTAGRAM_*, PINTEREST_*
# Các platform chưa có key sẽ tự skip, không cần điền hết cùng lúc.
pip install -r requirements.txt  # tweepy cho X, python-dotenv, requests
```

Kiểm tra adapter nào sẵn sàng:

```bash
python -c "from social_publisher import ADAPTERS; \
print([c().name for c in ADAPTERS if c().is_configured()])"
# Output ví dụ: ['telegram', 'discord', 'facebook_page']
```

### Bước 1 — Crawl truyện mới

```bash
python run.py --url "https://truyenfull.vn/am-thanh-trong-tieng-mua/" \
              --max-chapters 20 \
              --seo --images
```

Tạo ra:

```
docx_output/2026-04-19/am-thanh-trong-tieng-mua/
├── chapters/
│   ├── 0001.json
│   ├── 0002.json
│   └── ...
├── seo.txt                  # title + description + hashtag
├── cover.jpg                # từ --images
└── thumbnails/
```

### Bước 2 — Rewrite để né trùng lặp (tuỳ chọn)

```bash
# Rewrite tất cả chương, tự backup
python run.py --rewrite-from-dir docx_output/2026-04-19/am-thanh-trong-tieng-mua

# Rewrite chỉ chương 1, 5, 10
python run.py --rewrite-from-dir docx_output/2026-04-19/am-thanh-trong-tieng-mua \
              --rewrite-chapter 1 5 10
```

### Bước 3 — Tạo cover đẹp (nếu muốn thay cover auto-crawl)

```bash
python run.py --cover-from-dir docx_output/2026-04-19/am-thanh-trong-tieng-mua
```

### Bước 4 — Import vào DB Next.js

Giả sử Next.js đã có route import — crawler ghi thẳng vào Prisma SQLite (xem `db_helper.py`). Sau khi import:

```sql
-- SELECT slug, title, publishStatus, coverImage FROM Novel WHERE slug = 'am-thanh-trong-tieng-mua';
-- am-thanh-trong-tieng-mua | Âm Thanh Trong Tiếng Mưa | draft | /images/covers/am-thanh-trong-tieng-mua.jpg
```

### Bước 5 — Preview MXH trước khi publish

```bash
python run.py --social-publish docx_output/2026-04-19/am-thanh-trong-tieng-mua \
              --social-dry-run
```

Output mẫu:

```
[telegram] DRY RUN caption:
📖 Truyện mới: Âm Thanh Trong Tiếng Mưa
Một đêm mưa, cái bóng lạ đứng trên mái nhà...
👉 https://hongtrantruyen.net/truyen/am-thanh-trong-tieng-mua
#truyenma #audiostory
[discord]  DRY RUN embed: title=..., image=cover.jpg
[twitter]  DRY RUN tweet (247/280 chars)
[facebook_page] DRY RUN photo upload
[instagram] SKIP: cover_url missing (Novel.coverImage không có trong DB)
[pinterest] SKIP: cover_url missing
```

→ Sửa `coverImage` trong DB cho đầy đủ URL public, preview lại.

### Bước 6 — Publish truyện trên web

Trong Next.js admin, đổi `publishStatus` từ `draft` → `published`. Prisma update:

```sql
UPDATE Novel SET publishStatus='published', createdAt=CURRENT_TIMESTAMP WHERE slug='am-thanh-trong-tieng-mua';
```

### Bước 7 — Watcher tự đăng MXH

**Cách A — cron/systemd đã chạy từ trước** (xem § Auto-watcher):

Watcher poll mỗi 5 phút, phát hiện slug mới `published` trong 48h qua, tự đăng. Không cần làm gì thêm.

```bash
tail -f crawler/logs/watcher.log
# 10:05:00 INFO 🔍 Tìm thấy 1 truyện published trong 48h qua
# 10:05:01 INFO 📣 am-thanh-trong-tieng-mua: đăng lên ['discord', 'facebook_page', 'telegram']
# 10:05:03 INFO [telegram] ✓ message_id=142
# 10:05:05 INFO [discord]  ✓
# 10:05:09 INFO [facebook_page] ✓ post_id=109876...
```

**Cách B — chạy 1 lần tay**:

```bash
python social_watcher.py --slug am-thanh-trong-tieng-mua
# Hoặc quét mọi truyện mới:
python social_watcher.py --once
```

**Cách C — webhook từ Next.js**: publish action gọi trực tiếp:

```ts
// app/admin/novels/[slug]/publish/route.ts
await prisma.novel.update({ where: { slug }, data: { publishStatus: 'published' } });
execFile('python3', ['crawler/social_watcher.py', '--slug', slug], { detached: true });
```

### Bước 8 — Kiểm tra kết quả

```bash
cat crawler/social_log.json
```

```json
{
  "am-thanh-trong-tieng-mua": {
    "telegram":      {"status":"ok","posted_at":"2026-04-19T10:05:03","message_id":142},
    "discord":       {"status":"ok","posted_at":"2026-04-19T10:05:05"},
    "facebook_page": {"status":"ok","posted_at":"2026-04-19T10:05:09","post_id":"109876..."},
    "instagram":     {"status":"failed","posted_at":"2026-04-19T10:05:11","error":"cover_url missing"},
    "twitter":       {"status":"ok","posted_at":"2026-04-19T10:05:13","tweet_id":"18234..."}
  }
}
```

### Bước 9 — Retry platform fail

Sửa lỗi (VD: điền `coverImage` vào DB cho Instagram), watcher vòng sau tự retry các platform `failed` — nó chỉ skip khi `status=ok`.

Force đăng lại toàn bộ (bỏ qua log):

```bash
python social_watcher.py --slug am-thanh-trong-tieng-mua --force
```

### Bước 10 — Thêm Facebook Group (qua n8n)

Sau khi watcher đã đăng 5 platform, gọi thêm webhook n8n cho FB Group:

```bash
curl -X POST http://localhost:5678/webhook/publish-novel \
  -H 'Content-Type: application/json' \
  -d '{
    "slug": "am-thanh-trong-tieng-mua",
    "title": "Âm Thanh Trong Tiếng Mưa",
    "description": "Một đêm mưa...",
    "url": "https://hongtrantruyen.net/truyen/am-thanh-trong-tieng-mua",
    "cover_url": "https://hongtrantruyen.net/images/covers/am-thanh-trong-tieng-mua.jpg",
    "hashtags": ["#truyenma", "#audiostory"]
  }'
```

Tích hợp vào watcher: sửa `social_watcher.process_slug` thêm `requests.post(N8N_WEBHOOK, json={...})` sau `publish_to_all`.

### Sơ đồ tổng thể

```
┌──────────────┐   crawl     ┌─────────────────────┐
│  truyenfull  │────────────▶│ docx_output/.../    │
└──────────────┘             │ chapters + seo.txt  │
                             └──────────┬──────────┘
                                        │ rewrite + cover
                                        ▼
                             ┌─────────────────────┐
                             │   Prisma SQLite     │
                             │  Novel.publishStatus│
                             └──────────┬──────────┘
                                        │ publish (UI admin)
                                        ▼
                    ┌───────────────────────────────────────┐
                    │  social_watcher.py (cron/daemon)      │
                    └───────┬────────────────────┬──────────┘
                            │                    │
            ┌───────────────┼──────┬──────┬──────┼──────────┐
            ▼               ▼      ▼      ▼      ▼          ▼
        Telegram       Discord    X    FB Page  IG     Pinterest
                                                          │
                                                          │ webhook n8n
                                                          ▼
                                                  Facebook Group
                                                 (Graph API hoặc
                                                  Puppeteer fallback)
```

## Auto-watcher — đăng tự động khi có truyện publish

Module: `social_watcher.py`

Poll DB tìm truyện `publishStatus='published'` mới → gọi `publish_to_all` cho mỗi slug → ghi log để không đăng trùng.

```bash
# 1 lần (cho cron)
python social_watcher.py --once

# Daemon — poll mỗi 5 phút
python social_watcher.py --interval 300

# Đăng lại 1 truyện bỏ qua log
python social_watcher.py --force --slug ten-truyen

# Chỉ 1 số platform
python social_watcher.py --once --only telegram,discord

# Nhìn lại 7 ngày thay vì 48h mặc định
python social_watcher.py --once --hours 168
```

Hoặc gọi qua `run.py`:

```bash
python run.py --social-watch                    # 1 lần
python run.py --social-watch-daemon 300         # daemon poll 5 phút
python run.py --social-watch --social-watch-hours 168
```

### Cron recipe (Linux/macOS)

```cron
# Mỗi 10 phút quét truyện mới trong 48h qua
*/10 * * * * cd /path/to/crawler && /usr/bin/python3 social_watcher.py --once >> logs/watcher.log 2>&1
```

### systemd service (Linux)

```ini
# /etc/systemd/system/social-watcher.service
[Unit]
Description=Hong Tran Truyen social watcher
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/opt/truyen-web/crawler
ExecStart=/usr/bin/python3 social_watcher.py --interval 300
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now social-watcher
journalctl -u social-watcher -f
```

### Wire Next.js `publish` action → watcher

Hai lựa chọn:

**(a) Pull model (đơn giản, khuyên dùng)** — không cần Next.js biết gì. Watcher chạy định kỳ, tự phát hiện `publishStatus` chuyển thành `published` trong `--hours` window.

**(b) Push model (gần real-time)** — Next.js publish action gọi webhook. Ví dụ trong route handler sau khi update DB:

```ts
// app/admin/novels/[slug]/publish/route.ts (đơn giản hoá)
await prisma.novel.update({ where: { slug }, data: { publishStatus: 'published' } });
// Fire-and-forget — spawn subprocess watcher cho 1 slug
execFile('python3', ['crawler/social_watcher.py', '--slug', slug], { detached: true });
```

Hoặc nếu dùng n8n làm hub: Next.js `POST http://n8n:5678/webhook/publish-novel` với payload — xem § Facebook Group bên dưới.

## Log & chống đăng trùng — `social_log.json`

Module: `social_log.py`  
File: `crawler/social_log.json` (thread-safe, atomic write qua `.tmp`).

Schema:

```json
{
  "ten-truyen-slug": {
    "telegram": {
      "status": "ok",
      "posted_at": "2026-04-19T10:20:00",
      "message_id": 42
    },
    "discord":  { "status": "ok", "posted_at": "..." },
    "twitter":  {
      "status": "failed",
      "posted_at": "...",
      "error": "403: duplicate content"
    }
  }
}
```

`status` là 1 trong `ok | skipped | failed`. Watcher chỉ skip khi `ok`; `failed` sẽ được thử lại vòng poll kế tiếp.

**Reset 1 truyện** (để đăng lại tất cả platform):

```python
import social_log
social_log.reset_slug('ten-truyen')
```

Hoặc xoá tay entry trong JSON, hoặc dùng `--force` khi chạy watcher.

## Facebook Group (qua n8n)

Graph API cho Groups deprecated 2020, Meta không còn approve permission `publish_to_groups` cho app mới. Workflow:

```
Next.js publish  ──▶  webhook /publish-novel (n8n)
                       │
                       ├─▶ Facebook Graph API node (nếu app được Meta approve)
                       └─▶ HTTP Request → Puppeteer microservice (fallback)
```

### 1. Cài đặt n8n

```bash
# Docker (khuyên dùng)
docker run -d --name n8n -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n n8nio/n8n

# Hoặc npm
npm install -g n8n
n8n start
```

Mở `http://localhost:5678` → tạo account.

### 2. Import workflow template

- File: `crawler/n8n/facebook_group_workflow.json`
- n8n UI → **Workflows** → **Import from File** → chọn file trên.
- Sửa các placeholder:
  - Node `Facebook Group Post`: thay `YOUR_FACEBOOK_GROUP_ID`.
  - Node `Puppeteer Fallback`: thay `YOUR_GROUP_ID` trong jsonBody.
- Tạo credential **Facebook Graph API** trong n8n (Settings → Credentials) rồi gán cho node FB.

### 3. Gọi từ Next.js/watcher

Watcher hiện không tự gọi n8n — thêm webhook call trong `social_publisher.publish_to_all` hoặc gọi trực tiếp:

```python
import requests
requests.post('http://localhost:5678/webhook/publish-novel', json={
    'slug': 'ten-truyen',
    'title': 'Âm Thanh Trong Tiếng Mưa',
    'description': '...',
    'url': 'https://hongtrantruyen.net/truyen/ten-truyen',
    'cover_url': 'https://.../cover.jpg',
    'hashtags': ['#truyenma', '#audiostory'],
})
```

### 4. Puppeteer microservice (fallback không dùng Graph API)

Nếu không có Meta-approved app, self-host microservice dùng session cookie. Skeleton:

```js
// services/fb-group-puppeteer/server.js
const express = require('express');
const puppeteer = require('puppeteer');
const app = express();
app.use(express.json());

let browser, page;
(async () => {
  browser = await puppeteer.launch({ headless: 'new', userDataDir: './session' });
  page = await browser.newPage();
  // Lần đầu: chạy với headless=false, login FB manually, session lưu vào ./session
})();

app.post('/post-to-fb-group', async (req, res) => {
  const { group_id, caption, image_url, link } = req.body;
  try {
    await page.goto(`https://www.facebook.com/groups/${group_id}`);
    await page.waitForSelector('[aria-label="Write something"]', { timeout: 10000 });
    await page.click('[aria-label="Write something"]');
    await page.keyboard.type(caption);
    // TODO: upload ảnh từ image_url, click Post
    await page.click('[aria-label="Post"]');
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.listen(3001);
```

⚠️ **Rủi ro**: Facebook có thể ban tài khoản dùng automation. Giải pháp giảm rủi ro:
- Dùng tài khoản phụ chuyên để post (không phải tài khoản chính).
- Random delay 30–120s giữa các post.
- Không post quá 5–10 truyện/ngày.
- User agent + viewport giống thật.

## Roadmap (chưa implement)

| Platform | Cách làm dự kiến |
|---------|-------------------|
| **TikTok** | Content Posting API (v2) — app review cực kỳ khắt khe, thường chỉ approve cho nhà sáng tạo đã verified. |
| **Zalo OA** | Zalo Official Account API — chỉ push được tin nhắn cho follower, không post timeline. |
| **Threads** | API mới (2026), tương tự IG Graph API. Có thể add khi ổn định. |

Khi cần thêm platform, viết class kế thừa `BaseAdapter` (xem pattern trong source):

```python
class NewAdapter(BaseAdapter):
    name = 'new_platform'
    def is_configured(self) -> bool: ...
    def publish(self, payload: NovelPayload) -> dict: ...

ADAPTERS.append(NewAdapter)
```
