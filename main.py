# -*- coding: utf-8 -*-
"""
Z Onliner - Professional Discord Token Onliner Bot
Built by Arsh

A Discord bot that manages user account tokens and keeps them online
with beautiful, professional embeds.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from token_manager import TokenManager, add_token, load_tokens, save_tokens, parse_token_line

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("z_onliner")

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("DISCORD_BOT_TOKEN not set in .env file!")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Color Palette & Constants
# ---------------------------------------------------------------------------
LOGO_URL = "https://i.ibb.co/0pPwjVmf/Screenshot-2026-08-02-at-10-53-33-AM-removebg-preview.png"

COLORS = {
    "primary":    0x5865F2,
    "success":    0x57F287,
    "warning":    0xFEE75C,
    "danger":     0xED4245,
    "info":       0x5BC0EB,
    "purple":     0x9B59B6,
    "gold":       0xF1C40F,
    "dark":       0x2C2F33,
    "teal":       0x00CED1,
    "hot_pink":   0xFF6B9D,
    "orange":     0xE67E22,
    "white":      0xFFFFFF,
    "online":     0x57F287,
    "idle":       0xFEE75C,
    "dnd":        0xED4245,
    "offline":    0x808080,
}

STATUS_MARK = {
    "online": "\U0001f7e2",
    "idle": "\U0001f7e1",
    "dnd": "\U0001f534",
    "offline": "\u26ab",
    "invisible": "\u26ab",
}

STATUS_COLOR = {
    "online": 0x57F287,
    "idle": 0xFEE75C,
    "dnd": 0xED4245,
    "offline": 0x808080,
    "invisible": 0x808080,
}


# ---------------------------------------------------------------------------
# Embed Builders
# ---------------------------------------------------------------------------

def _footer():
    return {"text": "Z Onliner  \u2502  Built by Arsh", "icon_url": LOGO_URL}


def _ts():
    return datetime.utcnow().strftime("%H:%M:%S UTC")


def embed_success(title, description):
    e = discord.Embed(
        title=f"\u2705  {title}",
        description=description,
        color=COLORS["success"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_footer(**_footer())
    return e


def embed_error(title, description):
    e = discord.Embed(
        title=f"\u274c  {title}",
        description=description,
        color=COLORS["danger"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_footer(**_footer())
    return e


def embed_info(title, description, color_key="info"):
    e = discord.Embed(
        title=title,
        description=description,
        color=COLORS.get(color_key, COLORS["info"]),
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_footer(**_footer())
    return e


# ---------------------------------------------------------------------------
# Bot Class
# ---------------------------------------------------------------------------

class ZOnlinerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.CustomActivity(name="Z Onliner \u2502 Built by Arsh"),
            status=discord.Status.online,
        )
        self.token_manager: Optional[TokenManager] = None

    async def setup_hook(self):
        logger.info("Syncing slash commands...")
        try:
            await self.tree.sync()
            logger.info("Slash commands synced!")
        except Exception as exc:
            logger.error(f"Failed to sync commands: {exc}")

    async def on_ready(self):
        self.token_manager = TokenManager(self.loop)
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Z Onliner is ready!")
        print()
        print("  \u2554" + "\u2550" * 50 + "\u2557")
        print("  \u2551" + " " * 12 + "\u2728  Z  O N L I N E R  \u2728" + " " * 10 + "\u2551")
        print("  \u2551" + " " * 18 + "Built by Arsh" + " " * 14 + "\u2551")
        print("  \u255a" + "\u2550" * 50 + "\u255d")
        print(f"  Logged in: {self.user}")
        print(f"  Servers: {len(self.guilds)}")
        print(f"  Time: {_ts()}")
        print()

    async def on_close(self):
        if self.token_manager:
            await self.token_manager.shutdown_all()


bot = ZOnlinerBot()


# ---------------------------------------------------------------------------
# UI Select Classes
# ---------------------------------------------------------------------------

class TokenSelectView(discord.ui.View):
    """A view containing a dropdown to select a saved token."""

    def __init__(self, tokens_info, callback_action, timeout=60):
        super().__init__(timeout=timeout)
        options = []
        for t in tokens_info[:25]:
            label = t.get("label", t.get("token_preview", "Unknown"))[:80]
            status = t.get("status", "offline").upper()
            desc = f"{status} | {t.get('token_preview', '')}"
            options.append(
                discord.SelectOption(label=label, description=desc, value=t.get("token_preview", ""))
            )
        if not options:
            options.append(discord.SelectOption(label="No tokens available", value="__none__"))

        self.select = discord.ui.Select(
            placeholder="\U0001f50d  Select an account...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = lambda interaction: callback_action(interaction, self.select.values[0])
        self.add_item(self.select)


class StatusSelectView(discord.ui.View):
    """A view containing a dropdown to select a status."""

    def __init__(self, callback_action, timeout=60):
        super().__init__(timeout=timeout)
        options = [
            discord.SelectOption(label="Online", description="Set status to Online", value="online", emoji="\U0001f7e2"),
            discord.SelectOption(label="Idle", description="Set status to Idle", value="idle", emoji="\U0001f7e1"),
            discord.SelectOption(label="Do Not Disturb", description="Set status to DND", value="dnd", emoji="\U0001f534"),
            discord.SelectOption(label="Invisible / Offline", description="Set status to Invisible", value="invisible", emoji="\u26ab"),
        ]
        self.select = discord.ui.Select(
            placeholder="\U0001f3a8  Choose a status...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = lambda interaction: callback_action(interaction, self.select.values[0])
        self.add_item(self.select)


class DurationModal(discord.ui.Modal, title="Set Duration"):
    """Modal to input duration in minutes."""

    duration_input = discord.ui.TextInput(
        label="Duration (minutes)",
        placeholder="Enter minutes (e.g. 60). Leave empty for permanent.",
        required=False,
        max_length=10,
        style=discord.TextStyle.short,
    )

    def __init__(self, on_submit):
        super().__init__()
        self._on_submit = on_submit

    async def on_submit(self, interaction: discord.Interaction):
        val = self.duration_input.value.strip()
        minutes = int(val) if val and val.isdigit() and int(val) > 0 else None
        await self._on_submit(interaction, minutes)


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

@bot.tree.command(name="help", description="Get help and list all available commands")
async def cmd_help(interaction: discord.Interaction):
    e = discord.Embed(
        title="\u2728  Z Onliner - Command List",
        description=(
            "Welcome to **Z Onliner** \u2014 the ultimate Discord token management bot. "
            "Keep your accounts online, manage statuses, and monitor everything from one place.\n\n"
            "> Built with \u2764\ufe0f by **Arsh**"
        ),
        color=COLORS["primary"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_author(name="Z Onliner", icon_url=LOGO_URL)

    cmds = [
        ("`/online`", "Bring a single account online",
         "Usage: `/online token: YOUR_TOKEN duration: 0`\n"
         "Supports: `token` or `user:pass:token` format\n"
         "Duration `0` = infinite (always online)"),
        ("`/mass-online`", "Bring multiple accounts online from a file",
         "Upload a `.txt` file with one entry per line.\n"
         "Supports: `token` or `user:pass:token` per line.\n"
         "Duration `0` = infinite."),
        ("`/tokens`", "View all saved accounts and their status",
         "Shows every account with its current status (online / offline / idle / dnd)."),
        ("`/online-tokens`", "View only accounts currently online",
         "Quick overview of all active online accounts."),
        ("`/offline-tokens`", "View only accounts that are offline",
         "See which accounts are not currently running."),
        ("`/change-status`", "Change an account\u2019s status (with optional timeout)",
         "Select an account, pick a status. Set a duration and it auto-reverts to Online after."),
        ("`/offline-token`", "Take a specific account offline",
         "Select an account from the dropdown to disconnect it."),
    ]

    for name, desc, usage in cmds:
        e.add_field(name=name, value=f"**{desc}**\n{usage}", inline=False)

    e.add_field(
        name="\U0001f4a1  Tips",
        value=(
            "\u2022 Tokens are auto-saved when you use `/online` or `/mass-online`.\n"
            "\u2022 Duration `0` means the account stays online forever (until bot restart).\n"
            "\u2022 Use `/change-status` with a time to temporarily change status, auto-reverting to online."
        ),
        inline=False,
    )

    e.set_footer(**_footer())
    await interaction.response.send_message(embed=e, ephemeral=False)


# ---------------------------------------------------------------------------
# /online
# ---------------------------------------------------------------------------

@bot.tree.command(name="online", description="Bring a single account online")
@app_commands.describe(
    token="Token or user:pass:token format",
    duration="Duration in minutes (0 = infinite, always online)",
)
async def cmd_online(interaction: discord.Interaction, token: str, duration: int = 0):
    parsed = parse_token_line(token)
    if not parsed:
        await interaction.response.send_message(
            embed=embed_error(
                "Invalid Format",
                "Could not parse a token from your input.\n\n"
                "Supported formats:\n"
                "`token`\n"
                "`user:pass:token`",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=False)
    add_token(parsed)
    result = await bot.token_manager.go_online(parsed, duration)

    if result["success"]:
        dur_text = " indefinitely" if duration == 0 else f" for {duration} minutes"
        await interaction.followup.send(
            embed=embed_success(
                "Account Online",
                f"{result['message']}\n\n\u23f1  Duration: **{duration} min**{dur_text}\n\U0001f550  Time: `{_ts()}`",
            )
        )
    else:
        await interaction.followup.send(
            embed=embed_error("Failed to Go Online", result["message"]),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# /mass-online
# ---------------------------------------------------------------------------

@bot.tree.command(name="mass-online", description="Bring multiple accounts online from a file")
@app_commands.describe(
    file="Text file: one token per line (token OR user:pass:token)",
    duration="Duration in minutes (0 = infinite, always online)",
)
async def cmd_mass_online(interaction: discord.Interaction, file: discord.Attachment, duration: int = 0):
    if not file.filename.endswith((".txt", ".text")):
        await interaction.response.send_message(
            embed=embed_error("Invalid File", "Please upload a `.txt` file with one token per line."),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=False)

    try:
        content = await file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
    except Exception as exc:
        await interaction.followup.send(
            embed=embed_error("File Error", f"Could not read file: `{exc}`"),
            ephemeral=True,
        )
        return

    result = await bot.token_manager.go_online_from_file(content, duration)

    e = discord.Embed(
        title="\U0001f680  Mass Online Results",
        color=COLORS["purple"] if result["success"] else COLORS["danger"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.description = result["message"]

    if "results" in result and result["results"]:
        ok_lines = [f"  \u2705 {r['message']}" for r in result["results"] if r["success"]]
        fail_lines = [f"  \u274c {r['message']}" for r in result["results"] if not r["success"]]
        if ok_lines:
            e.add_field(
                name=f"\u2705 Successful ({len(ok_lines)})",
                value="\n".join(ok_lines[:10]) + ("\n  ..." if len(ok_lines) > 10 else ""),
                inline=False,
            )
        if fail_lines:
            e.add_field(
                name=f"\u274c Failed ({len(fail_lines)})",
                value="\n".join(fail_lines[:10]) + ("\n  ..." if len(fail_lines) > 10 else ""),
                inline=False,
            )

    dur_text = "indefinite" if duration == 0 else f"{duration} minutes"
    e.add_field(name="\u23f1  Duration", value=f"**{dur_text}**", inline=True)
    e.add_field(name="\U0001f550  Time", value=f"`{_ts()}`", inline=True)
    e.set_footer(**_footer())
    await interaction.followup.send(embed=e)


# ---------------------------------------------------------------------------
# /tokens
# ---------------------------------------------------------------------------

@bot.tree.command(name="tokens", description="View all saved accounts and their status")
async def cmd_tokens(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    tokens_info = bot.token_manager.get_all_tokens()
    online_count = sum(1 for t in tokens_info if t["status"] == "online")
    offline_count = len(tokens_info) - online_count

    e = discord.Embed(
        title=f"\U0001f4cb  All Accounts  |  \U0001f7e2 {online_count} Online  |  \u26ab {offline_count} Offline",
        color=COLORS["primary"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_author(name="Z Onliner", icon_url=LOGO_URL)

    if not tokens_info:
        e.description = "No tokens saved yet. Use `/online <token>` to add tokens."
    else:
        for i, t in enumerate(tokens_info[:25], 1):
            status = t.get("status", "offline").lower()
            mark = STATUS_MARK.get(status, "\u26ab")
            label = t.get("label", t.get("token_preview", "Unknown"))
            token_prev = t.get("token_preview", "???...")
            ready = "Yes" if t.get("ready") else "No"
            e.add_field(
                name=f"{mark}  #{i}  {label}",
                value=f"`Token: {token_prev}`\n**Status:** {status.upper()}  |  **Ready:** {ready}",
                inline=False,
            )
        if len(tokens_info) > 25:
            e.add_field(name="...", value=f"and {len(tokens_info) - 25} more. Showing first 25.", inline=False)

    e.set_footer(**_footer())
    await interaction.followup.send(embed=e)


# ---------------------------------------------------------------------------
# /online-tokens
# ---------------------------------------------------------------------------

@bot.tree.command(name="online-tokens", description="View only the accounts that are currently online")
async def cmd_online_tokens(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    tokens_info = bot.token_manager.get_online_tokens()

    e = discord.Embed(
        title=f"\U0001f7e2  Online Accounts  ({len(tokens_info)})",
        color=COLORS["success"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_author(name="Z Onliner", icon_url=LOGO_URL)

    if not tokens_info:
        e.description = "No accounts are currently online. Use `/online <token>` to bring accounts online."
    else:
        for i, t in enumerate(tokens_info[:25], 1):
            label = t.get("label", t.get("token_preview", "Unknown"))
            token_prev = t.get("token_preview", "???...")
            e.add_field(
                name=f"\U0001f7e2  #{i}  {label}",
                value=f"`Token: {token_prev}`  |  **Status:** ONLINE",
                inline=False,
            )

    e.set_footer(**_footer())
    await interaction.followup.send(embed=e)


# ---------------------------------------------------------------------------
# /offline-tokens
# ---------------------------------------------------------------------------

@bot.tree.command(name="offline-tokens", description="View only the accounts that are offline")
async def cmd_offline_tokens(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    tokens_info = bot.token_manager.get_offline_tokens()

    e = discord.Embed(
        title=f"\u26ab  Offline Accounts  ({len(tokens_info)})",
        color=COLORS["offline"],
        timestamp=discord.utils.utcnow(),
    )
    e.set_thumbnail(url=LOGO_URL)
    e.set_author(name="Z Onliner", icon_url=LOGO_URL)

    if not tokens_info:
        e.description = "All accounts are online! \U0001f389"
    else:
        for i, t in enumerate(tokens_info[:25], 1):
            label = t.get("label", t.get("token_preview", "Unknown"))
            token_prev = t.get("token_preview", "???...")
            e.add_field(
                name=f"\u26ab  #{i}  {label}",
                value=f"`Token: {token_prev}`  |  **Status:** OFFLINE",
                inline=False,
            )

    e.set_footer(**_footer())
    await interaction.followup.send(embed=e)


# ---------------------------------------------------------------------------
# /change-status
# ---------------------------------------------------------------------------

@bot.tree.command(name="change-status", description="Change an account's status (online, idle, dnd, offline)")
async def cmd_change_status(interaction: discord.Interaction):
    tokens_info = bot.token_manager.get_all_tokens()
    if not tokens_info:
        await interaction.response.send_message(
            embed=embed_error("No Tokens", "No saved tokens found. Use `/online <token>` first."),
            ephemeral=True,
        )
        return

    async def on_token_selected(interaction: discord.Interaction, selected_value: str):
        if selected_value == "__none__":
            await interaction.response.edit_message(content="No selection made.", view=None)
            return
        chosen_preview = selected_value

        async def on_status_selected(interaction: discord.Interaction, new_status: str):
            async def on_duration_submitted(interaction: discord.Interaction, minutes):
                await interaction.response.defer(ephemeral=False)
                result = await bot.token_manager.change_status(chosen_preview, new_status, duration=minutes)

                if result["success"]:
                    dur_text = f" for {minutes} min (auto-reverts to Online)" if minutes else " permanently"
                    await interaction.followup.send(
                        embed=embed_success(
                            "Status Changed",
                            f"{result['message']}{dur_text}\n\n\U0001f550  Time: `{_ts()}`",
                        )
                    )
                else:
                    await interaction.followup.send(
                        embed=embed_error("Status Change Failed", result["message"]),
                        ephemeral=True,
                    )

            modal = DurationModal(on_submit=on_duration_submitted)
            await interaction.response.send_modal(modal)

        info_e = discord.Embed(
            title="\U0001f3a8  Change Status",
            description=(
                f"Selected account: **{chosen_preview}**\n\n"
                f"Choose the new status below.\n"
                f"After selecting, you'll be asked for an optional **duration**.\n"
                f"If a duration is set, the account will **auto-revert to Online** after the time expires."
            ),
            color=COLORS["purple"],
            timestamp=discord.utils.utcnow(),
        )
        info_e.set_thumbnail(url=LOGO_URL)
        info_e.set_footer(**_footer())

        view = StatusSelectView(on_status_selected, timeout=60)
        await interaction.response.edit_message(embed=info_e, view=view)

    view = TokenSelectView(tokens_info, on_token_selected, timeout=60)
    info_e = discord.Embed(
        title="\U0001f50d  Select an Account",
        description="Choose an account from the dropdown below to change its status.",
        color=COLORS["info"],
        timestamp=discord.utils.utcnow(),
    )
    info_e.set_thumbnail(url=LOGO_URL)
    info_e.set_footer(**_footer())
    await interaction.response.send_message(embed=info_e, view=view, ephemeral=False)


# ---------------------------------------------------------------------------
# /offline-token
# ---------------------------------------------------------------------------

@bot.tree.command(name="offline-token", description="Take a specific account offline")
async def cmd_offline_token(interaction: discord.Interaction):
    tokens_info = bot.token_manager.get_all_tokens()
    if not tokens_info:
        await interaction.response.send_message(
            embed=embed_error("No Tokens", "No saved tokens found. Use `/online <token>` first."),
            ephemeral=True,
        )
        return

    async def on_token_selected(interaction: discord.Interaction, selected_value: str):
        if selected_value == "__none__":
            await interaction.response.edit_message(content="No selection made.", view=None)
            return

        await interaction.response.defer(ephemeral=False)
        result = await bot.token_manager.go_offline(selected_value)

        if result["success"]:
            await interaction.followup.send(
                embed=embed_success(
                    "Account Offline",
                    f"{result['message']}\n\n\U0001f550  Time: `{_ts()}`",
                )
            )
        else:
            await interaction.followup.send(
                embed=embed_error("Failed", result["message"]),
                ephemeral=True,
            )

    view = TokenSelectView(tokens_info, on_token_selected, timeout=60)
    info_e = discord.Embed(
        title="\u26ab  Take Account Offline",
        description="Choose an account from the dropdown below to disconnect it and make it offline.",
        color=COLORS["danger"],
        timestamp=discord.utils.utcnow(),
    )
    info_e.set_thumbnail(url=LOGO_URL)
    info_e.set_footer(**_footer())
    await interaction.response.send_message(embed=info_e, view=view, ephemeral=False)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        bot.run(BOT_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
