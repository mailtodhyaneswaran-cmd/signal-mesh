"""
test_telegram.py — send a sample Signal Mesh notification to verify
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are wired up correctly.

Usage:
  set TELEGRAM_BOT_TOKEN=<token>
  set TELEGRAM_CHAT_ID=<chat_id>
  python int/bin/test_telegram.py
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from lib_env import load_dotenv


def build_sample_message() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "<b>📊 Signal Mesh — TEST MESSAGE</b>",
        f"{now}  ·  agents=[claude + gemini]",
        "",
        "<b>Results (ranked by score):</b>",
        "  🟢 <b>NVDA</b>  BUY   74.2  B:14 S:3  H:8",
        "  🟢 <b>AAPL</b>  BUY   69.8  B:13 S:4  H:8",
        "  🟡 <b>MSFT</b>  HOLD  58.7  B:11 S:7  H:7",
        "  🟡 <b>META</b>  HOLD  52.1  B:10 S:8  H:7",
        "  🔴 <b>TSLA</b>  SELL  41.3  B:5  S:12 H:8  ⚠️2skip",
        "",
        "🏆 <b>Top pick: NVDA</b>  (score 74.2, 14/25 BUY votes)",
        "",
        "<b>Agent Reliability:</b>",
        "  ✅ claude: 50/50 proper replies (100%)",
        "  ⚠️ gemini: 48/50 proper replies (96%)",
        "",
        "<i>This is a test message — no real analysis was run.</i>",
    ])


def main():
    load_dotenv()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id   = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token:
        print("[ERROR] TELEGRAM_BOT_TOKEN is not set.")
        return
    if not chat_id:
        print("[ERROR] TELEGRAM_CHAT_ID is not set.")
        return

    print(f"Sending test message to chat_id={chat_id} ...")
    text = build_sample_message()
    data = urllib.parse.urlencode({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }).encode()

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data, method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            print(f"✅ Test message sent!  message_id={msg_id}")
        else:
            print(f"❌ Telegram API returned ok=false:")
            print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ HTTP {e.code}: {body}")
    except Exception as e:
        print(f"❌ Request failed: {e}")


if __name__ == "__main__":
    main()
