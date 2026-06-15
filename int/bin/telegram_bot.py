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
import sqlite3
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

import html
from lib_get_state import (
    create_session, save_run, get_baseline, get_previous_run,
    mark_session_complete, cancel_session, list_active_sessions,
    get_session, get_session_runs, get_run_count, get_active_session_for_ticker,
    create_get2_meta, update_get2_position, get_get2_meta,
    record_get2_trade, get_get2_trades, list_active_get2_sessions,
    get_active_get2_session_for_ticker,
)
from lib_market_hours import is_market_open, next_market_open
from lib_telegram_format import format_report, format_pulse, format_summary
try:
    from lib_ibkr import get_client as get_ibkr_client, IBKR_AVAILABLE
except ImportError:
    IBKR_AVAILABLE = False
    get_ibkr_client = None

BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
MAIN_CHAT    = os.environ.get("TELEGRAM_CHAT_ID",   "").strip()
_raw_wl      = os.environ.get("TELEGRAM_WHITELIST", "").strip()
WHITELIST    = {c.strip() for c in _raw_wl.split(",") if c.strip()} if _raw_wl else set()
ALLOWED_CHATS = {MAIN_CHAT} | WHITELIST   # all chat IDs permitted to use the bot
VALID_AGENTS  = {"claude", "gemini", "mistral", "all"}
POLL_TIMEOUT  = 30   # seconds for long-poll — Telegram holds the connection open

_active_sessions: dict = {}   # session_id -> threading.Thread


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
        print(f"[Bot] send failed to {chat_id}: {e}")


def broadcast(chat_ids: list, text: str) -> None:
    for cid in chat_ids:
        send(cid, text)


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

def _run_analysis(requester_id: str, notify_chats: list, ticker: str, agent_name: str) -> None:
    from lib_agents_claude import ClaudeAgent
    from lib_agents_gemini import GeminiAgent
    from lib_agents_mistral import MistralAgent
    from signal_mesh_orchestrator import fetch_stock_data, run_bulk_prompts_for_ticker

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
    by_tag = f"  <i>(requested by {requester_id})</i>" if requester_id != MAIN_CHAT else ""

    # Fetch market data
    broadcast(notify_chats, f"⏳ Fetching market data for <b>{ticker}</b>...{by_tag}")
    stock_data = fetch_stock_data(ticker)
    if "error" in stock_data:
        broadcast(notify_chats,
                  f"❌ Could not fetch data for <b>{ticker}</b>: {stock_data['error']}\n\n"
                  f"<i>Check the ticker symbol — EU stocks need an exchange suffix, e.g. ASML.AS, SAP.DE</i>")
        return

    broadcast(notify_chats,
              f"📈 Data fetched for <b>{ticker}</b>:{by_tag}\n"
              f"  Price: ${stock_data['price']}  ·  RSI: {stock_data['rsi']}  ·  Vol: {stock_data['vol_trend']}\n\n"
              f"Running bulk analysis with [{agents_label}]...\n"
              f"<i>This takes a few minutes — sit tight.</i>")

    # Run analysis
    try:
        result = run_bulk_prompts_for_ticker(ticker, stock_data, agents=agents, euro=False)
    except Exception as e:
        broadcast(notify_chats, f"❌ Analysis failed for <b>{ticker}</b>: {e}")
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
        f"{now}  ·  [{agents_label}]{by_tag}",
        "",
        f"{emoji} <b>{sig}</b>  score: {score:.1f}",
        f"Votes: {result['buy_count']} BUY  ·  {result['sell_count']} SELL  ·  {result['hold_count']} HOLD  ({total} total)",
        "",
        "<b>Category Breakdown:</b>",
        cat_lines,
    ]
    if reliability_lines:
        lines += ["", "<b>Agent Reliability:</b>"] + reliability_lines

    broadcast(notify_chats, "\n".join(lines))
    print(f"[Bot] Analysis complete for {ticker} ({agent_name}) — sent to {notify_chats}.")


# ── /get monitoring loop ──────────────────────────────────────────────────────

