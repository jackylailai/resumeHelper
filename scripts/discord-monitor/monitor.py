#!/usr/bin/env python3
"""
Standalone Discord monitoring script.

Reads DISCORD_BOT_TOKEN from ~/.claude/channels/discord/.env (same token
the Claude Code MCP plugin uses). Polls one or more Discord channels and
optionally auto-replies via the Claude API.

Usage:
    python3 monitor.py [--channel CHANNEL_ID] [--interval 30] [--reply]

Options:
    --channel    Channel ID to monitor (default: 1241933442434732128)
    --interval   Poll interval in seconds (default: 30)
    --reply      Enable auto-reply via Claude API (requires ANTHROPIC_API_KEY)
    --limit      Messages to fetch per poll (default: 10)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DISCORD_ENV = Path.home() / ".claude" / "channels" / "discord" / ".env"
DISCORD_API = "https://discord.com/api/v10"

DEFAULT_CHANNEL = "1241933442434732128"
DEFAULT_INTERVAL = 30  # seconds


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


# ---------------------------------------------------------------------------
# Discord API helpers
# ---------------------------------------------------------------------------

def discord_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (resumeHelper-monitor, 1.0)",
    }


def fetch_messages(
    token: str,
    channel_id: str,
    after: str | None = None,
    limit: int = 10,
) -> list[dict]:
    params: dict[str, str | int] = {"limit": limit}
    if after:
        params["after"] = after
    resp = requests.get(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=discord_headers(token),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    # Discord returns newest-first; reverse so we process oldest-first
    return list(reversed(resp.json()))


def send_message(token: str, channel_id: str, content: str) -> dict:
    resp = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=discord_headers(token),
        json={"content": content},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_me(token: str) -> dict:
    resp = requests.get(
        f"{DISCORD_API}/users/@me",
        headers=discord_headers(token),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Claude API auto-reply (optional)
# ---------------------------------------------------------------------------

def claude_reply(message_text: str, anthropic_key: str) -> str:
    import anthropic  # only imported when --reply is set

    client = anthropic.Anthropic(api_key=anthropic_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    "你是 resumeHelper 專案助理，回答要簡短。以下是 Discord 收到的訊息，"
                    f"請回覆：\n\n{message_text}"
                ),
            }
        ],
    )
    return response.content[0].text  # type: ignore[index]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Discord monitor for resumeHelper")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="Channel ID to monitor")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Poll interval (s)")
    parser.add_argument("--reply", action="store_true", help="Auto-reply via Claude API")
    parser.add_argument("--limit", type=int, default=10, help="Messages per poll")
    args = parser.parse_args()

    # Load credentials
    env = load_env(DISCORD_ENV)
    token = env.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        print(f"ERROR: DISCORD_BOT_TOKEN not found in {DISCORD_ENV}", file=sys.stderr)
        print("Run /discord:configure in Claude Code first, or set DISCORD_BOT_TOKEN env var.")
        sys.exit(1)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if args.reply and not anthropic_key:
        print("ERROR: --reply requires ANTHROPIC_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    # Identify the bot
    try:
        me = get_me(token)
        bot_id = me["id"]
        bot_tag = f"{me['username']}#{me.get('discriminator','0')}"
    except Exception as e:
        print(f"ERROR: Cannot authenticate with Discord: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[{_ts()}] 監聽上線 — bot: {bot_tag} ({bot_id})")
    print(f"[{_ts()}] 頻道: {args.channel}  |  間隔: {args.interval}s  |  自動回覆: {args.reply}")
    print("─" * 60)

    last_id: str | None = None

    # Seed last_id from latest message so we only react to NEW messages
    try:
        seed = fetch_messages(token, args.channel, limit=1)
        if seed:
            last_id = seed[-1]["id"]
            print(f"[{_ts()}] 最新訊息 ID 已同步 ({last_id})，只處理之後的新訊息")
    except Exception as e:
        print(f"[{_ts()}] WARNING: 無法取得初始訊息: {e}")

    while True:
        try:
            new_messages = fetch_messages(
                token, args.channel, after=last_id, limit=args.limit
            )
        except requests.HTTPError as e:
            print(f"[{_ts()}] HTTP error: {e}")
            time.sleep(args.interval)
            continue
        except Exception as e:
            print(f"[{_ts()}] Error: {e}")
            time.sleep(args.interval)
            continue

        for msg in new_messages:
            last_id = msg["id"]
            author = msg.get("author", {})
            username = author.get("username", "?")
            user_id = author.get("id", "")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")

            # Skip own messages
            if user_id == bot_id:
                continue

            print(f"[{_ts()}] 新訊息 from {username}: {content[:120]}")

            # Auto-reply if flag set and message mentions the bot
            if args.reply and bot_id in content:
                try:
                    reply_text = claude_reply(content, anthropic_key)
                    send_message(token, args.channel, reply_text)
                    print(f"[{_ts()}] 已回覆: {reply_text[:80]}…")
                except Exception as e:
                    print(f"[{_ts()}] 回覆失敗: {e}")

        if not new_messages:
            print(f"[{_ts()}] 無新訊息", end="\r")

        time.sleep(args.interval)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 監聽已停止")
