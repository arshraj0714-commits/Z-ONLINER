"""
Z Onliner - Token Manager Module
Manages user account clients that stay online via discord.py-self.
"""

import asyncio
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import discord_self as discord

logger = logging.getLogger("z_onliner")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def parse_token_line(line: str) -> Optional[str]:
    """
    Parse a single line and extract the Discord token.
    Supports two formats:
      - user:pass:token   →  extracts the 3rd colon-separated part
      - token             →  uses the line as-is
    Returns the token string, or None if the line is empty/invalid.
    """
    line = line.strip()
    if not line:
        return None

    # If it contains colons and has exactly 3 parts → user:pass:token
    parts = line.split(":")
    if len(parts) >= 3:
        # The token is everything after the second colon (in case token has colons)
        # Re-join from index 2 onwards in case the token itself contains colons
        token = ":".join(parts[2:])
        token = token.strip()
        if token:
            return token

    # Otherwise treat the whole line as a plain token
    # Basic sanity: Discord tokens are typically 50-120 chars
    if len(line) >= 20:
        return line

    return None


def load_tokens() -> Dict[str, dict]:
    """Load tokens from JSON file. Returns {token_str: {label, added_at}}"""
    _ensure_data_dir()
    if not os.path.exists(TOKENS_FILE):
        return {}
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_tokens(tokens: Dict[str, dict]):
    """Persist tokens to JSON file."""
    _ensure_data_dir()
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)


def add_token(token: str, label: str = None) -> bool:
    """Add a new token. Returns True if newly added, False if already existed."""
    tokens = load_tokens()
    if token in tokens:
        return False
    tokens[token] = {
        "label": label or token[:12] + "...",
        "added_at": datetime.utcnow().isoformat(),
    }
    save_tokens(tokens)
    return True


def remove_token(token: str) -> bool:
    """Remove a token. Returns True if removed, False if not found."""
    tokens = load_tokens()
    if token in tokens:
        del tokens[token]
        save_tokens(tokens)
        return True
    return False


class AccountClient(discord.Client):
    """A self-bot client that logs in as a user account to keep it online."""

    def __init__(self, token: str, loop: asyncio.AbstractEventLoop):
        intents = discord.Intents.all()
        super().__init__(intents=intents, loop=loop)
        self._token = token
        self._status_task: Optional[asyncio.Task] = None
        self._current_status = "offline"
        self._target_status = "online"
        self._temp_status_until: Optional[datetime] = None
        self._username: Optional[str] = None
        self._is_ready = False
        self._keep_alive = True

    @property
    def account_label(self) -> str:
        return self._username or self._token[:16] + "..."

    @property
    def current_status(self) -> str:
        return self._current_status

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    async def set_online(self):
        self._target_status = "online"
        self._temp_status_until = None
        if self._is_ready:
            try:
                await self.change_presence(
                    status=discord.Status.online,
                    activity=discord.CustomActivity(name="Z Onliner"),
                )
                self._current_status = "online"
                logger.info(f"[{self.account_label}] Set to online")
            except Exception as e:
                logger.error(f"[{self.account_label}] Error setting online: {e}")

    async def set_status(self, status_name: str, duration_minutes: Optional[int] = None):
        """Set account to a specific status (online, idle, dnd, invisible/offline)."""
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
            "offline": discord.Status.invisible,
        }
        disc_status = status_map.get(status_name.lower(), discord.Status.online)
        self._target_status = status_name.lower()

        if duration_minutes:
            self._temp_status_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        else:
            self._temp_status_until = None

        if self._is_ready:
            try:
                await self.change_presence(
                    status=disc_status,
                    activity=discord.CustomActivity(name="Z Onliner"),
                )
                self._current_status = status_name.lower()
                logger.info(f"[{self.account_label}] Set to {status_name}")
            except Exception as e:
                logger.error(f"[{self.account_label}] Error setting status: {e}")

    async def set_offline(self):
        """Set account to invisible/offline."""
        await self.set_status("offline")
        self._keep_alive = False

    async def on_ready(self):
        self._username = str(self.user)
        self._is_ready = True
        logger.info(f"[{self.account_label}] Logged in successfully")
        await self.set_online()
        self._status_task = self.loop.create_task(self._status_watcher())

    async def _status_watcher(self):
        """Watch for temporary status expiry and revert to online."""
        try:
            while self._keep_alive and not self.is_closed():
                if self._temp_status_until and datetime.utcnow() >= self._temp_status_until:
                    logger.info(f"[{self.account_label}] Temporary status expired, reverting to online")
                    await self.set_online()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.account_label}] Status watcher error: {e}")

    async def on_disconnect(self):
        self._is_ready = False
        self._current_status = "offline"


# ---------------------------------------------------------------------------
# Singleton manager that the bot interacts with
# ---------------------------------------------------------------------------


