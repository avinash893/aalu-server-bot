# 🤖 Tillu — Smart AI Co-Host & Minecraft Community Manager

Tillu is an autonomous, witty Hinglish AI co-host and Discord community manager. Powered by **NVIDIA AI** (with auto-rolling API keys) and **Groq fallback**, Tillu handles Minecraft server operations, self-service whitelisting, live server telemetry, and Discord administration.

---

## ⚡ Features

- 🎭 **Dual-Tone Hinglish AI**: Casual banter, meme culture, and humor for chat; sharp, professional execution for admin tasks.
- 🚀 **High-Speed AI Architecture**: Powered by NVIDIA API with automatic 5–10 use rolling keys and instant Groq fallback.
- 🎮 **Minecraft Telemetry & Controls**: Real-time status ping, player count display, remote server start via Pterodactyl API, and self-service player whitelisting.
- 🧠 **Persistent Cloud Memory**: Learns rules, facts, and moderation preferences with continuous GitHub cloud synchronization.
- 🛡️ **Autonomous Discord Actions**: Give/remove roles, kick/ban members, create channels, and enforce custom server rules via natural language.

---

## 📖 Usage

### 1. Chatting with Tillu
You can talk to Tillu anywhere in your server:
- Mention `@Tillu` or simply type `tillu <your message>` in chat.
- Ask questions about the Minecraft server, request a whitelist, or chat naturally in Hinglish.
- Tillu automatically detects intent and executes actions or answers questions.

### 2. Slash Commands

| Command | Description | Permission |
| :--- | :--- | :--- |
| `/start` | Starts the Minecraft server via Pterodactyl API | Everyone |
| `/status` | Shows live server status, TPS, and player count | Everyone |
| `/whitelist <ign>` | Adds your Minecraft username to the whitelist | Everyone |
| `/ask <query>` | Asks Tillu anything about the server or SMP | Everyone |
| `/tts <message>` | Makes Tillu speak out loud via Discord TTS | Everyone |
| `/remember <fact>` | Teaches Tillu a rule or fact to remember | Admin / Mod |
| `/memories` | Displays all learned facts and server rules | Everyone |
| `/console <cmd>` | Executes a command on the server console | Admin / Mod |
| `/ban <player>` | Bans a player from the Minecraft server | Admin / Mod |
| `/unban <player>` | Unbans a player from the Minecraft server | Admin / Mod |
| `/unwhitelist <ign>` | Removes a player from the whitelist | Admin / Mod |
| `/tag <target> <msg>` | Tags a user or role with a message | Admin / Mod |
| `/listbots` | Lists all other active bots in the server | Everyone |
| `/help` | Displays help menu with all available commands | Everyone |

### 3. Natural Language Actions
Admins can speak naturally to Tillu in chat:
- *"Give Member role to @user"*
- *"Tillu, check kitne players online hain"*
- *"Whitelist player Alex"*
- *"Server start kar do"*

---

## ➕ How to Add Tillu to Your Own Server

### Option A: 1-Click Bot Invite (Recommended)
Add the hosted Tillu bot directly to your Discord server:

1. Click the **[Invite Tillu to Your Server](https://discord.com/api/oauth2/authorize?client_id=1530717587212603402&permissions=8&scope=bot%20applications.commands)** link.
2. Select your Discord server from the dropdown.
3. Keep the requested permissions checked (Administrator or Bot + Manage Roles + Send Messages).
4. Click **Authorize**.
5. Move the `Tillu` role above the roles it needs to manage in **Server Settings > Roles**.

---

### Option B: Self-Host Your Own Instance

#### 1. Clone the Repository
```bash
git clone https://github.com/avinash893/aalu-server-bot.git
cd aalu-server-bot
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Configure `.env`
Create a `.env` file in the project root:
```env
# Discord Configuration
BOT_TOKEN=your_discord_bot_token_here

# AI Engines (NVIDIA Primary + Groq Fallback)
NVIDIA_API_KEYS=nvapi-key1,nvapi-key2,nvapi-key3
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3

# Minecraft & Pterodactyl Integration
SERVER_HOST=your.server.ip
SERVER_PORT=25565
PTERO_URL=https://panel.example.com
PTERO_API_KEY=ptlc_your_client_api_key
PTERO_SERVER_ID=your_server_uuid

# GitHub Auto-Sync (Optional - for persistent cloud memory)
GITHUB_TOKEN=ghp_your_github_token
GITHUB_REPO=your_username/your_repo
```

#### 4. Run the Bot
```bash
python bot.py
```

#### 5. 24/7 Hosting (Free on Wispbyte)
1. Create a free **Python** server on [Wispbyte](https://wispbyte.com).
2. Upload the project files and extract them.
3. Select `bot.py` as the main entry file.
4. Click **Start** in the console.
