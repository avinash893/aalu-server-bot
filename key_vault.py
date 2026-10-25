"""
key_vault.py - Secure Encrypted Key Vault for Tillu BYOK (Bring Your Own Key)
Stores encrypted API keys per Discord user ID with timestamped checkpoint history.
"""

import os
import json
import base64
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger("KeyVault")

VAULT_DIR = Path("data")
VAULT_FILE = VAULT_DIR / "user_vault.json"
VAULT_KEY_FILE = VAULT_DIR / ".vault_master.key"


def _get_or_create_master_key() -> bytes:
    """Retrieve or generate a persistent 32-byte Fernet key."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check env first
    env_secret = os.environ.get("VAULT_SECRET_KEY")
    if env_secret:
        # derive 32-byte urlsafe key from secret
        derived = hashlib.sha256(env_secret.encode()).digest()
        return base64.urlsafe_b64encode(derived)
        
    if VAULT_KEY_FILE.exists():
        try:
            return VAULT_KEY_FILE.read_bytes().strip()
        except Exception as e:
            logger.warning(f"Failed reading vault key file: {e}")

    # Generate new key
    key = Fernet.generate_key()
    try:
        VAULT_KEY_FILE.write_bytes(key)
    except Exception as e:
        logger.warning(f"Could not persist vault master key to file: {e}")
    return key


_FERNET = Fernet(_get_or_create_master_key())


def _load_raw_vault() -> dict:
    if not VAULT_FILE.exists():
        return {}
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading user vault: {e}")
        return {}


def _save_raw_vault(data: dict):
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = VAULT_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    temp_file.replace(VAULT_FILE)


def _encrypt_str(text: str) -> str:
    if not text:
        return ""
    return _FERNET.encrypt(text.encode("utf-8")).decode("utf-8")


def _decrypt_str(token: str) -> str:
    if not token:
        return ""
    try:
        return _FERNET.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def save_user_keys(
    user_id: int | str,
    chat_key: str = "",
    image_key: str = "",
    coding_key: str = "",
    username: str = ""
) -> dict:
    """
    Save or update user's encrypted API keys and record a checkpoint.
    Preserves existing keys if new ones are blank.
    """
    uid = str(user_id)
    vault = _load_raw_vault()
    user_record = vault.get(uid, {
        "username": username,
        "chat_key": "",
        "image_key": "",
        "coding_key": "",
        "checkpoints": []
    })

    if username:
        user_record["username"] = username

    # Only overwrite if provided
    updated_fields = []
    if chat_key.strip():
        user_record["chat_key"] = _encrypt_str(chat_key.strip())
        updated_fields.append("chat")
    if image_key.strip():
        user_record["image_key"] = _encrypt_str(image_key.strip())
        updated_fields.append("image")
    if coding_key.strip():
        user_record["coding_key"] = _encrypt_str(coding_key.strip())
        updated_fields.append("coding")

    now_iso = datetime.now(timezone.utc).isoformat()
    checkpoint = {
        "timestamp": now_iso,
        "updated": updated_fields,
        "chat_active": bool(user_record.get("chat_key")),
        "image_active": bool(user_record.get("image_key")),
        "coding_active": bool(user_record.get("coding_key")),
    }
    
    checkpoints = user_record.get("checkpoints", [])
    checkpoints.append(checkpoint)
    # keep last 10 checkpoints
    user_record["checkpoints"] = checkpoints[-10:]
    user_record["last_updated"] = now_iso

    vault[uid] = user_record
    _save_raw_vault(vault)
    logger.info(f"[KeyVault] Checkpoint saved for user {uid} ({username}) with {updated_fields}")

    return {
        "success": True,
        "last_updated": now_iso,
        "chat_active": bool(user_record.get("chat_key")),
        "image_active": bool(user_record.get("image_key")),
        "coding_active": bool(user_record.get("coding_key")),
        "checkpoints": user_record["checkpoints"]
    }


def get_user_keys(user_id: int | str) -> dict:
    """
    Retrieve decrypted keys for a given user ID.
    Returns:
    {
      "chat_key": "...",
      "image_key": "...",
      "coding_key": "...",
      "has_chat": bool,
      "has_image": bool,
      "has_coding": bool,
      "last_updated": str,
      "checkpoints": list
    }
    """
    uid = str(user_id)
    vault = _load_raw_vault()
    record = vault.get(uid)
    if not record:
        return {
            "chat_key": "",
            "image_key": "",
            "coding_key": "",
            "has_chat": False,
            "has_image": False,
            "has_coding": False,
            "last_updated": None,
            "checkpoints": []
        }

    chat_decrypted = _decrypt_str(record.get("chat_key", ""))
    image_decrypted = _decrypt_str(record.get("image_key", ""))
    coding_decrypted = _decrypt_str(record.get("coding_key", ""))

    return {
        "chat_key": chat_decrypted,
        "image_key": image_decrypted,
        "coding_key": coding_decrypted,
        "has_chat": bool(chat_decrypted),
        "has_image": bool(image_decrypted),
        "has_coding": bool(coding_decrypted),
        "last_updated": record.get("last_updated"),
        "checkpoints": record.get("checkpoints", [])
    }


def has_user_key(user_id: int | str, category: str = "chat") -> bool:
    """Quick boolean check if a user has configured a key for a category."""
    keys = get_user_keys(user_id)
    if category == "chat":
        return keys["has_chat"]
    if category == "image":
        return keys["has_image"]
    if category == "coding":
        return keys["has_coding"]
    return False