def _run_get_loop(
    session_id: str,
    requester_id: str,
    notify_chats: list,
    ticker: str,
    agent_name: str,
    total_runs: int,
    interval_min: int,
    quiet: bool,
    start_run: int = 1,
) -> None:
    """Background thread that runs N analysis passes for a /get session."""
    from signal_mesh_orchestrator import fetch_single_ticker_data, analyze_single_ticker
    import datetime as _dt

    run_n = start_run
    while run_n <= total_runs:
        # ── Cancellation check ────────────────────────────────────────────
        sess = get_session(session_id)
        if sess and sess["status"] == "cancelled":
            broadcast(notify_chats, f"🛑 <b>{ticker}</b> monitoring cancelled at run {run_n}/{total_runs}.")
            return

        # ── Market hours gate ─────────────────────────────────────────────
        if not is_market_open(ticker):
            next_open  = next_market_open(ticker)
            next_str   = next_open.strftime("%H:%M UTC")
            broadcast(notify_chats, f"💤 <b>{ticker}</b> market closed. Pausing. Resuming at {next_str}")
            now_utc    = _dt.datetime.now(_dt.timezone.utc)
            sleep_secs = max(0.0, (next_open - now_utc).total_seconds())
            # Sleep in up-to-1-hour chunks so we can re-check for cancellation
            slept = 0.0
            while slept < sleep_secs:
                chunk = min(3600.0, sleep_secs - slept)
                time.sleep(chunk)
                slept += chunk
                # Re-check cancellation after each chunk
                sess = get_session(session_id)
                if sess and sess["status"] == "cancelled":
                    broadcast(notify_chats, f"🛑 <b>{ticker}</b> monitoring cancelled while market was closed.")
                    return
            # Do not increment run_n — retry the same run number
            continue

        # ── Fetch market data ─────────────────────────────────────────────
        stock_data = fetch_single_ticker_data(ticker)
        if "error" in stock_data:
            broadcast(
                notify_chats,
                f"❌ <b>{ticker}</b> data fetch failed (run {run_n}): {stock_data['error']}",
            )
            if run_n < total_runs:
                time.sleep(interval_min * 60)
            run_n += 1
            continue

        # ── Run analysis ──────────────────────────────────────────────────
        result = analyze_single_ticker(
            ticker, stock_data, agent_name, run_n, session_id, interval_min, total_runs
        )

        if "error" in result and "signal" not in result:
            broadcast(
                notify_chats,
                f"⚠️ <b>{ticker}</b> analysis error (run {run_n}): {result.get('error')}",
            )
        else:
            # Persist to DB
            save_run(session_id, run_n, result, stock_data.get("price", 0))

            sig_changed = result.get("signal_changed_from_previous", False)
            score_delta = abs(result.get("score_delta_vs_baseline", 0) or 0)
            send_full   = (not quiet) or run_n == 1 or sig_changed or score_delta >= 5

            by_tag = f"  <i>(req by {requester_id})</i>" if requester_id != MAIN_CHAT else ""

            if send_full:
                msgs = format_report(result, run_n, total_runs, interval_min)
                for i, msg in enumerate(msgs):
                    out = msg + by_tag if (by_tag and i == 0) else msg
                    broadcast(notify_chats, out)
            else:
                broadcast(notify_chats, format_pulse(result, run_n, total_runs) + by_tag)

        # ── Sleep before next run ─────────────────────────────────────────
        run_n += 1
        if run_n <= total_runs:
            time.sleep(interval_min * 60)

    # ── Session complete ──────────────────────────────────────────────────
    mark_session_complete(session_id)
    _active_sessions.pop(session_id, None)

    runs    = get_session_runs(session_id)
    session = get_session(session_id)
    if runs and session:
        run_dicts = [
            {"signal": r["signal"], "price": r["price"], "factor_score": r["factor_score"]}
            for r in runs
        ]
        broadcast(notify_chats, format_summary(session, run_dicts))

    broadcast(notify_chats, f"✅ <b>{ticker}</b> monitoring complete ({total_runs} runs finished).")
    print(f"[Bot] /get session {session_id} for {ticker} complete.")


# ── /get2 automated trading loop ─────────────────────────────────────────────

