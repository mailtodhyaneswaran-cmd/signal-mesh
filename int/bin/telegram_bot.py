"""
telegram_bot.py — Signal Mesh Telegram bot.

Listens for commands and runs on-demand stock analysis, replying with results.

Commands:
  /ticker <STOCK>            — analyse with Claude (default)
  /ticker <STOCK> claude     — analyse with Claude only
  /ticker <STOCK> gemini     — analyse with Gemini only
  /ticker <STOCK> mistral    — analyse with Mistral only
  /ticker <STOCK> all        — analyse with all 3 agents
  /help                      — show usage

<STOCK> is a ticker symbol recognised by yfinance:
  US stocks : NVDA, AAPL, MSFT
  EU stocks : ASML.AS, SAP.DE, MC.PA   (exchange suffix required for non-US)
  ETFs      : SPY, QQQ, IWDA.AS

Usage:
  python int/bin/telegram_bot.py

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the project-root .env file.
The bot only accepts commands from the configured TELEGRAM_CHAT_ID for security.
"""

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from lib_env import load_dotenv

load_dotenv()

BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT   = os.environ.get("TELEGRAM_CHAT_ID",   "").strip()
VALID_AGENTS   = {"claude", "gemini", "mistral", "all"}
POLL_TIMEOUT   = 30   # seconds for long-poll — Telegram holds the connection open


# ── Telegram API helpers ──────────────────────────────────────────────────────

def _api(method: str, params: dict, timeout: int = 35) -> dict:
    data = urllib.parse.urlencode(params).encode()
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req  = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def send(chat_id: str, text: str) -> None:
    try:
        _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print(f"[Bot] send failed: {e}")


def get_updates(offset: int) -> list:
    try:
        result = _api(
            "getUpdates",
            {"offset": offset, "timeout": POLL_TIMEOUT, "allowed_updates": ["message"]},
            timeout=POLL_TIMEOUT + 5,
        )
        return result.get("result", [])
    except Exception:
        return []


# ── Analysis runner (called from a background thread) ────────────────────────

def _run_analysis(chat_id: str, ticker: str, agent_name: str) -> None:
    from lib_agents_claude import ClaudeAgent
    from lib_agents_gemini import GeminiAgent
    from lib_agents_mistral import MistralAgent
    from signal_mesh_orchestrator import fetch_stock_data, run_all_prompts_for_ticker

    # Build agent list
    if agent_name == "all":
        agents = [ClaudeAgent(verbose=False), GeminiAgent(verbose=False), MistralAgent(verbose=False)]
    elif agent_name == "gemini":
        agents = [GeminiAgent(verbose=False)]
    elif agent_name == "mistral":
        agents = [MistralAgent(verbose=False)]
    else:
        agents = [ClaudeAgent(verbose=False)]

    agents_label = " + ".join(a.name for a in agents)

    # Fetch market data
    send(chat_id, f"⏳ Fetching market data for <b>{ticker}</b>...")
    stock_data = fetch_stock_data(ticker)
    if "error" in stock_data:
        send(chat_id, f"❌ Could not fetch data for <b>{ticker}</b>: {stock_data['error']}\n\n"
                      f"<i>Check the ticker symbol — EU stocks need an exchange suffix, e.g. ASML.AS, SAP.DE</i>")
        return

    send(chat_id,
         f"📈 Data fetched for <b>{ticker}</b>:\n"
         f"  Price: ${stock_data['price']}  ·  RSI: {stock_data['rsi']}  ·  Vol: {stock_data['vol_trend']}\n\n"
         f"Running 25 prompts with [{agents_label}]...\n"
         f"<i>This takes a few minutes — sit tight.</i>")

    # Run analysis
    try:
        result = run_all_prompts_for_ticker(ticker, stock_data, agents=agents, euro=False)
    except Exception as e:
        send(chat_id, f"❌ Analysis failed for <b>{ticker}</b>: {e}")
        return

    # Format result
    sig   = result["final_signal"]
    score = result["weighted_score"]
    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(sig, "⚪")
    total = result["buy_count"] + result["sell_count"] + result["hold_count"]
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cat_lines = "\n".join(
        f"  {c.split('_')[-1][:4].upper()}: {v:.1f}"
        for c, v in result.get("category_scores", {}).items()
    )

    reliability_lines = []
    for name, stats in result.get("agent_reliability", {}).items():
        t    = stats["proper"] + stats["failed"]
        pct  = round(stats["proper"] / t * 100) if t else 0
        icon = "✅" if pct >= 90 else "⚠️" if pct >= 70 else "❌"
        reliability_lines.append(f"  {icon} {name}: {stats['proper']}/{t} ({pct}%)")

    lines = [
        f"<b>📊 Signal Mesh — {ticker}</b>",
        f"{now}  ·  [{agents_label}]",
        "",
        f"{emoji} <b>{sig}</b>  score: {score:.1f}",
        f"Votes: {result['buy_count']} BUY  ·  {result['sell_count']} SELL  ·  {result['hold_count']} HOLD  ({total} total)",
        "",
        "<b>Category Breakdown:</b>",
        cat_lines,
    ]
    if reliability_lines:
        lines += ["", "<b>Agent Reliability:</b>"] + reliability_lines

    send(chat_id, "\n".join(lines))
    print(f"[Bot] Analysis complete for {ticker} ({agent_name}) — result sent to chat.")


