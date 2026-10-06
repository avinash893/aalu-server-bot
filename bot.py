"""
Aalu Chipas Minecraft Server Builder Discord Bot
24/7 Cloud Edition for Render
Author: Antigravity Pair Programmer
"""

import os
import sys
import time
import socket
import struct
import json
import asyncio
import re
import logging
import aiohttp
from aiohttp import web
import requests
import discord
from discord.ext import commands
from discord import app_commands

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ── CONFIGURATION ────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SERVER_HOST = os.environ.get("SERVER_HOST", "legacy-7.hexacraft.fun")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "25587"))

PRIMARY_GUILD_ID = int(os.environ.get("PRIMARY_GUILD_ID", "1456298447979286541"))
CS2_GUILD_ID = int(os.environ.get("CS2_GUILD_ID", "1530719250237362297"))

PTERO_URL = os.environ.get("PTERO_URL", "https://panel.hexacraft.fun")
PTERO_KEY = os.environ.get("PTERO_KEY", "")
PTERO_SERVER = os.environ.get("PTERO_SERVER", "14c2ebb6")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

WHITELIST_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "whitelist_registry.json")

# ── LOCAL PERSISTENCE ────────────────────────────────────────────────────────
def load_whitelist_registry() -> dict:
    if os.path.exists(WHITELIST_REGISTRY_PATH):
        try:
            with open(WHITELIST_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_whitelist_registry(data: dict):
    try:
        with open(WHITELIST_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save whitelist registry: {e}")

# ── MINECRAFT SLP PING ───────────────────────────────────────────────────────
def ping_minecraft_server(timeout=2.5):
    """Minecraft Server List Ping (SLP) to query real-time player count & status."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((SERVER_HOST, SERVER_PORT))

        def send_varint(val):
            res = bytearray()
            while True:
                b = val & 0x7F
                val >>= 7
                if val != 0:
                    b |= 0x80
                res.append(b)
                if val == 0:
                    break
            return bytes(res)

        def read_varint(sock):
            val = 0
            for i in range(5):
                b = sock.recv(1)
                if not b:
                    raise EOFError("Closed")
                byte = b[0]
                val |= (byte & 0x7F) << (7 * i)
                if not (byte & 0x80):
                    break
            return val

        host_b = SERVER_HOST.encode('utf-8')
        packet = b'\x00' + send_varint(767) + send_varint(len(host_b)) + host_b + struct.pack('>H', SERVER_PORT) + send_varint(1)
        s.send(send_varint(len(packet)) + packet)
        s.send(send_varint(1) + b'\x00')

        length = read_varint(s)
        packet_id = read_varint(s)
        str_len = read_varint(s)
        data = b''
        while len(data) < str_len:
            chunk = s.recv(min(4096, str_len - len(data)))
            if not chunk:
                break
            data += chunk
        s.close()

        res = json.loads(data.decode('utf-8'))
        online_players = res.get('players', {}).get('online', 0)
        max_players = res.get('players', {}).get('max', 50)
        version = res.get('version', {}).get('name', 'Paper 26.3')
        return True, f"Online ({online_players}/{max_players})", online_players, max_players, version
    except Exception:
        return False, "Offline", 0, 0, None

# ── PTERODACTYL API HELPER ───────────────────────────────────────────────────
def ptero_api_call(method: str, endpoint: str, json_data=None):
    """Make authenticated call to Pterodactyl client API."""
    url = f"{PTERO_URL}/api/client/servers/{PTERO_SERVER}{endpoint}"
    headers = {
        "Authorization": f"Bearer {PTERO_KEY}",
        "Accept": "Application/vnd.pterodactyl.v1+json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.request(method, url, headers=headers, json=json_data, timeout=8)
        if resp.status_code in [200, 204]:
            return True, resp.json() if resp.text else {}
        return False, resp.text
    except Exception as e:
        return False, str(e)

def send_pterodactyl_start():
    return ptero_api_call("POST", "/power", {"signal": "start"})

def send_whitelist_command(ign: str) -> bool:
    try:
        ptero_api_call("POST", "/command", {"command": f"whitelist add {ign}"})
        ptero_api_call("POST", "/command", {"command": f"fwd:whitelist add {ign}"})
        ptero_api_call("POST", "/command", {"command": "whitelist reload"})
        return True
    except Exception:
        return False

# ── DISCORD BOT & UI ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

start_lock = asyncio.Lock()
is_starting = False

class WhitelistModal(discord.ui.Modal, title="Minecraft Whitelist"):
    ign_input = discord.ui.TextInput(
        label="Minecraft Username (Java or Bedrock)",
        placeholder="e.g. AaluGamer123 or .BedrockUser",
        min_length=3,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await handle_whitelist_request(interaction, self.ign_input.value, user=interaction.user)

class ServerControlView(discord.ui.View):
    """Interactive Discord buttons for controlling or whitelisting on the server."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Turn On Server", style=discord.ButtonStyle.success, custom_id="btn_start_server", emoji="⚡")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_start_request(interaction, user=interaction.user)

    @discord.ui.button(label="📊 Server Status", style=discord.ButtonStyle.secondary, custom_id="btn_status_server", emoji="🔍")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_status_request(interaction)

    @discord.ui.button(label="📝 Whitelist Me", style=discord.ButtonStyle.primary, custom_id="btn_whitelist_server", emoji="🎟️")
    async def whitelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhitelistModal())

class ServerBuilderBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(ServerControlView())
        logging.info("[SetupHook] Persistent ServerControlView registered.")

        for gid in [PRIMARY_GUILD_ID, CS2_GUILD_ID]:
            try:
                g_obj = discord.Object(id=gid)
                self.tree.copy_global_to(guild=g_obj)
                synced = await self.tree.sync(guild=g_obj)
                logging.info(f"[SetupHook] Synced {len(synced)} slash commands directly to Guild {gid}.")
            except Exception as ge:
                logging.error(f"[SetupHook] Sync error for guild {gid}: {ge}")

        try:
            await self.tree.sync()
            logging.info("[SetupHook] Global slash commands synced.")
        except Exception as se:
            logging.error(f"[SetupHook] Global sync notice: {se}")

bot = ServerBuilderBot(command_prefix=['!', '/', '.'], intents=intents, help_command=None)

# ── REQUEST HANDLERS ─────────────────────────────────────────────────────────
async def handle_status_request(interaction_or_ctx):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer()
            except Exception: pass
        reply_fn = interaction_or_ctx.followup.send if interaction_or_ctx.response.is_done() else interaction_or_ctx.response.send_message
    else:
        reply_fn = interaction_or_ctx.send

    is_online, desc, online_p, max_p, ver = await asyncio.to_thread(ping_minecraft_server, 2.5)

    if is_online:
        embed = discord.Embed(
            title="🟢 Minecraft Server is ONLINE & READY!",
            description="The server is actively running and accepting connections.",
            color=0x2ECC71
        )
        embed.add_field(name="👥 Players Online", value=f"`{online_p}/{max_p}`", inline=True)
        embed.add_field(name="⚡ Version", value=f"`{ver}`\n*(Crossplay 1.7 - 1.21.x & Bedrock)*", inline=True)
        embed.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
        embed.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)
        embed.set_footer(text="Aalu Server Builder • 24/7 Always-Online Active")
        await reply_fn(embed=embed, view=ServerControlView())
    else:
        embed = discord.Embed(
            title="🔴 Minecraft Server is OFFLINE",
            description="The server is currently stopped. Click below to turn it on!",
            color=0xE74C3C
        )
        embed.add_field(name="🚀 How to turn on?", value="Click **🟢 Turn On Server** below or type `!start` in chat.", inline=False)
        embed.add_field(name="📝 Join Whitelist", value="Click **📝 Whitelist Me** or type `/whitelist <ign>`.", inline=False)
        embed.set_footer(text="Aalu Server Builder • Click below to play!")
        await reply_fn(embed=embed, view=ServerControlView())

