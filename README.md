# Tillu — Stream Co-Host & Community Assistant

Tillu is an autonomous Hinglish AI co-host and Discord community manager built for @AALU_CHIPAS. Powered by Google Antigravity, Gemini AI, NVIDIA, and Groq fallback, Tillu handles YouTube live timings, member discovery, public gaming telemetry, inter-bot delegation, and dynamic personality responses.

---

## Features

- Voice Channel AI Co-Host: Joins Discord voice channels to speak live roasts, clutch commentary, and banter using natural Indian TTS.
- Stream Prediction and Betting Economy: Allows viewers to bet virtual Tillu Coins on stream clutches and match predictions with pari-mutuel payouts.
- Viewer Leveling and Loyalty Badges: Rewards active stream watchers and Discord members with XP, levels, rank progress cards, and loyalty badges.
- Dynamic Personality Engine: Switches dynamically between Sarcastic, Funny, Sad Sarcastic, Wholesome, and Savage tones.
- 130+ Meme & Anti-Repetition Vault: Over 130 Bollywood, Desi OTT, gaming, and Gen-Z memes with active anti-phrase loop protection so Tillu never repeats identical starters.
- YouTube Live Tracking: Real-time stream timings and live broadcast detection via the YouTube Data API.
- Member Directory & Tagging: Look up server members by role or name and tag them cleanly in chat.
- Gaming Presence Telemetry: Tracks games played by server members using public Discord activities into an ongoing history.
- Inter-Bot Orchestration: Dispatches commands to other bots in the server (music bots, utilities, moderation).
- Autonomous Daily Self-Audit: Performs 5 daily cycles auditing task success, bot capabilities, and evolution rules synced with GitHub.
- Cloud Memory Diary: Remembers server facts, streamer preferences, and rules with automatic GitHub persistence.

---

## Slash Commands

| Command | Description | Permission |
| :--- | :--- | :--- |
| `/joinvc` | Connects Tillu to your voice channel as AI stream co-host | Everyone |
| `/leavevc` | Disconnects Tillu from the voice channel | Everyone |
| `/speak <text>` | Makes Tillu speak custom text out loud in VC | Everyone |
| `/vcroast [user]` | Roasts a member out loud in voice channel using memes | Everyone |
| `/vchype` | Triggers live stream clutch hype commentary in voice channel | Everyone |
| `/predict <q> <opt_a> <opt_b> [mins]` | Starts a stream prediction event with coin betting | Everyone |
| `/bet <pred_id> <option> <amount>` | Bets Tillu coins on an active prediction | Everyone |
| `/resolveprediction <pred_id> <winner>` | Resolves a prediction and distributes winnings | Admin / Mod |
| `/predictions` | Views active stream predictions and prize pools | Everyone |
| `/coins [@user]` | Checks wallet balance and betting stats | Everyone |
| `/dailycoins` | Claims daily 250 bonus coins | Everyone |
| `/coinboard` | Shows leaderboard of richest coin holders | Everyone |
| `/rank [@user]` | Displays viewer level, XP, badges, and progress | Everyone |
| `/topviewers` | Shows leaderboard of most active chat and voice members | Everyone |
| `/livetiming` | Checks YouTube live stream timings and status for @AALU_CHIPAS | Everyone |
| `/members [role]` | Lists community members with an optional role filter | Everyone |
| `/tagmember <name>` | Finds a member by name/query and mentions them | Everyone |
| `/gamehistory [@user]` | Shows games played by a member based on Discord activity | Everyone |
| `/topgames` | Displays leaderboard of games played across the server | Everyone |
| `/meme [category]` | Drops a fresh Bollywood, Indian gaming, or Desi meme from 130+ vault | Everyone |
| `/memestats` | Shows the category breakdown of Tillu's 130+ meme collection | Everyone |
| `/usebot <command>` | Commands or delegates a task to another bot | Admin / Mod |
| `/mood [mood_name]` | Views or sets Tillu's active personality tone | Everyone / Staff |
| `/status` | Checks Tillu bot health and stream status | Everyone |
| `/ask <query>` | Asks Tillu anything about the community or stream | Everyone |
| `/remember <fact>` | Teaches Tillu a rule or fact to remember | Admin / Mod |
| `/memories` | Displays all learned facts and community rules | Everyone |
| `/audit` | Triggers an immediate self-reflection audit and report | Admin / Mod |
| `/help` | Displays interactive help menu with quick action buttons | Everyone |

---

## Configuration (.env)

```env
# Discord Bot
BOT_TOKEN=your_discord_bot_token

# Streamer / YouTube Tracking
YOUTUBE_API_KEY=your_youtube_data_api_v3_key
YOUTUBE_CHANNEL_ID=UCS__Q82af4iKTPDwDQ19UZQ

# AI Providers
GEMINI_API_KEYS=key1,key2
NVIDIA_API_KEYS=nvapi-key1,nvapi-key2
GROQ_API_KEYS=gsk-key1,gsk-key2

# Antigravity Hybrid Bridge (Optional)
ANTIGRAVITY_PORT=8000
ANTIGRAVITY_TOKEN=optional_token

# GitHub Cloud Sync (for persistent memory diary)
GITHUB_TOKEN=ghp_your_token
GITHUB_REPO=avinash893/aalu-server-bot
```