def _run_get2_loop(
    session_id: str,
    requester_id: str,
    notify_chats: list,
    ticker: str,
    agent_name: str,
    total_runs: int,
    interval_min: int,
    budget: float,
    start_run: int = 1,
) -> None:
    from signal_mesh_orchestrator import fetch_single_ticker_data, analyze_single_ticker
    import datetime as _dt

    if not IBKR_AVAILABLE or get_ibkr_client is None:
        broadcast(notify_chats, "⚠️ IBKR not available. Run: pip install ib_insync")
        cancel_session(session_id)
        return

    ibkr = get_ibkr_client()
    if not ibkr.is_connected():
        if not ibkr.connect():
            broadcast(notify_chats, f"❌ <b>{ticker}</b> /get2 aborted — could not connect to IBKR. Start IB Gateway first.")
            cancel_session(session_id)
            return

    meta = get_get2_meta(session_id)
    position_status   = meta["position_status"]   if meta else "none"
    position_qty      = meta["position_qty"]      if meta else 0.0
    position_buy_price = meta["position_buy_price"] if meta else 0.0

    run_n = start_run
    while run_n <= total_runs:
        sess = get_session(session_id)
        if sess and sess["status"] == "cancelled":
            if position_status == "long":
                try:
                    res = ibkr.sell_position(ticker)
                    pnl = res.get("pnl", 0.0)
                    record_get2_trade(
                        session_id, run_n, "SELL", ticker,
                        res.get("quantity", 0), res.get("fill_price", 0) * res.get("quantity", 0),
                        res.get("fill_price", 0), res.get("order_id"), res.get("status"), pnl,
                    )
                    update_get2_position(session_id, "none", 0, 0)
                    broadcast(notify_chats,
                              f"🛑 <b>{ticker}</b> /get2 cancelled — liquidated position.\n"
                              f"Fill: ${res.get('fill_price', 0):.2f}  ·  P&amp;L: ${pnl:.2f}")
                except Exception as e:
                    broadcast(notify_chats,
                              f"🛑 <b>{ticker}</b> /get2 cancelled — sell failed: {html.escape(str(e))}\n"
                              f"<b>Close position manually in IBKR.</b>")
            else:
                broadcast(notify_chats, f"🛑 <b>{ticker}</b> /get2 cancelled at run {run_n}/{total_runs}.")
            return

        if not is_market_open(ticker):
            next_open = next_market_open(ticker)
            next_str  = next_open.strftime("%H:%M UTC")
            broadcast(notify_chats, f"💤 <b>{ticker}</b> market closed. Pausing. Resuming at {next_str}")
            now_utc    = _dt.datetime.now(_dt.timezone.utc)
            sleep_secs = max(0.0, (next_open - now_utc).total_seconds())
            slept = 0.0
            while slept < sleep_secs:
                chunk = min(3600.0, sleep_secs - slept)
                time.sleep(chunk)
                slept += chunk
                sess = get_session(session_id)
                if sess and sess["status"] == "cancelled":
                    broadcast(notify_chats, f"🛑 <b>{ticker}</b> /get2 cancelled while market was closed.")
                    return
            continue

        stock_data = fetch_single_ticker_data(ticker)
        if "error" in stock_data:
            broadcast(notify_chats,
                      f"❌ <b>{ticker}</b> data fetch failed (run {run_n}): {html.escape(str(stock_data['error']))}")
            run_n += 1
            if run_n <= total_runs:
                time.sleep(interval_min * 60)
            continue

        result = analyze_single_ticker(ticker, stock_data, agent_name, run_n, session_id, interval_min, total_runs)
        price  = float(stock_data.get("price", 0))
        signal = result.get("signal", "HOLD")
        score  = result.get("factor_score", 50)

        save_run(session_id, run_n, result, price)

        if signal == "BUY" and position_status == "none":
            try:
                res = ibkr.buy_dollars(ticker, budget)
                if res.get("status") in ("Filled", "Submitted", "PreSubmitted"):
                    qty        = float(res.get("quantity", 0))
                    fill_price = float(res.get("fill_price", 0))
                    order_id   = res.get("order_id")
                    record_get2_trade(
                        session_id, run_n, "BUY", ticker,
                        qty, budget, fill_price, order_id, res.get("status"), 0.0,
                    )
                    update_get2_position(session_id, "long", qty, fill_price)
                    position_status    = "long"
                    position_qty       = qty
                    position_buy_price = fill_price
                    broadcast(notify_chats,
                              f"🟢 <b>BUY executed</b>  ·  {ticker}  run {run_n}/{total_runs}\n"
                              f"Qty: {qty}  ·  Fill: ${fill_price:.2f}  ·  Order: <code>{order_id}</code>")
                else:
                    broadcast(notify_chats,
                              f"⚠️ <b>{ticker}</b> BUY order status: {html.escape(str(res.get('status', 'unknown')))}\n"
                              f"Position not updated. Check IBKR.")
            except Exception as e:
                broadcast(notify_chats,
                          f"❌ <b>{ticker}</b> BUY failed (run {run_n}): {html.escape(str(e))}")

        elif signal == "SELL" and position_status == "long":
            try:
                res = ibkr.sell_position(ticker)
                if res.get("status") in ("Filled", "Submitted", "PreSubmitted"):
                    fill_price = float(res.get("fill_price", 0))
                    qty        = float(res.get("quantity", 0))
                    pnl        = float(res.get("pnl", 0))
                    order_id   = res.get("order_id")
                    record_get2_trade(
                        session_id, run_n, "SELL", ticker,
                        qty, qty * fill_price, fill_price, order_id, res.get("status"), pnl,
                    )
                    update_get2_position(session_id, "none", 0, 0)
                    position_status    = "none"
                    position_qty       = 0.0
                    position_buy_price = 0.0
                    pnl_sign = "+" if pnl >= 0 else ""
                    broadcast(notify_chats,
                              f"🔴 <b>SELL executed</b>  ·  {ticker}  run {run_n}/{total_runs}\n"
                              f"Qty: {qty}  ·  Fill: ${fill_price:.2f}  ·  P&amp;L: {pnl_sign}${pnl:.2f}  ·  Order: <code>{order_id}</code>")
                else:
                    broadcast(notify_chats,
                              f"⚠️ <b>{ticker}</b> SELL order status: {html.escape(str(res.get('status', 'unknown')))}\n"
                              f"<b>Close position manually in IBKR.</b>")
            except Exception as e:
                broadcast(notify_chats,
                          f"❌ <b>{ticker}</b> SELL failed (run {run_n}): {html.escape(str(e))}\n"
                          f"<b>Close position manually in IBKR.</b>")

        elif signal == "BUY" and position_status == "long":
            pct = ((price - position_buy_price) / position_buy_price * 100) if position_buy_price else 0
            pct_sign = "+" if pct >= 0 else ""
            broadcast(notify_chats,
                      f"🟢 BUY confirmed — holding position  ·  {ticker}  run {run_n}/{total_runs}\n"
                      f"Current: ${price:.2f}  ·  Bought at: ${position_buy_price:.2f}  ·  {pct_sign}{pct:.1f}%")

        elif signal == "HOLD" and position_status == "long":
            pct = ((price - position_buy_price) / position_buy_price * 100) if position_buy_price else 0
            pct_sign = "+" if pct >= 0 else ""
            broadcast(notify_chats,
                      f"🟡 HOLD — keeping position  ·  {ticker}  run {run_n}/{total_runs}\n"
                      f"Current: ${price:.2f}  ·  Bought at: ${position_buy_price:.2f}  ·  {pct_sign}{pct:.1f}%")

        else:
            broadcast(notify_chats,
                      f"📡 {ticker}  {run_n}/{total_runs}  {signal}  {score}  ${price:.2f}  (waiting for BUY)")

        run_n += 1
        if run_n <= total_runs:
            time.sleep(interval_min * 60)

    if position_status == "long":
        try:
            res = ibkr.sell_position(ticker)
            fill_price = float(res.get("fill_price", 0))
            qty        = float(res.get("quantity", 0))
            pnl        = float(res.get("pnl", 0))
            order_id   = res.get("order_id")
            record_get2_trade(
                session_id, total_runs, "SELL", ticker,
                qty, qty * fill_price, fill_price, order_id, res.get("status"), pnl,
            )
            update_get2_position(session_id, "none", 0, 0)
            pnl_sign = "+" if pnl >= 0 else ""
            broadcast(notify_chats,
                      f"🔴 <b>Session end — auto-liquidated</b>  ·  {ticker}\n"
                      f"Fill: ${fill_price:.2f}  ·  P&amp;L: {pnl_sign}${pnl:.2f}")
        except Exception as e:
            broadcast(notify_chats,
                      f"⚠️ <b>{ticker}</b> end-of-session sell failed: {html.escape(str(e))}\n"
                      f"<b>Close position manually in IBKR.</b>")

    mark_session_complete(session_id)
    _active_sessions.pop(session_id, None)

    trades = get_get2_trades(session_id)
    buys   = [t for t in trades if t["action"] == "BUY"]
    sells  = [t for t in trades if t["action"] == "SELL"]
    net_pnl     = sum(t["pnl"] for t in sells)
    avg_buy     = (sum(t["fill_price"] for t in buys)  / len(buys))  if buys  else 0.0
    avg_sell    = (sum(t["fill_price"] for t in sells) / len(sells)) if sells else 0.0
    pnl_sign    = "+" if net_pnl >= 0 else ""
    broadcast(notify_chats,
              f"✅ <b>{ticker}</b> /get2 session complete ({total_runs} runs)\n"
              f"Trades: {len(buys)} BUY  ·  {len(sells)} SELL\n"
              f"Avg buy: ${avg_buy:.2f}  ·  Avg sell: ${avg_sell:.2f}\n"
              f"Net P&amp;L: {pnl_sign}${net_pnl:.2f}")
    print(f"[Bot] /get2 session {session_id} for {ticker} complete.")


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

    # Build recipient list: requester + main chat (deduplicated, order preserved)
    notify_chats = [chat_id]
    if MAIN_CHAT and MAIN_CHAT != chat_id:
        notify_chats.append(MAIN_CHAT)

    thread = threading.Thread(
        target=_run_analysis,
        args=(chat_id, notify_chats, ticker, agent_name),
        name=f"analysis-{ticker}",
        daemon=True,
    )
    thread.start()