# ── Command handlers ──────────────────────────────────────────────────────────

def handle_ticker(chat_id: str, args: list) -> None:
    if not args:
        send(chat_id,
             "Usage: /ticker &lt;STOCK&gt; [claude|gemini|mistral|all]\n\n"
             "Examples:\n"
             "  /ticker NVDA\n"
             "  /ticker ASML.AS all\n"
             "  /ticker AAPL gemini")
        return

    ticker     = args[0].upper()
    agent_name = args[1].lower() if len(args) > 1 else "claude"

    if agent_name not in VALID_AGENTS:
        send(chat_id,
             f"Unknown agent: <b>{agent_name}</b>\n"
             f"Valid options: claude · gemini · mistral · all")
        return

    label = "Claude + Gemini + Mistral" if agent_name == "all" else agent_name.title()
    send(chat_id, f"🔍 Starting analysis for <b>{ticker}</b> with [{label}]...")

    thread = threading.Thread(
        target=_run_analysis,
        args=(chat_id, ticker, agent_name),
        name=f"analysis-{ticker}",
        daemon=True,
    )
    thread.start()


HELP_TEXT = (
    "<b>Signal Mesh Bot</b>\n\n"
    "<b>Commands:</b>\n"
    "  /ticker &lt;STOCK&gt;          — analyse with Claude (default)\n"
    "  /ticker &lt;STOCK&gt; all       — analyse with all 3 agents\n"
    "  /ticker &lt;STOCK&gt; gemini    — analyse with Gemini only\n"
    "  /ticker &lt;STOCK&gt; mistral   — analyse with Mistral only\n"
    "  /ticker &lt;STOCK&gt; claude    — analyse with Claude only\n\n"
    "<b>Ticker format (yfinance):</b>\n"
    "  US stocks  →  NVDA, AAPL, MSFT\n"
    "  EU stocks  →  ASML.AS, SAP.DE, MC.PA\n"
    "  ETFs       →  SPY, QQQ, IWDA.AS\n\n"
    "<i>Analysis takes 2–5 minutes. You'll get a reply when it's done.</i>"
)


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env", file=sys.stderr)
        sys.exit(1)
    if not ALLOWED_CHAT:
        print("Error: TELEGRAM_CHAT_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    print("[Bot] Signal Mesh Telegram bot started.")
    print(f"[Bot] Accepting commands from chat_id={ALLOWED_CHAT}")
    print("[Bot] Send /ticker <STOCK> [agent] to trigger analysis.")
    print("[Bot] Press Ctrl+C to stop.\n")

    offset = 0
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1

            msg     = update.get("message", {})
            text    = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if not text or not chat_id:
                continue

            # Security: only respond to the configured chat
            if chat_id != ALLOWED_CHAT:
                print(f"[Bot] Ignored message from unauthorised chat_id={chat_id}")
                continue

            parts   = text.split()
            command = parts[0].lower().split("@")[0]   # strip @botname suffix
            args    = parts[1:]

            print(f"[Bot] Command: {text!r}  from chat_id={chat_id}")

            if command == "/ticker":
                handle_ticker(chat_id, args)
            elif command in ("/start", "/help"):
                send(chat_id, HELP_TEXT)
            else:
                send(chat_id, f"Unknown command: {command}\nSend /help to see available commands.")

        if not updates:
            time.sleep(1)


if __name__ == "__main__":
    main()