class TokenManager:
    """Manages all AccountClient instances."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.clients: Dict[str, AccountClient] = {}  # token -> AccountClient

    def _make_client(self, token: str) -> AccountClient:
        client = AccountClient(token, self.loop)
        self.clients[token] = client
        return client

    async def go_online(self, token: str, duration: int = 0) -> dict:
        """
        Start a token client. duration=0 means infinite.
        Returns {success, message, username}.
        """
        if token in self.clients:
            c = self.clients[token]
            if c.is_ready and c.current_status == "online":
                return {
                    "success": False,
                    "message": f"**{c.account_label}** is already online.",
                    "username": c.account_label,
                }
            # Reconnect
            return await self._start_client(token)

        return await self._start_client(token)

    async def _start_client(self, token: str) -> dict:
        client = self._make_client(token)
        try:
            # Validate token by attempting login
            await client.login(token)
            self.loop.create_task(client.connect(reconnect=True))
            # Wait briefly for on_ready
            for _ in range(20):
                await asyncio.sleep(0.5)
                if client.is_ready:
                    break

            if client.is_ready:
                return {
                    "success": True,
                    "message": f"**{client.account_label}** is now online!",
                    "username": client.account_label,
                }
            else:
                # Login succeeded but on_ready didn't fire yet - still OK
                return {
                    "success": True,
                    "message": f"**{client.account_label}** is connecting... (will be online shortly)",
                    "username": client.account_label,
                }
        except discord.LoginFailure:
            self.clients.pop(token, None)
            return {
                "success": False,
                "message": f"Invalid token: `{token[:20]}...`",
                "username": None,
            }
        except Exception as e:
            self.clients.pop(token, None)
            logger.exception(f"Error starting client")
            return {
                "success": False,
                "message": f"Error: `{str(e)[:100]}`",
                "username": None,
            }

    async def go_online_from_file(self, file_content: str, duration: int = 0) -> dict:
        """Parse tokens from file content and start them all.
        Supports both formats per line:
          - user:pass:token
          - token
        """
        raw_lines = [l.strip() for l in file_content.strip().splitlines() if l.strip()]
        parsed = []
        skipped = 0
        for line in raw_lines:
            token = parse_token_line(line)
            if token:
                parsed.append(token)
            else:
                skipped += 1

        if not parsed:
            return {"success": False, "message": f"No valid tokens found in file. {skipped} line(s) skipped.", "results": []}

        results = []
        for token in parsed:
            res = await self.go_online(token, duration)
            results.append(res)
            add_token(token, res.get("username", token[:12] + "..."))
            await asyncio.sleep(0.5)  # Stagger logins

        success_count = sum(1 for r in results if r["success"])
        fail_count = len(results) - success_count
        msg = f"Processed **{len(parsed)}** tokens: {success_count} online, {fail_count} failed."
        if skipped:
            msg += f" ({skipped} line(s) skipped - invalid format)"
        return {
            "success": True,
            "message": msg,
            "results": results,
        }

    def get_all_tokens(self) -> List[dict]:
        """Return list of all known tokens with their status."""
        saved = load_tokens()
        result = []
        for token, info in saved.items():
            if token in self.clients:
                c = self.clients[token]
                result.append({
                    "token_preview": token[:20] + "...",
                    "label": c.account_label if c._username else info.get("label", token[:12] + "..."),
                    "status": c.current_status,
                    "ready": c.is_ready,
                })
            else:
                result.append({
                    "token_preview": token[:20] + "...",
                    "label": info.get("label", token[:12] + "..."),
                    "status": "offline",
                    "ready": False,
                })
        return result

    def get_online_tokens(self) -> List[dict]:
        return [t for t in self.get_all_tokens() if t["status"] == "online"]

    def get_offline_tokens(self) -> List[dict]:
        return [t for t in self.get_all_tokens() if t["status"] != "online"]

    async def change_status(self, token_preview: str, new_status: str, duration: int = None) -> dict:
        """Change status of a specific token by its preview string."""
        saved = load_tokens()
        for token in saved:
            if token[:20] + "..." == token_preview:
                if token in self.clients:
                    c = self.clients[token]
                    await c.set_status(new_status, duration_minutes=duration)
                    return {
                        "success": True,
                        "message": f"Changed **{c.account_label}** to **{new_status}**" +
                        (f" for {duration} minutes" if duration else ""),
                        "username": c.account_label,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"**{token_preview}** is not currently running. Use `/online` first.",
                    }
        return {"success": False, "message": f"Token **{token_preview}** not found in saved tokens."}

    async def go_offline(self, token_preview: str) -> dict:
        """Disconnect a specific token by its preview string."""
        saved = load_tokens()
        for token in saved:
            if token[:20] + "..." == token_preview:
                if token in self.clients:
                    c = self.clients[token]
                    await c.set_offline()
                    await c.close()
                    self.clients.pop(token, None)
                    return {
                        "success": True,
                        "message": f"**{c.account_label}** is now offline.",
                        "username": c.account_label,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"**{token_preview}** is already offline.",
                    }
        return {"success": False, "message": f"Token **{token_preview}** not found."}

    async def shutdown_all(self):
        """Gracefully shut down all clients."""
        for token, client in list(self.clients.items()):
            try:
                client._keep_alive = False
                if client._status_task:
                    client._status_task.cancel()
                await client.close()
            except Exception:
                pass
        self.clients.clear()
        logger.info("All clients shut down.")