def handle_get(chat_id: str, args: list) -> None:
    """Start a /get monitoring session for a ticker."""
    if not args:
        send(chat_id, "Usage: /get &lt;STOCK&gt; [agent] [runs] [interval] [verbose|quiet]\nExample: /get NVDA claude 100 20")
        return

    ticker       = args[0].upper()
    agent_name   = "claude"
    total_runs   = 1
    interval_min = 20
    quiet        = True

    # Parse remaining args in order: agent, runs, interval, mode.
    # Track how many integer args have been consumed so the first int → total_runs
    # and the second int → interval_min.
    remaining   = args[1:]
    int_count   = 0
    for val in remaining:
        vl = val.lower()
        if vl in VALID_AGENTS:
            agent_name = vl
        elif vl == "verbose":
            quiet = False
        elif vl == "quiet":
            quiet = True
        elif val.isdigit():
            n = int(val)
            if int_count == 0 and 1 <= n <= 500:
                total_runs = n
                int_count += 1
            elif int_count == 1 and 5 <= n <= 240:
                interval_min = n
                int_count += 1

    # Check for existing active session for this ticker
    existing = get_active_session_for_ticker(ticker)
    if existing:
        send(chat_id,
             f"⚠️ <b>{ticker}</b> already has an active session (<code>{existing['session_id']}</code>, "
             f"started {existing['started_at'][:16]} UTC).\nUse /stop {ticker} first.")
        return

    session_id   = create_session(ticker, agent_name, total_runs, interval_min)
    notify_chats = [chat_id]
    if MAIN_CHAT and MAIN_CHAT != chat_id:
        notify_chats.append(MAIN_CHAT)

    mode_str    = "quiet" if quiet else "verbose"
    agent_label = "Claude + Gemini + Mistral" if agent_name == "all" else agent_name.title()
    duration_h  = round(total_runs * interval_min / 60, 1)

    send(chat_id,
         f"🔍 <b>Monitoring started</b>  ·  session: <code>{session_id}</code>\n"
         f"Ticker: <b>{ticker}</b>  ·  Agent: [{agent_label}]\n"
         f"Runs: {total_runs} × {interval_min} min = {duration_h}h  ·  Mode: {mode_str}\n"
         f"<i>Use /stop {ticker} to cancel early.</i>")

    thread = threading.Thread(
        target=_run_get_loop,
        args=(session_id, chat_id, notify_chats, ticker, agent_name, total_runs, interval_min, quiet),
        name=f"get-{ticker}-{session_id}",
        daemon=True,
    )
    _active_sessions[session_id] = thread
    thread.start()


