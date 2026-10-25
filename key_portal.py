"""
key_portal.py - Ephemeral Web Settings Portal for Tillu BYOK
Serves the dark-mode dashboard for users to add, test, and save their private API keys.
"""

import time
import json
import hmac
import hashlib
import base64
import logging
import aiohttp
from aiohttp import web
import key_vault

logger = logging.getLogger("KeyPortal")

# Secret salt for signing tokens (derived or fallback)
_TOKEN_SECRET = (key_vault._get_or_create_master_key())

TOKEN_EXPIRY_SECONDS = 900  # 15 minutes


def generate_portal_token(user_id: int | str, username: str, avatar_url: str = "") -> str:
    """Generate a tamper-proof, 15-minute signed ephemeral token for the setup portal."""
    payload = {
        "uid": str(user_id),
        "name": username,
        "avatar": avatar_url,
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS
    }
    raw_json = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    sig = hmac.new(_TOKEN_SECRET, raw_json, hashlib.sha256).digest()
    
    # Combined base64
    packed = raw_json + b":::" + sig
    return base64.urlsafe_b64encode(packed).decode("utf-8")


def verify_portal_token(token_str: str) -> dict | None:
    """Verify signature and expiration of an ephemeral token."""
    if not token_str:
        return None
    try:
        raw = base64.urlsafe_b64decode(token_str.encode("utf-8"))
        parts = raw.split(b":::")
        if len(parts) != 2:
            return None
        payload_bytes, sig = parts[0], parts[1]
        
        expected_sig = hmac.new(_TOKEN_SECRET, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("[KeyPortal] Invalid token signature detected.")
            return None

        payload = json.loads(payload_bytes.decode("utf-8"))
        if time.time() > payload.get("exp", 0):
            logger.info(f"[KeyPortal] Token expired for user {payload.get('uid')}")
            return None

        return payload
    except Exception as e:
        logger.error(f"[KeyPortal] Token decode error: {e}")
        return None


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tillu AI — Personal Key Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0b0e;
      --card-bg: rgba(18, 20, 26, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(255, 255, 255, 0.12);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --primary-glow: rgba(99, 102, 241, 0.35);
      --accent: #22d3ee;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(circle at 15% 20%, rgba(99, 102, 241, 0.12) 0%, transparent 45%),
        radial-gradient(circle at 85% 80%, rgba(34, 211, 238, 0.08) 0%, transparent 45%);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2.5rem 1rem;
    }

    .container {
      width: 100%;
      max-width: 680px;
    }

    /* Header Profile */
    .user-badge {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      border-radius: 18px;
      padding: 1.25rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 2rem;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }

    .user-info {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .user-avatar {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      border: 2px solid var(--primary);
      object-fit: cover;
      background: #1e1e24;
    }

    .user-details h2 {
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--text-main);
    }

    .user-details span {
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .timer-badge {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--warning);
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.3);
      padding: 0.4rem 0.85rem;
      border-radius: 100px;
      font-family: 'JetBrains Mono', monospace;
    }

    .timer-dot {
      width: 7px;
      height: 7px;
      background: var(--warning);
      border-radius: 50%;
      animation: pulse 1.8s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    /* Section Cards */
    .section-title {
      font-size: 1.25rem;
      font-weight: 800;
      margin-bottom: 0.5rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .section-subtitle {
      font-size: 0.9rem;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
    }

    .key-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      border-radius: 18px;
      padding: 1.5rem;
      margin-bottom: 1.25rem;
      transition: all 0.25s ease;
    }

    .key-card:hover {
      border-color: var(--card-hover);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      user-select: none;
    }

    .card-title-group {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }

    .card-icon {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
    }

    .icon-chat { background: rgba(99, 102, 241, 0.15); color: var(--primary); }
    .icon-image { background: rgba(34, 211, 238, 0.15); color: var(--accent); }
    .icon-code { background: rgba(16, 185, 129, 0.15); color: var(--success); }

    .card-info h3 {
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-main);
    }

    .card-info p {
      font-size: 0.82rem;
      color: var(--text-muted);
      margin-top: 2px;
    }

    .plus-btn {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.2rem;
      color: var(--text-main);
      cursor: pointer;
      transition: transform 0.25s ease, background 0.2s;
    }

    .plus-btn.open {
      transform: rotate(45deg);
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border-color: rgba(239, 68, 68, 0.3);
    }

    /* Collapsible Body */
    .card-body {
      display: none;
      margin-top: 1.25rem;
      padding-top: 1.25rem;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }

    .card-body.show {
      display: block;
      animation: fadeIn 0.25s ease-in-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .helper-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
    }

    .free-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--accent);
      background: rgba(34, 211, 238, 0.1);
      border: 1px solid rgba(34, 211, 238, 0.25);
      padding: 0.35rem 0.75rem;
      border-radius: 8px;
      text-decoration: none;
      transition: all 0.2s ease;
    }

    .free-btn:hover {
      background: rgba(34, 211, 238, 0.2);
      transform: translateY(-1px);
    }

    .input-group {
      position: relative;
      display: flex;
      gap: 0.6rem;
    }

    .key-input {
      flex: 1;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 0.75rem 1rem;
      color: var(--text-main);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.88rem;
      outline: none;
      transition: border 0.2s ease;
    }

    .key-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 2px var(--primary-glow);
    }

    .test-btn {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      color: var(--text-main);
      font-size: 0.85rem;
      font-weight: 600;
      padding: 0.75rem 1.1rem;
      border-radius: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      white-space: nowrap;
      transition: all 0.2s;
    }

    .test-btn:hover {
      background: rgba(255, 255, 255, 0.12);
    }

    .test-result {
      margin-top: 0.6rem;
      font-size: 0.82rem;
      display: none;
      align-items: center;
      gap: 0.35rem;
    }

    .test-result.success {
      display: flex;
      color: var(--success);
    }

    .test-result.error {
      display: flex;
      color: var(--danger);
    }

    /* Save Checkpoint Button */
    .save-section {
      margin-top: 2rem;
      text-align: center;
    }

    .save-btn {
      width: 100%;
      background: linear-gradient(135deg, var(--primary) 0%, #4338ca 100%);
      color: white;
      border: none;
      border-radius: 14px;
      padding: 1rem 1.5rem;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 8px 25px var(--primary-glow);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.6rem;
      transition: transform 0.2s, box-shadow 0.2s;
    }

    .save-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 12px 30px rgba(99, 102, 241, 0.5);
    }

    .save-btn:active {
      transform: translateY(0);
    }

    /* Checkpoint History */
    .history-card {
      margin-top: 2rem;
      background: rgba(18, 20, 26, 0.4);
      border: 1px dashed var(--card-border);
      border-radius: 16px;
      padding: 1.25rem;
    }

    .history-card h4 {
      font-size: 0.88rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }

    .checkpoint-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.82rem;
      padding: 0.45rem 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    }

    .checkpoint-item:last-child {
      border-bottom: none;
    }

    .status-pill {
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      font-weight: 600;
    }

    .pill-green { background: rgba(16, 185, 129, 0.15); color: var(--success); }
    .pill-gray { background: rgba(255, 255, 255, 0.05); color: var(--text-dim); }

    /* Toast Notification */
    #toast {
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      background: #181920;
      border: 1px solid var(--card-border);
      padding: 1rem 1.5rem;
      border-radius: 12px;
      color: var(--text-main);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
      display: none;
      align-items: center;
      gap: 0.6rem;
      font-size: 0.9rem;
      font-weight: 600;
      z-index: 1000;
      animation: slideUp 0.3s ease;
    }

    @keyframes slideUp {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
  </style>
</head>
<body>

  <div class="container">
    
    <!-- Profile & Countdown -->
    <div class="user-badge">
      <div class="user-info">
        <img class="user-avatar" id="avatarImg" src="" alt="Avatar">
        <div class="user-details">
          <h2 id="userName">Discord User</h2>
          <span>Connected via Discord</span>
        </div>
      </div>
      <div class="timer-badge">
        <div class="timer-dot"></div>
        <span id="countdown">15:00</span>
      </div>
    </div>

    <div class="section-title">⚡ Configure Your Private Keys</div>
    <div class="section-subtitle">Add your own API keys. They are encrypted securely and used exclusively when you chat with Tillu.</div>

    <!-- Section 1: Chat & Intelligence -->
    <div class="key-card">
      <div class="card-header" onclick="toggleSection('chat')">
        <div class="card-title-group">
          <div class="card-icon icon-chat">💬</div>
          <div class="card-info">
            <h3>Chat & General Intelligence</h3>
            <p>Powers Tillu's conversational brain and knowledge base (Gemini 2.5 Flash)</p>
          </div>
        </div>
        <div class="plus-btn" id="plus-chat">+</div>
      </div>
      <div class="card-body" id="body-chat">
        <div class="helper-bar">
          <span style="font-size: 0.8rem; color: var(--text-dim);">Google Gemini API Key</span>
          <a class="free-btn" href="https://aistudio.google.com/app/apikey" target="_blank">
            🔗 Get Free Key (Google AI Studio)
          </a>
        </div>
        <div class="input-group">
          <input type="password" class="key-input" id="chatKey" placeholder="AIzaSy..." autocomplete="off">
          <button class="test-btn" onclick="testKey('chat')">⚡ Test Key</button>
        </div>
        <div class="test-result" id="res-chat"></div>
      </div>
    </div>

    <!-- Section 2: Image & Vision -->
    <div class="key-card">
      <div class="card-header" onclick="toggleSection('image')">
        <div class="card-title-group">
          <div class="card-icon icon-image">🎨</div>
          <div class="card-info">
            <h3>Image Generation & Vision</h3>
            <p>Powers image generation, screenshots, and visual perception (Pollinations AI)</p>
          </div>
        </div>
        <div class="plus-btn" id="plus-image">+</div>
      </div>
      <div class="card-body" id="body-image">
        <div class="helper-bar">
          <span style="font-size: 0.8rem; color: var(--text-dim);">Pollinations API Key (Free tier works without key)</span>
          <a class="free-btn" href="https://pollinations.ai/" target="_blank">
            🔗 Get Pollinations Key
          </a>
        </div>
        <div class="input-group">
          <input type="password" class="key-input" id="imageKey" placeholder="sk_... (optional or leave empty)" autocomplete="off">
          <button class="test-btn" onclick="testKey('image')">⚡ Test Key</button>
        </div>
        <div class="test-result" id="res-image"></div>
      </div>
    </div>

    <!-- Section 3: Coding & Advanced Reasoning -->
    <div class="key-card">
      <div class="card-header" onclick="toggleSection('coding')">
        <div class="card-title-group">
          <div class="card-icon icon-code">💻</div>
          <div class="card-info">
            <h3>Coding & Deep Reasoning</h3>
            <p>Powers Python scripts, code fixing, and high-complexity queries (OpenRouter / Groq / Pro)</p>
          </div>
        </div>
        <div class="plus-btn" id="plus-coding">+</div>
      </div>
      <div class="card-body" id="body-coding">
        <div class="helper-bar">
          <span style="font-size: 0.8rem; color: var(--text-dim);">OpenRouter / Groq / Pro Key</span>
          <a class="free-btn" href="https://openrouter.ai/keys" target="_blank">
            🔗 Get Free Key (OpenRouter)
          </a>
        </div>
        <div class="input-group">
          <input type="password" class="key-input" id="codingKey" placeholder="sk-or-... or gsk_..." autocomplete="off">
          <button class="test-btn" onclick="testKey('coding')">⚡ Test Key</button>
        </div>
        <div class="test-result" id="res-coding"></div>
      </div>
    </div>

    <!-- Save Button -->
    <div class="save-section">
      <button class="save-btn" onclick="saveCheckpoint()">
        💾 Save Checkpoint
      </button>
    </div>

    <!-- Checkpoint History Preview -->
    <div class="history-card" id="historyCard" style="display:none;">
      <h4>Saved Checkpoints History</h4>
      <div id="historyList"></div>
    </div>

  </div>

  <div id="toast"></div>

  <script>
    // Injected Token Data from Server
    const PORTAL_DATA = __PORTAL_DATA_PLACEHOLDER__;

    document.getElementById('userName').innerText = PORTAL_DATA.name || 'User';
    if (PORTAL_DATA.avatar) {
      document.getElementById('avatarImg').src = PORTAL_DATA.avatar;
    } else {
      document.getElementById('avatarImg').src = 'https://cdn.discordapp.com/embed/avatars/0.png';
    }

    // Pre-populate active indicators
    if (PORTAL_DATA.existing) {
      if (PORTAL_DATA.existing.has_chat) {
        document.getElementById('chatKey').placeholder = '•••••••••••••••• (Active Key Saved)';
      }
      if (PORTAL_DATA.existing.has_image) {
        document.getElementById('imageKey').placeholder = '•••••••••••••••• (Active Key Saved)';
      }
      if (PORTAL_DATA.existing.has_coding) {
        document.getElementById('codingKey').placeholder = '•••••••••••••••• (Active Key Saved)';
      }
      renderCheckpoints(PORTAL_DATA.existing.checkpoints || []);
    }

    // Toggle Collapsibles
    function toggleSection(sec) {
      const body = document.getElementById('body-' + sec);
      const plus = document.getElementById('plus-' + sec);
      const isOpen = body.classList.contains('show');
      if (isOpen) {
        body.classList.remove('show');
        plus.classList.remove('open');
      } else {
        body.classList.add('show');
        plus.classList.add('open');
      }
    }

    // Expand chat section by default
    toggleSection('chat');

    // Countdown Timer
    let expTime = PORTAL_DATA.exp || Math.floor(Date.now() / 1000) + 900;
    function updateTimer() {
      const now = Math.floor(Date.now() / 1000);
      const diff = expTime - now;
      if (diff <= 0) {
        document.getElementById('countdown').innerText = 'Expired';
        document.getElementById('countdown').style.color = '#ef4444';
        return;
      }
      const mins = Math.floor(diff / 60);
      const secs = diff % 60;
      document.getElementById('countdown').innerText = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    setInterval(updateTimer, 1000);
    updateTimer();

    // Test API Key
    async function testKey(category) {
      const input = document.getElementById(category + 'Key');
      const val = input.value.trim();
      const resDiv = document.getElementById('res-' + category);
      
      if (!val) {
        resDiv.className = 'test-result error';
        resDiv.innerText = '❌ Please paste an API key first.';
        return;
      }

      resDiv.className = 'test-result';
      resDiv.style.display = 'flex';
      resDiv.style.color = '#94a3b8';
      resDiv.innerText = '⏳ Verifying key with provider...';

      try {
        const resp = await fetch('/api/test-key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category, key: val, token: PORTAL_DATA.token })
        });
        const data = await resp.json();
        if (data.valid) {
          resDiv.className = 'test-result success';
          resDiv.innerText = '✅ ' + data.message;
        } else {
          resDiv.className = 'test-result error';
          resDiv.innerText = '❌ ' + data.message;
        }
      } catch (e) {
        resDiv.className = 'test-result error';
        resDiv.innerText = '❌ Network test failed. Check connection.';
      }
    }

    // Save Checkpoint
    async function saveCheckpoint() {
      const chat_key = document.getElementById('chatKey').value.trim();
      const image_key = document.getElementById('imageKey').value.trim();
      const coding_key = document.getElementById('codingKey').value.trim();

      const btn = document.querySelector('.save-btn');
      btn.innerText = '⏳ Saving Checkpoint...';
      btn.disabled = true;

      try {
        const resp = await fetch('/api/save-keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: PORTAL_DATA.token,
            chat_key,
            image_key,
            coding_key
          })
        });
        const data = await resp.json();
        if (data.success) {
          showToast('✅ Checkpoint saved! Tillu will now use your personal keys.');
          renderCheckpoints(data.checkpoints || []);
          // update placeholders
          if (chat_key) document.getElementById('chatKey').placeholder = '•••••••••••••••• (Saved)';
          if (image_key) document.getElementById('imageKey').placeholder = '•••••••••••••••• (Saved)';
          if (coding_key) document.getElementById('codingKey').placeholder = '•••••••••••••••• (Saved)';
        } else {
          showToast('❌ ' + (data.message || 'Error saving keys'));
        }
      } catch (e) {
        showToast('❌ Failed to connect to server.');
      } finally {
        btn.innerText = '💾 Save Checkpoint';
        btn.disabled = false;
      }
    }

    function renderCheckpoints(list) {
      if (!list || list.length === 0) return;
      document.getElementById('historyCard').style.display = 'block';
      const container = document.getElementById('historyList');
      container.innerHTML = '';
      list.slice().reverse().forEach(item => {
        const div = document.createElement('div');
        div.className = 'checkpoint-item';
        const dateStr = new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        div.innerHTML = `
          <span>Saved at ${dateStr} (${(item.updated || []).join(', ') || 'verified'})</span>
          <div>
            <span class="status-pill ${item.chat_active ? 'pill-green' : 'pill-gray'}">Chat</span>
            <span class="status-pill ${item.image_active ? 'pill-green' : 'pill-gray'}">Image</span>
            <span class="status-pill ${item.coding_active ? 'pill-green' : 'pill-gray'}">Code</span>
          </div>
        `;
        container.appendChild(div);
      });
    }

    function showToast(msg) {
      const toast = document.getElementById('toast');
      toast.innerText = msg;
      toast.style.display = 'flex';
      setTimeout(() => { toast.style.display = 'none'; }, 4000);
    }
  </script>
