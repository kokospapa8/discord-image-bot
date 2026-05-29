# discord-image-bot

Discord bot that searches and returns images/GIFs when @mentioned.

## Owner context

- **kokospapa8** — experienced developer, built discord-song-bot (Python/discord.py) on the same EC2 server
- Prefers concise responses, no trailing summaries
- Uses Korean in Discord, English in code comments is fine
- Same deployment infrastructure as discord-song-bot (AWS EC2 + GitHub Actions + SSM)

## Architecture

```
discord-image-bot/
├── bot.py                  # entry point, loads cogs
├── cogs/
│   └── image_search.py     # main cog: on_message → search → reply
├── utils/                  # shared helpers (add as needed)
├── Dockerfile
├── docker-compose.yml
├── scripts/deploy.sh       # SSM deploy script (same pattern as sister bot)
└── .github/workflows/deploy.yml
```

**Trigger:** Bot responds only when @mentioned. Strips the mention prefix from message content, uses remaining text as search query.

## Deployment

Same EC2 instance as `discord-song-bot`. Independent Docker service at `/home/ubuntu/discord-image-bot/`.

**GitHub Secrets required** (same EC2 secrets as discord-song-bot, add image-bot-specific ones):
| Secret | Source |
|--------|--------|
| `AWS_ACCESS_KEY_ID` | already set |
| `AWS_SECRET_ACCESS_KEY` | already set |
| `AWS_REGION` | already set |
| `EC2_INSTANCE_ID` | already set |
| `DISCORD_TOKEN` | new Discord bot token |
| `DISCORD_CHANNEL_ID` | 업데이트 공지 채널 ID |
| `GIPHY_API_KEY` | Giphy developer dashboard |
| `NAVER_CLIENT_ID` | 네이버 개발자센터 앱 등록 |
| `NAVER_CLIENT_SECRET` | 네이버 개발자센터 앱 등록 |

Deploy: push to `main` → GitHub Actions → SSM → EC2 runs `docker compose up -d`

## Environment variables

See `.env.example`. Never commit `.env` or any file with real credentials.

## APIs to implement

### Giphy (GIF search) — implemented
- Free tier: 1000 req/day
- Docs: https://developers.giphy.com/docs/api/
- Endpoint: `GET https://api.giphy.com/v1/gifs/search?q={query}&api_key={GIPHY_API_KEY}&limit=1`
- Note: Tenor shut down new API clients as of Jan 2026

### Naver Image Search (image search) — implemented
- 25,000 req/day free
- Docs: https://developers.naver.com/docs/serviceapi/search/image/image.md
- Endpoint: `GET https://openapi.naver.com/v1/search/image?query={query}&display=1`
- Headers: `X-Naver-Client-Id`, `X-Naver-Client-Secret`

### Alternatives to consider
- **Reddit API** — free, good quality images for many topics
- **Unsplash API** — 50 req/hr free, high quality photos
- **Giphy API** — free tier available, similar to Tenor

## Key patterns (from sister bot)

```python
# Async HTTP with aiohttp (already in requirements.txt)
async with aiohttp.ClientSession() as session:
    async with session.get(url, params=params) as resp:
        data = await resp.json()

# Reply with embed (image shows inline)
embed = discord.Embed()
embed.set_image(url=image_url)
await message.reply(embed=embed)

# Reply with GIF (just send the URL — Discord auto-embeds)
await message.reply(gif_url)
```

## Security

- `.env`, `data/`, `infra/terraform.tfvars` — NEVER stage or commit
- No other bots' tokens or secrets in this repo

## What's already implemented

- `bot.py` — loads cogs, sets up logging
- `cogs/image_search.py` — on_message listener skeleton (mention detection, content stripping)
- CI/CD pipeline — deploy.yml + deploy.sh ready to use
- Dockerfile + docker-compose.yml

## What needs to be built

1. **Actual search logic** in `cogs/image_search.py` — pick an API and implement
2. **Response formatting** — embed with image, or raw URL for GIF auto-embed
3. **Error handling** — no results found, API key missing, rate limit
4. **(Optional) LLM routing** — use Claude to decide whether to search GIF vs image based on query
5. **(Optional) Multiple results** — show numbered list, user picks one