def handle_get2(chat_id: str, args: list) -> None:
    if not IBKR_AVAILABLE:
        send(chat_id, "⚠️ IBKR not available. Run: pip install ib_insync")
        return

    if not args:
        send(chat_id, "Usage: /get2 &lt;STOCK&gt; [agent] &lt;runs&gt; &lt;interval&gt; &lt;budget&gt;\nExample: /get2 NVDA claude 10 20 50")
        return

    ticker       = args[0].upper()
    agent_name   = "claude"
    total_runs   = 1
    interval_min = 20
    budget       = None

    remaining = args[1:]
    int_count = 0
    for val in remaining:
        vl = val.lower()
        if vl in VALID_AGENTS:
            agent_name = vl
        elif val.isdigit():
            n = int(val)
            if int_count == 0 and 1 <= n <= 500:
                total_runs = n
                int_count += 1
            elif int_count == 1 and 5 <= n <= 240:
                interval_min = n
                int_count += 1
            elif int_count == 2 and n > 0:
                budget = float(n)
                int_count += 1

    if budget is None or budget <= 0:
        send(chat_id, "⚠️ Budget is required and must be > 0.\nExample: /get2 NVDA claude 10 20 50")
        return

    existing = get_active_get2_session_for_ticker(ticker)
    if existing:
        send(chat_id,
             f"⚠️ <b>{ticker}</b> already has an active /get2 session (<code>{existing['session_id']}</code>, "
             f"started {existing['started_at'][:16]} UTC).\nUse /stop {ticker} first.")
        return

    session_id = create_session(ticker, agent_name, total_runs, interval_min)
    create_get2_meta(session_id, budget)

    notify_chats = [chat_id]
    if MAIN_CHAT and MAIN_CHAT != chat_id:
        notify_chats.append(MAIN_CHAT)

    agent_label = "Claude + Gemini + Mistral" if agent_name == "all" else agent_name.title()
    duration_h  = round(total_runs * interval_min / 60, 1)

    send(chat_id,
         f"🤖 <b>Automated trading started</b>  ·  session: <code>{session_id}</code>\n"
         f"Ticker: <b>{ticker}</b>  ·  Agent: [{agent_label}]\n"
         f"Runs: {total_runs} × {interval_min} min = {duration_h}h  ·  Budget: ${budget:.2f}\n"
         f"<i>Use /stop {ticker} to cancel early.</i>")

    thread = threading.Thread(
        target=_run_get2_loop,
        args=(session_id, chat_id, notify_chats, ticker, agent_name, total_runs, interval_min, budget),
        name=f"get2-{ticker}-{session_id}",
        daemon=True,
    )
    _active_sessions[session_id] = thread
    thread.start()