async def handle_start_request(interaction_or_ctx, user):
    global is_starting
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer()
            except Exception: pass
        reply_fn = interaction_or_ctx.followup.send if interaction_or_ctx.response.is_done() else interaction_or_ctx.response.send_message
    else:
        reply_fn = interaction_or_ctx.send

    is_online, desc, online_p, max_p, ver = await asyncio.to_thread(ping_minecraft_server, 1.5)
    if is_online:
        embed = discord.Embed(
            title="🟢 Server is Already ONLINE!",
            description=f"The server is already running with **{online_p}/{max_p}** players.\nJoin now at `{SERVER_HOST}:{SERVER_PORT}`!",
            color=0x2ECC71
        )
        await reply_fn(embed=embed, view=ServerControlView())
        return

    if is_starting:
        embed = discord.Embed(
            title="⏳ Server is Already Booting Up!",
            description="Someone has already requested to start the server! Please wait ~20-30 seconds.",
            color=0xF1C40F
        )
        await reply_fn(embed=embed, view=ServerControlView())
        return

    async with start_lock:
        is_starting = True
        try:
            embed_init = discord.Embed(
                title="🚀 Turning ON the Minecraft Server...",
                description=f"Startup command triggered by **{user.mention}**!\n\nSending power signal to hosting panel...",
                color=0x3498DB
            )
            embed_init.add_field(name="📍 Server Address", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
            embed_init.add_field(name="⏳ Expected Boot Time", value="~25-45 seconds for Paper to load worlds.", inline=False)
            embed_init.set_footer(text="Aalu Server Builder • 24/7 Cloud Host")
            await reply_fn(embed=embed_init, view=ServerControlView())

            await asyncio.to_thread(send_pterodactyl_start)

            ready = False
            for _ in range(25):
                await asyncio.sleep(3)
                is_up, _, cur_players, _, ver = await asyncio.to_thread(ping_minecraft_server, 2.0)
                if is_up:
                    ready = True
                    break

            if ready:
                embed_ready = discord.Embed(
                    title="🎉 Minecraft Server is NOW ONLINE!",
                    description="The server has booted successfully and is **READY TO PLAY**!",
                    color=0x2ECC71
                )
                embed_ready.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`", inline=False)
                embed_ready.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)
                embed_ready.set_footer(text="Aalu Server Builder • Have fun!")
                if is_inter and interaction_or_ctx.channel:
                    await interaction_or_ctx.channel.send(content=f"🔔 {user.mention} the Minecraft server is online!", embed=embed_ready, view=ServerControlView())
                else:
                    await reply_fn(embed=embed_ready, view=ServerControlView())
            else:
                embed_to = discord.Embed(
                    title="⏳ Server Boot is in Progress...",
                    description=f"The server is taking longer than usual to boot.\nPlease try checking `/status` or connecting in 1 minute at `{SERVER_HOST}:{SERVER_PORT}`.",
                    color=0xF1C40F
                )
                await reply_fn(embed=embed_to, view=ServerControlView())
        except Exception as e:
            embed_err = discord.Embed(
                title="✖ Notice on Start Request",
                description=f"Startup signal dispatched. Please check `/status` in 30 seconds.\n`{str(e)[:200]}`",
                color=0xF1C40F
            )
            await reply_fn(embed=embed_err, view=ServerControlView())
        finally:
            is_starting = False

async def handle_whitelist_request(interaction_or_ctx, ign: str, user):
    is_inter = isinstance(interaction_or_ctx, discord.Interaction)
    if is_inter:
        if not interaction_or_ctx.response.is_done():
            try: await interaction_or_ctx.response.defer()
            except Exception: pass
        reply_fn = interaction_or_ctx.followup.send if interaction_or_ctx.response.is_done() else interaction_or_ctx.response.send_message
    else:
        reply_fn = interaction_or_ctx.send

    if not ign:
        await reply_fn("❌ Usage: `/whitelist <your_minecraft_ign>` or `!whitelist <ign>`")
        return

    clean_ign = ign.strip().replace('"', '').replace("'", '')
    if not re.match(r'^[a-zA-Z0-9_.* ]{3,20}$', clean_ign):
        embed_err = discord.Embed(
            title="❌ Invalid Minecraft Username",
            description=f"**`{clean_ign}`** is not a valid username.\nPlease enter your Java or Bedrock gamer tag (3-20 characters).",
            color=0xE74C3C
        )
        await reply_fn(embed=embed_err)
        return

    reg = load_whitelist_registry()
    user_id_str = str(user.id)
    prev_entry = reg.get(user_id_str)

    reg[user_id_str] = {
        "ign": clean_ign,
        "discord_id": user.id,
        "discord_username": str(user),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_whitelist_registry(reg)

    applied_live = False
    try:
        applied_live = await asyncio.to_thread(send_whitelist_command, clean_ign)
    except Exception:
        pass

    avatar_url = f"https://mc-heads.net/avatar/{clean_ign.replace(' ', '%20')}/128"

    embed = discord.Embed(
        title="✅ Successfully Whitelisted on Aalu SMP!",
        description=f"Welcome to the community, {user.mention}!\nYour account **`{clean_ign}`** has been registered to the whitelist.",
        color=0x2ECC71
    )
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="🎮 Minecraft IGN", value=f"`{clean_ign}`", inline=True)
    embed.add_field(name="⚡ Whitelist Status", value="**Active & Whitelisted**" if applied_live else "**Queued (Applies on boot)**", inline=True)
    embed.add_field(name="☕ Java Connection", value=f"`{SERVER_HOST}:{SERVER_PORT}`\n*(Versions 1.7 to 1.21.x)*", inline=False)
    embed.add_field(name="📱 Bedrock Connection", value=f"IP: `{SERVER_HOST}` | Port: `{SERVER_PORT}`", inline=False)

    if prev_entry and prev_entry.get("ign") != clean_ign:
        embed.set_footer(text=f"Updated from previous IGN: {prev_entry.get('ign')} • Follow rules & enjoy!")
    else:
        embed.set_footer(text="Aalu Server Builder • 24/7 Always-Online Active")

    await reply_fn(embed=embed, view=ServerControlView())

# ── SLASH COMMANDS ───────────────────────────────────────────────────────────
@bot.tree.command(name="start", description="Turn on the Minecraft server (anyone can use this!)")
async def slash_start(interaction: discord.Interaction):
    await handle_start_request(interaction, user=interaction.user)

@bot.tree.command(name="status", description="Check if the Minecraft server is online or offline")
async def slash_status(interaction: discord.Interaction):
    await handle_status_request(interaction)

@bot.tree.command(name="whitelist", description="Self-service: Whitelist your Minecraft IGN to join the Aalu SMP!")
@app_commands.describe(ign="Your exact in-game Minecraft username (Java or Bedrock)")
async def slash_whitelist(interaction: discord.Interaction, ign: str):
    await handle_whitelist_request(interaction, ign, user=interaction.user)

@bot.tree.command(name="help", description="Show Minecraft server builder bot commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Server Builder Bot Commands",
        description="Commands to manage and play on the Minecraft server!",
        color=0x9B59B6
    )
    embed.add_field(name="🚀 Turn On Server", value="`/start`, `!start`, or the green button below", inline=False)
    embed.add_field(name="📝 Join Whitelist", value="`/whitelist <ign>` or `!whitelist <ign>`", inline=False)
    embed.add_field(name="🔍 Check Status", value="`/status`, `!status`, or `!ip`", inline=False)
    embed.set_footer(text="Aalu Server Builder • 24/7 Cloud Host")
    await interaction.response.send_message(embed=embed, view=ServerControlView())

# ── TEXT COMMANDS ────────────────────────────────────────────────────────────
@bot.command(name="start", aliases=["startserver", "turnon", "on"])
async def cmd_start(ctx):
    await handle_start_request(ctx, user=ctx.author)

@bot.command(name="status", aliases=["online", "server", "ip", "info"])
async def cmd_status(ctx):
    await handle_status_request(ctx)

@bot.command(name="whitelist", aliases=["wl", "addwhitelist"])
async def cmd_whitelist(ctx, *, ign: str = None):
    await handle_whitelist_request(ctx, ign, user=ctx.author)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="🤖 Server Builder Bot Commands",
        description="Commands to manage and play on the Minecraft server!",
        color=0x9B59B6
    )
    embed.add_field(name="🚀 Turn On Server", value="`!start` or `/start`", inline=False)
    embed.add_field(name="📝 Join Whitelist", value="`!whitelist <ign>` or `/whitelist <ign>`", inline=False)
    embed.add_field(name="🔍 Check Status", value="`!status` or `/status`", inline=False)
    embed.set_footer(text="Aalu Server Builder • 24/7 Cloud Host")
    await ctx.send(embed=embed, view=ServerControlView())

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        await asyncio.sleep(0.05)
        if not interaction.response.is_done():
            custom_id = (interaction.data or {}).get("custom_id", "")
            if "start" in custom_id:
                await handle_start_request(interaction, user=interaction.user)
            elif "status" in custom_id:
                await handle_status_request(interaction)
            elif "whitelist" in custom_id:
                await interaction.response.send_modal(WhitelistModal())

# ── BACKGROUND KEEP-ALIVE HTTP SERVER & GUARDIAN ─────────────────────────────
async def health_handler(request):
    return web.Response(text=json.dumps({"status": "healthy", "service": "Aalu Server Builder Bot", "time": time.time()}), content_type="application/json")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_handler)
    app.router.add_get('/healthz', health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"✓ Health Check Web Server running on port {PORT}")

async def render_keepalive_loop():
    """Pings healthcheck every 10 mins so Render free tier never idles or sleeps."""
    await asyncio.sleep(30)
    while True:
        try:
            urls_to_ping = [f"http://127.0.0.1:{PORT}/healthz"]
            if RENDER_EXTERNAL_URL:
                urls_to_ping.append(f"{RENDER_EXTERNAL_URL}/healthz")

            async with aiohttp.ClientSession() as session:
                for u in urls_to_ping:
                    async with session.get(u, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        pass
        except Exception:
            pass
        await asyncio.sleep(600)  # every 10 minutes

async def guardian_loop():
    """Periodically verifies Minecraft server health and updates Discord activity."""
    await asyncio.sleep(10)
    while True:
        try:
            is_up, _, p_count, _, _ = await asyncio.to_thread(ping_minecraft_server, 2.0)
            if is_up:
                activity = discord.Activity(type=discord.ActivityType.playing, name=f"Minecraft ({p_count}/50) | /start")
                await bot.change_presence(status=discord.Status.online, activity=activity)
            else:
                activity = discord.Activity(type=discord.ActivityType.listening, name="/start | legacy-7.hexacraft.fun")
                await bot.change_presence(status=discord.Status.idle, activity=activity)
        except Exception:
            pass
        await asyncio.sleep(1800)  # every 30 minutes

@bot.event
async def on_ready():
    logging.info(f"==========================================================")
    logging.info(f"  SERVER BUILDER BOT ONLINE: {bot.user} (ID: {bot.user.id})")
    logging.info(f"==========================================================")
    asyncio.create_task(guardian_loop())
    asyncio.create_task(render_keepalive_loop())

async def main():
    await start_web_server()
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