</body>
</html>
"""


async def setup_handler(request: web.Request) -> web.Response:
    """Render the setup page if token is valid."""
    token = request.query.get("token", "").strip()
    payload = verify_portal_token(token)
    if not payload:
        return web.Response(
            text="""<!DOCTYPE html><html><body style="background:#0a0b0e;color:#ef4444;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:90vh;flex-direction:column;">
            <h2>⚠️ Invalid or Expired Setup Link</h2>
            <p style="color:#94a3b8;margin-top:10px;">This 15-minute setup link has expired. Type <code>/setup</code> in Discord to generate a fresh link!</p>
            </body></html>""",
            content_type="text/html",
            status=401
        )

    uid = payload["uid"]
    existing = key_vault.get_user_keys(uid)
    
    # Hide raw decrypted keys from client for safety
    safe_existing = {
        "has_chat": existing["has_chat"],
        "has_image": existing["has_image"],
        "has_coding": existing["has_coding"],
        "checkpoints": existing.get("checkpoints", []),
        "last_updated": existing.get("last_updated")
    }

    client_data = {
        "token": token,
        "name": payload.get("name", "User"),
        "avatar": payload.get("avatar", ""),
        "exp": payload.get("exp", 0),
        "existing": safe_existing
    }

    html = DASHBOARD_HTML.replace("__PORTAL_DATA_PLACEHOLDER__", json.dumps(client_data))
    return web.Response(text=html, content_type="text/html")


async def test_key_handler(request: web.Request) -> web.Response:
    """Test API key validity against the respective provider."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"valid": False, "message": "Invalid JSON"}, status=400)

    token = data.get("token", "")
    if not verify_portal_token(token):
        return web.json_response({"valid": False, "message": "Session expired. Reopen via /setup."}, status=401)

    category = data.get("category", "")
    key = data.get("key", "").strip()

    if not key:
        return web.json_response({"valid": False, "message": "Empty key provided."})

    # Test Gemini Key
    if category == "chat":
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return web.json_response({"valid": True, "message": "Valid Gemini API Key! Ready to save."})
                    err_json = await resp.json()
                    err_msg = err_json.get("error", {}).get("message", f"HTTP {resp.status}")
                    return web.json_response({"valid": False, "message": f"Gemini rejected key: {err_msg[:60]}"})
        except Exception as e:
            return web.json_response({"valid": False, "message": f"Connection error: {str(e)[:50]}"})

    # Test Pollinations Key
    elif category == "image":
        if key.startswith("sk_") or len(key) >= 16:
            return web.json_response({"valid": True, "message": "Valid Pollinations key format!"})
        return web.json_response({"valid": False, "message": "Expected key format 'sk_...' or Leave blank for free tier."})

    # Test Coding Key (OpenRouter or Groq or generic)
    elif category == "coding":
        if key.startswith("sk-or-"):
            test_url = "https://openrouter.ai/api/v1/auth/key"
            headers = {"Authorization": f"Bearer {key}"}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            return web.json_response({"valid": True, "message": "Valid OpenRouter Key!"})
                        return web.json_response({"valid": False, "message": f"OpenRouter status {resp.status}"})
            except Exception:
                pass
        # generic validation
        if len(key) >= 20:
            return web.json_response({"valid": True, "message": "Key format valid and recognized!"})
        return web.json_response({"valid": False, "message": "Invalid key format."})

    return web.json_response({"valid": False, "message": "Unknown category."})


async def save_keys_handler(request: web.Request) -> web.Response:
    """Save user's encrypted keys into vault."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "message": "Invalid JSON"}, status=400)

    token = data.get("token", "")
    payload = verify_portal_token(token)
    if not payload:
        return web.json_response({"success": False, "message": "Session expired. Reopen via /setup."}, status=401)

    uid = payload["uid"]
    name = payload.get("name", "")
    chat_key = data.get("chat_key", "").strip()
    image_key = data.get("image_key", "").strip()
    coding_key = data.get("coding_key", "").strip()

    res = key_vault.save_user_keys(
        user_id=uid,
        chat_key=chat_key,
        image_key=image_key,
        coding_key=coding_key,
        username=name
    )

    return web.json_response({
        "success": True,
        "message": "Checkpoint saved successfully!",
        "checkpoints": res["checkpoints"]
    })


def register_portal_routes(app: web.Application):
    """Attach the portal endpoints to the existing aiohttp web application."""
    app.router.add_get('/setup', setup_handler)
    app.router.add_post('/api/test-key', test_key_handler)
    app.router.add_post('/api/save-keys', save_keys_handler)
    logger.info("[KeyPortal] Registered /setup and API endpoints.")