def handle_stop(chat_id: str, args: list) -> None:
    """Cancel an active /get session."""
    if not args:
        send(chat_id, "Usage: /stop &lt;STOCK&gt;")
        return
    ticker  = args[0].upper()
    session = get_active_session_for_ticker(ticker)
    if not session:
        send(chat_id, f"No active session for <b>{ticker}</b>.")
        return
    cancel_session(session["session_id"])
    completed = get_run_count(session["session_id"])
    send(chat_id,
         f"🛑 Cancelling <b>{ticker}</b> session <code>{session['session_id']}</code>.\n"
         f"Completed {completed}/{session['total_runs']} runs so far.")


def handle_status(chat_id: str, args: list) -> None:
    """List all currently active /get sessions."""
    sessions = list_active_sessions()
    if not sessions:
        send(chat_id, "No active monitoring sessions.")
        return
    lines = ["<b>Active Sessions:</b>"]
    for s in sessions:
        completed = get_run_count(s["session_id"])
        remaining = s["total_runs"] - completed
        next_min  = s["interval_min"]
        lines.append(
            f"  <b>{s['ticker']}</b> · <code>{s['session_id']}</code> · "
            f"run {completed}/{s['total_runs']} · "
            f"~{remaining * next_min}min left"
        )
    send(chat_id, "\n".join(lines))


def handle_summary(chat_id: str, args: list) -> None:
    """Show a summary of the most recent session for a ticker."""
    if not args:
        send(chat_id, "Usage: /summary &lt;STOCK&gt;")
        return
    ticker = args[0].upper()
    db     = Path(__file__).resolve().parent / "get_state.db"
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM get_sessions WHERE ticker=? ORDER BY started_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row:
        send(chat_id, f"No sessions found for <b>{ticker}</b>.")
        return
    session   = dict(row)
    runs      = get_session_runs(session["session_id"])
    run_dicts = [{"signal": r["signal"], "price": r["price"], "factor_score": r["factor_score"]} for r in runs]
    send(chat_id, format_summary(session, run_dicts))


def handle_portfolio(chat_id: str, args: list) -> None:
    if not IBKR_AVAILABLE or get_ibkr_client is None:
        send(chat_id, "⚠️ IBKR not available. Run: pip install ib_insync")
        return
    ibkr = get_ibkr_client()
    if not ibkr.is_connected():
        send(chat_id, "⚠️ IBKR not connected. Start IB Gateway first.")
        return
    try:
        summary   = ibkr.account_summary()
        positions = ibkr.get_all_positions()
    except Exception as e:
        send(chat_id, f"❌ Failed to fetch portfolio: {html.escape(str(e))}")
        return

    cash         = summary.get("AvailableFunds", summary.get("TotalCashValue", 0))
    net_liq      = summary.get("NetLiquidation", 0)
    buying_power = summary.get("BuyingPower", 0)
    unrealized   = summary.get("UnrealizedPnL", 0)
    unreal_sign  = "+" if unrealized >= 0 else ""

    lines = [
        "<b>📊 IBKR Portfolio</b>",
        f"Cash: ${cash:,.2f}  ·  Net Liq: ${net_liq:,.2f}  ·  Buying Power: ${buying_power:,.2f}",
        f"Unrealized P&amp;L: {unreal_sign}${unrealized:,.2f}",
    ]

    if positions:
        lines.append("")
        lines.append("<b>Positions:</b>")
        for p in positions:
            sym      = html.escape(str(p.get("ticker", "")))
            qty      = p.get("quantity", 0)
            avg_cost = p.get("avg_cost", 0)
            mkt_val  = p.get("market_value", 0)
            cost     = qty * avg_cost
            unreal_p = mkt_val - cost if cost else 0
            sign     = "+" if unreal_p >= 0 else ""
            lines.append(
                f"  <b>{sym}</b>  qty: {qty}  avg: ${avg_cost:.2f}  "
                f"mkt: ${mkt_val:,.2f}  P&amp;L: {sign}${unreal_p:.2f}"
            )
    else:
        lines.append("No open positions.")

    send(chat_id, "\n".join(lines))


def handle_trades(chat_id: str, args: list) -> None:
    if not args:
        send(chat_id, "Usage: /trades &lt;TICKER&gt;")
        return
    ticker = args[0].upper()
    db = Path(__file__).resolve().parent / "get_state.db"
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT s.session_id FROM get_sessions s "
            "INNER JOIN get2_meta m ON s.session_id = m.session_id "
            "WHERE s.ticker=? ORDER BY s.started_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row:
        send(chat_id, f"No /get2 sessions found for <b>{ticker}</b>.")
        return
    session_id = row["session_id"]
    trades = get_get2_trades(session_id)
    if not trades:
        send(chat_id, f"No trades recorded for <b>{ticker}</b> session <code>{session_id}</code>.")
        return
    lines = [f"<b>📋 Trades — {ticker}</b>  session: <code>{session_id}</code>"]
    for t in trades:
        action     = t["action"]
        qty        = t["quantity"]
        fill_price = t["fill_price"]
        pnl        = t["pnl"]
        ts         = t["timestamp"][:16]
        emoji      = "🟢" if action == "BUY" else "🔴"
        pnl_str    = ""
        if action == "SELL":
            sign    = "+" if pnl >= 0 else ""
            pnl_str = f"  P&amp;L: {sign}${pnl:.2f}"
        lines.append(f"  {emoji} {action}  qty: {qty}  fill: ${fill_price:.2f}{pnl_str}  <i>{ts}</i>")
    send(chat_id, "\n".join(lines))


HELP_TEXT = (
    "<b>🤖 Signal Mesh Bot — Commands</b>\n\n"
    "<b>📊 ANALYSIS</b>\n"
    "/ticker &lt;STOCK&gt; [agent]\n"
    "  One-shot analysis.\n"
    "  Agents: claude (default) · gemini · mistral · all\n"
    "  Example: /ticker NVDA all\n\n"
    "/get &lt;STOCK&gt; [agent] [runs] [interval] [mode]\n"
    "  Monitor a stock over time with full reports.\n"
    "  agent:    claude · gemini · mistral · all\n"
    "  runs:     1–500  (default 1)\n"
    "  interval: 5–240 min  (default 20)\n"
    "  mode:     verbose · quiet  (default quiet)\n\n"
    "  Examples:\n"
    "  /get NVDA\n"
    "  /get ASML.AS gemini\n"
    "  /get NVDA claude 100 20\n"
    "  /get NVDA all 50 30 verbose\n\n"
    "/get2 &lt;STOCK&gt; [agent] &lt;runs&gt; &lt;interval&gt; &lt;budget&gt;\n"
    "  Like /get but auto-executes trades via IBKR.\n"
    "  budget: USD amount per trade (e.g. 50 = buy $50 worth)\n"
    "  Buys on first BUY signal, sells on SELL signal.\n"
    "  Auto-liquidates on session end if position is open.\n"
    "  Example: /get2 NVDA claude 10 20 50\n\n"
    "<b>🛑 CONTROL</b>\n"
    "/stop &lt;STOCK&gt;   — cancel active monitoring\n"
    "/status          — list all running sessions\n"
    "/summary &lt;STOCK&gt; — summary of last session\n"
    "/portfolio        — show current IBKR positions + cash balance\n"
    "/trades &lt;TICKER&gt; — show trade history for last /get2 session\n\n"
    "<b>ℹ️ INFO</b>\n"
    "/help — this message\n\n"
    "<b>📌 TICKER FORMAT</b>\n"
    "US:        NVDA · AAPL · MSFT\n"
    "Amsterdam: ASML.AS · HEIA.AS\n"
    "Frankfurt: SAP.DE · BMW.DE\n"
    "Paris:     MC.PA · AIR.PA\n\n"
    "<b>⚙️ NOTES</b>\n"
    "- yfinance data is delayed ~15 min (free tier)\n"
    "- Monitoring pauses when market is closed\n"
    "- Quiet mode: pulse unless signal flips or score moves ≥5\n"
    "- Sessions survive bot restarts (SQLite-backed)\n\n"
    "<i>⚠️ Research tool only. Not financial advice.</i>"
)


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env", file=sys.stderr)
        sys.exit(1)
    if not MAIN_CHAT:
        print("Error: TELEGRAM_CHAT_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    print("[Bot] Signal Mesh Telegram bot started.")
    print(f"[Bot] Main chat  : {MAIN_CHAT}")
    print(f"[Bot] Whitelist  : {', '.join(WHITELIST) if WHITELIST else '(none)'}")
    print("[Bot] Send /ticker <STOCK> [agent] to trigger analysis.")
    print("[Bot] Press Ctrl+C to stop.\n")

    # Resume any sessions that were active when the bot last stopped
    interrupted = list_active_sessions()
    if interrupted:
        print(f"[Bot] Resuming {len(interrupted)} interrupted session(s)...")
        for s in interrupted:
            start_run = get_run_count(s["session_id"]) + 1
            if start_run > s["total_runs"]:
                mark_session_complete(s["session_id"])
                continue
            notify_chats = [MAIN_CHAT] if MAIN_CHAT else []
            t = threading.Thread(
                target=_run_get_loop,
                args=(s["session_id"], MAIN_CHAT, notify_chats,
                      s["ticker"], s["agent"], s["total_runs"],
                      s["interval_min"], True, start_run),
                name=f"get-{s['ticker']}-{s['session_id']}",
                daemon=True,
            )
            _active_sessions[s["session_id"]] = t
            t.start()
            print(f"[Bot]   Resumed {s['ticker']} session {s['session_id']} from run {start_run}")

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

            # Security: only respond to main chat + whitelisted IDs
            if chat_id not in ALLOWED_CHATS:
                print(f"[Bot] Ignored message from unauthorised chat_id={chat_id}")
                continue

            parts   = text.split()
            command = parts[0].lower().split("@")[0]   # strip @botname suffix
            args    = parts[1:]

            print(f"[Bot] Command: {text!r}  from chat_id={chat_id}")

            if command == "/ticker":
                handle_ticker(chat_id, args)
            elif command == "/get":
                handle_get(chat_id, args)
            elif command == "/stop":
                handle_stop(chat_id, args)
            elif command == "/status":
                handle_status(chat_id, args)
            elif command == "/summary":
                handle_summary(chat_id, args)
            elif command == "/get2":
                handle_get2(chat_id, args)
            elif command == "/portfolio":
                handle_portfolio(chat_id, args)
            elif command == "/trades":
                handle_trades(chat_id, args)
            elif command in ("/start", "/help"):
                send(chat_id, HELP_TEXT)
            else:
                send(chat_id, f"Unknown command: {command}\nSend /help to see available commands.")

        if not updates:
            time.sleep(1)


if __name__ == "__main__":
    main()
