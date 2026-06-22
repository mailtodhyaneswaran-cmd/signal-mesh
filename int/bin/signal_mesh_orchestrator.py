"""
signal_mesh_orchestrator.py
─────────────────────────────────────────────────────────────────────────────
Signal Mesh — Multi-Agent CLI Orchestrator

LLM calls are routed through pluggable agent backends (lib_agents_*.py).
Step 1 (trending-stock discovery) always uses Claude.
Steps 2-3 (per-stock analysis) use whichever agent(s) --agent selects.

Usage:
  python signal_mesh_orchestrator.py fetch_data
  python signal_mesh_orchestrator.py fetch_data --agent gemini
  python signal_mesh_orchestrator.py fetch_data --agent all
  python signal_mesh_orchestrator.py fetch_data --euro --agent all --verbose
  python signal_mesh_orchestrator.py fetch_data --bulk_prompt --agent gemini

Actions:
  fetch_data  — Discover 5 trending stocks (STEP1_PROMPT via Claude),
                fetch yfinance data, run all 25 prompts, print results.

Agent options:
  claude  — Claude Code CLI (default)
  gemini  — Google Gemini API  (set key in lib_agents_gemini.py first)
  all     — both agents, prompts split round-robin across them

Bulk mode (--bulk_prompt):
  Combines all 5 prompts within each category into one single LLM call,
  producing one JSON output per category. Total: 5 calls per stock instead
  of 25. One agent per category, round-robin across agents list.

Cross-pollination (automatic when --agent all):
  After the 25 factor prompts, each agent receives the other's composite
  thesis (signal, score, category breakdown) and gets one revision round.
  Revised signals are added to the vote pool; confidence_delta adjusts
  the weighted score. Flip cases are highlighted in the results table.
"""

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class _Tee:
    """Write to stdout and a file simultaneously."""
    def __init__(self, file_path: str):
        self._file = open(file_path, "w", encoding="utf-8")
        self._stdout = sys.stdout
        sys.stdout = self

    def write(self, data: str):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        sys.stdout = self._stdout
        self._file.close()

import yfinance as yf

from analysis_prompts import (
    ALL_PROMPTS, CATEGORY_WEIGHTS, STEP1_PROMPT, STEP2_CROSS_POLLINATION_PROMPT,
    TRADE_REPUBLIC_PROMPTS,
)
from lib_agents import BaseAgent
from lib_agents_claude import ClaudeAgent
from lib_agents_gemini import GeminiAgent
from lib_agents_mistral import MistralAgent
from lib_env import load_dotenv

VERBOSE = False

# ── Configurable run parameters ───────────────────────────────────────────────
NUM_STOCKS = 3   # number of trending stocks to analyse per run (Step 1 discovers this many)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — STEP 1: DISCOVER TRENDING STOCKS (always via ClaudeAgent)
# Uses STEP1_PROMPT["STEP1_market_buzz"] to ask Claude which 5 stocks
# are most talked about right now, then returns their tickers.
# ══════════════════════════════════════════════════════════════════════════════
def discover_trending_stocks(agent: BaseAgent) -> list[str]:
    print("  Running STEP1_PROMPT via Claude to discover trending stocks...")
    prompt = STEP1_PROMPT["STEP1_market_buzz"]
    result = agent.fetch_data(prompt, timeout=250)

    if "error" in result and "trending_stocks" not in result:
        print(f"[ERROR] STEP1 failed: {result.get('error')}. Cannot continue.")
        sys.exit(1)

    stocks = result.get("trending_stocks", [])
    if not stocks:
        print("[ERROR] STEP1 returned no stocks. Cannot continue without a watchlist.")
        sys.exit(1)

    tickers = [s["ticker"] for s in stocks if "ticker" in s]
    print(f"  Discovered: {' · '.join(tickers)}")
    for s in stocks:
        print(f"    [{s.get('rank','?')}] {s.get('ticker','?'):6s}  buzz={s.get('buzz_score','?'):>3}  "
              f"sentiment={s.get('sentiment','?'):8s}  {s.get('reason','')[:60]}")
    return tickers


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — MARKET DATA FETCHER (yfinance)
# Pulls everything needed for the 25 prompts. Same logic as orchestrator_v2.
# ══════════════════════════════════════════════════════════════════════════════
def fetch_stock_data(ticker: str) -> dict:
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        hist  = stock.history(period="1y")
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

    closes  = [float(c) for c in hist["Close"].tolist()]
    volumes = [int(v)   for v in hist["Volume"].tolist()]

    if not closes:
        return {"ticker": ticker, "error": "no price data"}

    price    = closes[-1]
    w52_high = info.get("fiftyTwoWeekHigh", price)
    w52_low  = info.get("fiftyTwoWeekLow",  price)

    ma10  = sum(closes[-10:])  / 10  if len(closes) >= 10  else price
    ma50  = sum(closes[-50:])  / 50  if len(closes) >= 50  else price
    ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else price

    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g  = sum(gains[-14:])  / 14 if len(gains)  >= 14 else 0
    avg_l  = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0.001
    rsi    = round(100 - (100 / (1 + avg_g / avg_l)), 1)

    win20   = closes[-20:] if len(closes) >= 20 else closes
    bb_mean = sum(win20) / len(win20)
    bb_std  = math.sqrt(sum((x - bb_mean)**2 for x in win20) / len(win20))
    bb_width = round((4 * bb_std / bb_mean) * 100, 2) if bb_mean else 0

    def mom(n):
        return round(((closes[-1] - closes[-n]) / closes[-n]) * 100, 2) if len(closes) >= n else 0

    vol_recent = sum(volumes[-5:])  / 5  if len(volumes) >= 5  else 0
    vol_avg    = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1
    vol_trend  = "up" if vol_recent > vol_avg * 1.1 else "down" if vol_recent < vol_avg * 0.9 else "flat"

    pe            = round(info.get("trailingPE",       0) or 0, 1)
    pb            = round(info.get("priceToBook",      0) or 0, 2)
    peg           = round(info.get("pegRatio",         0) or 0, 2)
    roe           = round((info.get("returnOnEquity",  0) or 0) * 100, 1)
    roa           = round((info.get("returnOnAssets",  0) or 0) * 100, 1)
    profit_margin = round((info.get("profitMargins",   0) or 0) * 100, 1)
    rev_growth    = round((info.get("revenueGrowth",   0) or 0) * 100, 1)
    earn_growth   = round((info.get("earningsGrowth",  0) or 0) * 100, 1)
    debt_equity   = round(info.get("debtToEquity",     0) or 0, 2)
    current_ratio = round(info.get("currentRatio",     0) or 0, 2)
    beta          = round(info.get("beta",              1) or 1, 2)
    sector        = info.get("sector", "Technology")
    short_pct     = round((info.get("shortPercentOfFloat", 0) or 0) * 100, 1)
    analyst_count = info.get("numberOfAnalystOpinions", 0) or 0
    target_price  = round(info.get("targetMeanPrice", price) or price, 2)
    upside_pct    = round(((target_price - price) / price) * 100, 1) if price else 0
    recommendation = info.get("recommendationKey", "hold")

    return {
        "ticker":             ticker,
        "price":              round(price, 2),
        "week52_high":        w52_high,
        "week52_low":         w52_low,
        "ma10":               round(ma10, 2),
        "ma50":               round(ma50, 2),
        "ma200":              round(ma200, 2),
        "vs_ma10":            round(((price - ma10)  / ma10)  * 100, 2),
        "vs_ma50":            round(((price - ma50)  / ma50)  * 100, 2),
        "vs_ma200":           round(((price - ma200) / ma200) * 100, 2),
        "ma_signal":          "BUY" if ma10 > ma50 else "SELL",
        "rsi":                rsi,
        "rsi_signal":         "BUY" if rsi < 30 else "SELL" if rsi > 70 else "HOLD",
        "bb_width":           bb_width,
        "vol_trend":          vol_trend,
        "return_1m":          mom(22),
        "return_3m":          mom(66),
        "return_6m":          mom(126),
        "return_12m":         mom(252),
        "pe_ratio":           pe,
        "pb_ratio":           pb,
        "peg_ratio":          peg,
        "roe":                roe,
        "roa":                roa,
        "profit_margin":      profit_margin,
        "revenue_growth":     rev_growth,
        "earnings_growth":    earn_growth,
        "debt_equity":        debt_equity,
        "current_ratio":      current_ratio,
        "beta":               beta,
        "sector":             sector,
        "short_pct":          short_pct,
        "analyst_count":      analyst_count,
        "target_price":       target_price,
        "upside_pct":         upside_pct,
        "recommendation":     recommendation,
        "closing_prices_30d": [round(c, 2) for c in closes[-30:]],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3b — SINGLE-TICKER RICH DATA FETCH  (/get command)
# Returns all fields required by SINGLE_TICKER_BASELINE_PROMPT and
# SINGLE_TICKER_DELTA_PROMPT placeholders.
# ══════════════════════════════════════════════════════════════════════════════

def _ema(values: list, period: int) -> list:
    """Compute EMA of a list of floats using a local helper.

    Initialises from the SMA of the first `period` values, then applies
    the standard EMA formula.  Pads the front with the initial EMA value
    so the output has the same length as the input.
    """
    if len(values) < period:
        return values[:]
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema = [seed] * period
    for v in values[period:]:
        ema.append(ema[-1] + k * (v - ema[-1]))
    # Pad front to match input length
    pad_len = len(values) - len(ema)
    return [ema[0]] * pad_len + ema


def fetch_single_ticker_data(ticker: str) -> dict:
    """Rich yfinance data fetch for the /get monitoring loop.

    Computes: day_change_pct, SMA20, MACD(12,26,9), Bollinger Bands(20,2),
    ATR(14), volume metrics, plus all fundamental fields needed by the
    single-ticker prompts.  Returns a flat dict with keys matching the
    prompt placeholders exactly.
    """
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        hist  = stock.history(period="1y")
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

    if hist.empty:
        return {"ticker": ticker, "error": "no price data returned"}

    closes  = [float(c) for c in hist["Close"].tolist()]
    highs   = [float(h) for h in hist["High"].tolist()]
    lows    = [float(l) for l in hist["Low"].tolist()]
    volumes = [int(v)   for v in hist["Volume"].tolist()]

    if len(closes) < 2:
        return {"ticker": ticker, "error": "insufficient price history"}

    price = closes[-1]

    # ── Day change % ──────────────────────────────────────────────────────
    day_change_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if closes[-2] != 0 else 0

    # ── 52-week range ─────────────────────────────────────────────────────
    low_52w  = info.get("fiftyTwoWeekLow",  min(lows))
    high_52w = info.get("fiftyTwoWeekHigh", max(highs))

    # ── RSI(14) ───────────────────────────────────────────────────────────
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g  = sum(gains[-14:])  / 14 if len(gains)  >= 14 else 0
    avg_l  = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0.001
    rsi    = round(100 - (100 / (1 + avg_g / avg_l)), 1)

    # ── SMA20 ─────────────────────────────────────────────────────────────
    sma20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)

    # ── SMA50 ─────────────────────────────────────────────────────────────
    sma50 = round(sum(closes[-50:]) / min(len(closes), 50), 2) if len(closes) >= 10 else round(price, 2)

    # ── SMA200 ────────────────────────────────────────────────────────────
    sma200 = round(sum(closes[-200:]) / min(len(closes), 200), 2) if len(closes) >= 20 else round(price, 2)

    # ── MACD(12, 26, 9) ──────────────────────────────────────────────────
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line_series  = [round(e12 - e26, 4) for e12, e26 in zip(ema12, ema26)]
    macd_signal_series = _ema(macd_line_series, 9)
    macd_line_val   = round(macd_line_series[-1],   4)
    macd_signal_val = round(macd_signal_series[-1], 4)
    macd_hist_val   = round(macd_line_val - macd_signal_val, 4)

    # ── Bollinger Bands(20, 2) ────────────────────────────────────────────
    win20    = closes[-20:] if len(closes) >= 20 else closes
    bb_mid   = sum(win20) / len(win20)
    bb_std   = math.sqrt(sum((x - bb_mid) ** 2 for x in win20) / len(win20))
    bb_upper = round(bb_mid + 2 * bb_std, 2)
    bb_lower = round(bb_mid - 2 * bb_std, 2)
    bb_mid   = round(bb_mid, 2)

    # ── ATR(14) using true ranges ─────────────────────────────────────────
    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        true_ranges.append(tr)
    atr = round(sum(true_ranges[-14:]) / min(len(true_ranges), 14), 4) if true_ranges else round(price * 0.02, 4)

    # ── Volume ────────────────────────────────────────────────────────────
    today_vol = volumes[-1] if volumes else 0
    avg_vol   = round(sum(volumes[-30:]) / min(len(volumes), 30)) if volumes else 0

    # ── Fundamentals from yfinance info ───────────────────────────────────
    pe_ttm  = info.get("trailingPE")
    pe_fwd  = info.get("forwardPE")
    peg     = info.get("pegRatio")
    eps_growth  = info.get("earningsGrowth")
    rev_growth  = info.get("revenueGrowth")
    op_margin   = info.get("operatingMargins")
    de_ratio    = info.get("debtToEquity")
    sector      = info.get("sector", "N/A")

    # Format percentages (yfinance returns decimals for growth/margins)
    def _pct(v):
        if v is None:
            return "N/A"
        return round(float(v) * 100, 1)

    def _round2(v):
        if v is None:
            return "N/A"
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return "N/A"

    # ── Next earnings date ────────────────────────────────────────────────
    next_earnings_date = "N/A"
    try:
        cal = stock.calendar
        if cal is not None:
            if hasattr(cal, "get"):
                # dict-style
                dates = cal.get("Earnings Date")
                if dates:
                    d = dates[0] if isinstance(dates, (list, tuple)) else dates
                    next_earnings_date = str(d)[:10]
            elif hasattr(cal, "loc"):
                # DataFrame-style (older yfinance versions)
                if "Earnings Date" in cal.index:
                    d = cal.loc["Earnings Date"].iloc[0] if hasattr(cal.loc["Earnings Date"], "iloc") else cal.loc["Earnings Date"]
                    next_earnings_date = str(d)[:10]
    except Exception:
        next_earnings_date = "N/A"

    return {
        "ticker":            ticker,
        "price":             round(price, 2),
        "day_change_pct":    day_change_pct,
        "low_52w":           round(float(low_52w),  2),
        "high_52w":          round(float(high_52w), 2),
        "rsi":               rsi,
        "sma20":             sma20,
        "sma50":             sma50,
        "sma200":            sma200,
        "macd_line":         macd_line_val,
        "macd_signal":       macd_signal_val,
        "macd_hist":         macd_hist_val,
        "bb_upper":          bb_upper,
        "bb_mid":            bb_mid,
        "bb_lower":          bb_lower,
        "atr":               atr,
        "today_vol":         today_vol,
        "avg_vol":           avg_vol,
        "pe_ttm":            _round2(pe_ttm),
        "pe_fwd":            _round2(pe_fwd),
        "peg":               _round2(peg),
        "eps_growth":        _pct(eps_growth),
        "rev_growth":        _pct(rev_growth),
        "op_margin":         _pct(op_margin),
        "de_ratio":          _round2(de_ratio),
        "sector":            sector,
        "next_earnings_date": next_earnings_date,
        # Stubs
        "vix":               18,
        "rate_trend":        "hold",
        "sector_perf":       0,
    }


def analyze_single_ticker(
    ticker: str,
    stock_data: dict,
    agent_name: str,
    run_n: int,
    session_id: str,
    interval_min: int,
    total_runs: int,
) -> dict:
    """Run a single-ticker analysis for one /get run.

    Builds baseline or delta prompt depending on run_n, sends it to the
    selected agent(s), parses the JSON response, and returns the result dict.

    For agent_name='all': runs all 3 agents, takes majority vote on signal,
    averages factor_score and confidence, and merges catalysts/risks.

    Returns a dict with at least: signal, factor_score, confidence, timestamp, price.
    On hard failure returns: {"error": "...", "signal": "HOLD", "factor_score": 50, "confidence": 0}.
    """
    from lib_agents_claude   import ClaudeAgent
    from lib_agents_gemini   import GeminiAgent
    from lib_agents_mistral  import MistralAgent
    from analysis_prompts    import build_baseline_prompt, build_delta_prompt
    from lib_get_state       import get_baseline, get_previous_run

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Build prompt ───────────────────────────────────────────────────────
    if run_n == 1:
        prompt = build_baseline_prompt(ticker, stock_data, total_runs, interval_min)
    else:
        baseline = get_baseline(session_id) or {}
        previous = get_previous_run(session_id, run_n) or baseline
        prompt   = build_delta_prompt(
            ticker, stock_data, run_n, baseline, previous, total_runs, interval_min
        )

    # ── Build agent list ───────────────────────────────────────────────────
    if agent_name == "all":
        agents = [ClaudeAgent(verbose=VERBOSE), GeminiAgent(verbose=VERBOSE), MistralAgent(verbose=VERBOSE)]
    elif agent_name == "gemini":
        agents = [GeminiAgent(verbose=VERBOSE)]
    elif agent_name == "mistral":
        agents = [MistralAgent(verbose=VERBOSE)]
    else:
        agents = [ClaudeAgent(verbose=VERBOSE)]

    # ── Run agent(s) ───────────────────────────────────────────────────────
    if len(agents) == 1:
        result = agents[0].fetch_data(prompt)
        if "error" in result and "signal" not in result:
            return {"error": result.get("error", "agent error"), "signal": "HOLD", "factor_score": 50, "confidence": 0}
        result["timestamp"]     = now_iso
        result["price"]         = stock_data.get("price", 0)
        result["has_stub_data"] = True
        return result

    # ── Multi-agent: majority vote ─────────────────────────────────────────
    responses = []
    for agent in agents:
        try:
            r = agent.fetch_data(prompt)
            if "signal" in r:
                r["_agent"] = agent.name
                responses.append(r)
        except Exception as e:
            print(f"[analyze_single_ticker] {agent.name} failed: {e}")

    if not responses:
        return {"error": "all agents failed", "signal": "HOLD", "factor_score": 50, "confidence": 0}

    # Majority vote on signal
    signals = [r.get("signal", "HOLD") for r in responses]
    buy_c  = signals.count("BUY")
    sell_c = signals.count("SELL")
    hold_c = signals.count("HOLD")
    total  = len(signals)
    if   buy_c  / total >= 0.5:  majority_signal = "BUY"
    elif sell_c / total >= 0.4:  majority_signal = "SELL"
    else:                         majority_signal = "HOLD"

    # Average numeric fields
    avg_score = round(sum(r.get("factor_score", 50) or 50 for r in responses) / len(responses))
    avg_conf  = round(sum(r.get("confidence",   50) or 50 for r in responses) / len(responses))

    # Use first successful result as structural template
    base = responses[0].copy()
    base["signal"]       = majority_signal
    base["factor_score"] = avg_score
    base["confidence"]   = avg_conf

    # ── Aggregate trade levels across all agents ───────────────────────────
    def _avg_numeric(key: str):
        vals = [r.get(key) for r in responses if r.get(key) is not None]
        if not vals:
            return None
        try:
            return round(sum(float(v) for v in vals) / len(vals), 2)
        except (TypeError, ValueError):
            return vals[0]

    agg_entry  = _avg_numeric("entry")
    agg_target = _avg_numeric("target")

    # Most conservative stop: max stop price (tightest risk control for longs)
    stop_vals = [r.get("stop_loss") for r in responses if r.get("stop_loss") is not None]
    if stop_vals:
        try:
            agg_stop = round(max(float(v) for v in stop_vals), 2)
        except (TypeError, ValueError):
            agg_stop = stop_vals[0]
    else:
        agg_stop = None

    base["entry"]     = agg_entry
    base["stop_loss"] = agg_stop
    base["target"]    = agg_target

    # Recompute R:R from aggregated levels (don't average ratios)
    if agg_entry and agg_stop and agg_target and agg_entry != agg_stop:
        try:
            base["risk_reward"] = round((agg_target - agg_entry) / (agg_entry - agg_stop), 2)
        except ZeroDivisionError:
            pass

    agg_horizon = _avg_numeric("horizon_days")
    if agg_horizon is not None:
        base["horizon_days"] = int(round(agg_horizon))

    # ── Aggregate per-category scores ─────────────────────────────────────
    def _modal_verdict(verdicts: list) -> str:
        if not verdicts:
            return ""
        counts: dict = {}
        for v in verdicts:
            counts[v] = counts.get(v, 0) + 1
        return max(counts, key=counts.__getitem__)

    merged_cats: dict = {}
    for r in responses:
        for cat, cat_data in (r.get("scores") or {}).items():
            if cat not in merged_cats:
                merged_cats[cat] = {"scores": [], "deltas": [], "verdicts": []}
            if cat_data.get("score") is not None:
                try:
                    merged_cats[cat]["scores"].append(float(cat_data["score"]))
                except (TypeError, ValueError):
                    pass
            if cat_data.get("delta") is not None:
                try:
                    merged_cats[cat]["deltas"].append(float(cat_data["delta"]))
                except (TypeError, ValueError):
                    pass
            if cat_data.get("verdict"):
                merged_cats[cat]["verdicts"].append(str(cat_data["verdict"]))

    if merged_cats:
        base["scores"] = {
            cat: {
                "score":   round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0,
                "delta":   round(sum(d["deltas"]) / len(d["deltas"]), 1) if d["deltas"] else None,
                "verdict": _modal_verdict(d["verdicts"]),
            }
            for cat, d in merged_cats.items()
        }

    # ── Aggregate baseline delta fields ───────────────────────────────────
    for delta_key in ("score_delta_vs_baseline", "price_delta_vs_baseline_pct"):
        vals = [r.get(delta_key) for r in responses if r.get(delta_key) is not None]
        if vals:
            try:
                base[delta_key] = round(sum(float(v) for v in vals) / len(vals), 2)
            except (TypeError, ValueError):
                base[delta_key] = vals[0]

    # Deduplicate and merge catalysts / risks (up to 5 each)
    def _merge_list(key: str) -> list:
        seen: set = set()
        merged: list = []
        for r in responses:
            for item in (r.get(key) or []):
                if item and item not in seen:
                    seen.add(item)
                    merged.append(item)
                    if len(merged) >= 5:
                        return merged
        return merged

    if run_n == 1:
        base["catalysts"] = _merge_list("catalysts")
        base["risks"]     = _merge_list("risks")
    else:
        base["new_catalysts"] = _merge_list("new_catalysts")
        base["new_risks"]     = _merge_list("new_risks")

    base["timestamp"]     = now_iso
    base["price"]         = stock_data.get("price", 0)
    base["has_stub_data"] = True
    return base


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — PROMPT FILLER
# Substitutes all {variable} placeholders in a prompt template with real data.
# ══════════════════════════════════════════════════════════════════════════════
TR_CATEGORY_WEIGHTS = {
    "tr_technical":   0.20,
    "tr_fundamental": 0.25,
    "tr_sentiment":   0.20,
    "tr_macro":       0.20,
    "tr_quant":       0.15,
}

MACRO_STUBS = {
    "fed_rate":      5.25,
    "treasury_10y":  4.3,
    "inflation":     3.2,
    "unemployment":  3.9,
    "vix":           18,
    "dxy":           104,
    "eurusd":        1.08,
    "risk_appetite": "neutral",
    "cycle_phase":   "late expansion",
    "gdp_trend":     "slowing",
    "rate_direction": "hold",
}

def fill_prompt(template: str, data: dict) -> str:
    fill = {
        "ticker":                   data["ticker"],
        "current_price":            data["price"],
        "ohlcv_data":               json.dumps({"last_30_closes": data["closing_prices_30d"]}),
        "closing_prices":           str(data["closing_prices_30d"]),
        "strategy_signals":         json.dumps({
            "MA_signal":   data["ma_signal"],
            "RSI":         data["rsi"],
            "RSI_signal":  data["rsi_signal"],
            "BB_width":    data["bb_width"],
            "momentum_1m": data["return_1m"],
        }),
        # technical
        "momentum_10d":             data["return_1m"],
        "momentum_30d":             data["return_3m"],
        "volume_trend":             data["vol_trend"],
        "rsi":                      data["rsi"],
        "price_vs_ma50":            data["vs_ma50"],
        "bb_width":                 data["bb_width"],
        "atr":                      round(data["price"] * 0.02, 2),
        "hist_volatility":          round(abs(data["return_3m"]), 1),
        "vs_ma10":                  data["vs_ma10"],
        "vs_ma50":                  data["vs_ma50"],
        "vs_ma200":                 data["vs_ma200"],
        "week52_high":              data["week52_high"],
        "week52_low":               data["week52_low"],
        # fundamental
        "pe_ratio":                 data["pe_ratio"],
        "sector_pe":                25,
        "peg_ratio":                data["peg_ratio"],
        "pb_ratio":                 data["pb_ratio"],
        "p_fcf":                    round(data["pe_ratio"] * 0.85, 1) if data["pe_ratio"] else 0,
        "ev_ebitda":                round(data["pe_ratio"] * 0.75, 1) if data["pe_ratio"] else 0,
        "revenue_growth":           data["revenue_growth"],
        "eps_growth":               data["earnings_growth"],
        "profit_margin":            data["profit_margin"],
        "fcf_margin":               round(data["profit_margin"] * 0.85, 1),
        "rev_eps_gap":              round(data["earnings_growth"] - data["revenue_growth"], 1),
        "debt_to_equity":           data["debt_equity"],
        "current_ratio":            data["current_ratio"],
        "interest_coverage":        round(10 / max(data["debt_equity"], 0.1), 1),
        "roe":                      data["roe"],
        "roa":                      data["roa"],
        "quarterly_revenue_growth": json.dumps([data["revenue_growth"]] * 4),
        "quarterly_eps_growth":     json.dumps([data["earnings_growth"]] * 4),
        "forward_revenue_growth":   data["revenue_growth"],
        "forward_eps_growth":       data["earnings_growth"],
        "earnings_surprise":        5.0,
        "sector":                   data["sector"],
        "margin_vs_sector":         round(data["profit_margin"] - 15, 1),
        "roe_vs_sector":            round(data["roe"] - 15, 1),
        "market_share_trend":       "stable",
        "competitive_news":         "No recent news",
        # sentiment
        "news_headlines":           json.dumps([]),
        "consensus_rating":         data["recommendation"].title(),
        "analyst_count":            data["analyst_count"],
        "recent_upgrades":          1,
        "recent_downgrades":        0,
        "avg_price_target":         data["target_price"],
        "upside_pct":               data["upside_pct"],
        "wsb_trend":                "stable",
        "twitter_sentiment":        15,
        "stocktwits_bullish":       55,
        "trending_topic":           f"{data['ticker']} swing trade",
        "abnormal_volume":          data["vol_trend"] == "up",
        "ceo_buys":                 0,
        "ceo_sells":                0,
        "exec_buys":                0,
        "exec_sells":               0,
        "net_insider_direction":    "neutral",
        "short_interest_pct":       data["short_pct"],
        "days_to_cover":            round(data["short_pct"] / 5, 1),
        "short_change":             0,
        "borrow_rate":              round(data["short_pct"] * 0.3, 1),
        # macro (stubs)
        "fed_rate":                 MACRO_STUBS["fed_rate"],
        "treasury_10y":             MACRO_STUBS["treasury_10y"],
        "rate_direction":           MACRO_STUBS["rate_direction"],
        "intl_revenue_pct":         40,
        "gdp_trend":                MACRO_STUBS["gdp_trend"],
        "inflation_rate":           MACRO_STUBS["inflation"],
        "unemployment":             MACRO_STUBS["unemployment"],
        "cycle_phase":              MACRO_STUBS["cycle_phase"],
        "days_to_earnings":         45,
        "expected_eps":             round(data["pe_ratio"] * 0.04, 2) if data["pe_ratio"] else 0,
        "last_surprise":            5.0,
        "options_implied_move":     round(abs(data["return_1m"]) * 1.5, 1),
        "dxy":                      MACRO_STUBS["dxy"],
        "eurusd":                   MACRO_STUBS["eurusd"],
        "risk_appetite":            MACRO_STUBS["risk_appetite"],
        "vix":                      MACRO_STUBS["vix"],
        "macro_news_headlines":     json.dumps([]),
        "supply_chain":             "Asia, US",
        "regulatory_risk":          "medium",
        # quant
        "pe_percentile":            min(100, int(data["pe_ratio"] / 0.5)) if data["pe_ratio"] else 50,
        "pb_percentile":            min(100, int(data["pb_ratio"] * 10))  if data["pb_ratio"] else 50,
        "pfcf_percentile":          50,
        "evebitda_percentile":      50,
        "value_composite":          50,
        "margin_stability":         round(abs(data["profit_margin"]) * 0.1, 2),
        "beat_ratio":               75,
        "fcf_yield":                round(100 / data["pe_ratio"], 1) if data["pe_ratio"] > 0 else 0,
        "return_12m_ex1m":          round(data["return_12m"] - data["return_1m"], 1),
        "return_6m":                data["return_6m"],
        "return_3m":                data["return_3m"],
        "return_1m":                data["return_1m"],
        "momentum_percentile":      50,
        "vol_30d":                  round(abs(data["return_1m"]) * 2, 1),
        "vol_90d":                  round(abs(data["return_3m"]) * 1.5, 1),
        "vol_percentile":           50,
        "max_drawdown":             round(abs(min(data["return_3m"], data["return_6m"])), 1),
        "eps_3m_ago":               round(data["pe_ratio"] * 0.038, 2) if data["pe_ratio"] else 0,
        "eps_today":                round(data["pe_ratio"] * 0.040, 2) if data["pe_ratio"] else 0,
        "revision_direction":       "up" if data["earnings_growth"] > 0 else "down",
        "pct_raising":              65 if data["earnings_growth"] > 0 else 35,
        "pct_cutting":              35 if data["earnings_growth"] > 0 else 65,
        "debt_equity":              data["debt_equity"],
    }
    try:
        return template.format(**fill)
    except KeyError:
        return template


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — RUN ALL 25 PROMPTS FOR ONE TICKER
# Loops through prompts, distributes them round-robin across the agents list.
# When multiple agents are used, fires a cross-pollination round afterwards.
# ══════════════════════════════════════════════════════════════════════════════

def _agent_signal(log: dict) -> str:
    t = len(log["signals"])
    if not t:
        return "HOLD"
    b = log["signals"].count("BUY")
    s = log["signals"].count("SELL")
    return "BUY" if b / t >= 0.5 else "SELL" if s / t >= 0.4 else "HOLD"

def _avg_score(log: dict) -> float:
    return round(sum(log["scores"]) / len(log["scores"]), 1) if log["scores"] else 50.0

def _cat_str(log: dict) -> str:
    return "  ".join(
        f"{c.split('_')[-1][:4].upper()}={v}"
        for c, v in log.get("category_scores", {}).items()
    ) or "N/A"


def run_cross_pollination_for_ticker(
    ticker: str, agents: list[BaseAgent], agent_log: dict
) -> list[dict]:
    results = []
    n = len(agents)
    for i, agent in enumerate(agents):
        my        = agent_log[agent.name]
        peer_name = agents[(i + 1) % n].name
        peer      = agent_log[peer_name]

        if not my["signals"] or not peer["signals"]:
            continue

        my_sig   = _agent_signal(my)
        peer_sig = _agent_signal(peer)
        my_buy   = my["signals"].count("BUY")
        my_sell  = my["signals"].count("SELL")
        my_hold  = len(my["signals"]) - my_buy - my_sell
        pb       = peer["signals"].count("BUY")
        ps       = peer["signals"].count("SELL")
        ph       = len(peer["signals"]) - pb - ps

        prompt = STEP2_CROSS_POLLINATION_PROMPT.format(
            ticker                  = ticker,
            n_prompts               = len(my["signals"]),
            my_signal               = my_sig,
            my_score                = _avg_score(my),
            my_category_breakdown   = _cat_str(my),
            my_buy                  = my_buy,
            my_sell                 = my_sell,
            my_hold                 = my_hold,
            peer_signal             = peer_sig,
            peer_score              = _avg_score(peer),
            peer_category_breakdown = _cat_str(peer),
            peer_buy                = pb,
            peer_sell               = ps,
            peer_hold               = ph,
        )

        result = agent.fetch_data(prompt)
        if "revised_signal" not in result:
            result = {
                "revised_signal": my_sig, "signal_changed": False,
                "confidence_delta": 0, "original_signal": my_sig,
                "revision_reason": "error — keeping original signal",
                "peer_argument_strength": "unknown",
            }
        result["_agent"] = agent.name
        result["_peer"]  = peer_name
        results.append(result)

        orig    = result.get("original_signal", my_sig)
        revised = result.get("revised_signal", orig)
        changed = result.get("signal_changed", False)
        delta   = int(result.get("confidence_delta", 0))
        reason  = result.get("revision_reason", "")[:80]
        print(f"    {ticker}  [{agent.name:6s}]  cross_pollination"
              f"  {orig:4s} → {revised:4s}  "
              f"{'CHANGED' if changed else 'held   '}  delta={delta:+d}  {reason}")
    return results


def run_all_prompts_for_ticker(
    ticker: str, stock_data: dict, agents: list[BaseAgent], euro: bool = False, threaded: bool = False
) -> dict:
    prompts_to_use = TRADE_REPUBLIC_PROMPTS if euro else ALL_PROMPTS
    weights_to_use = TR_CATEGORY_WEIGHTS    if euro else CATEGORY_WEIGHTS
    agent_log      = {a.name: {"signals": [], "scores": [], "category_raw": {}, "proper_replies": 0, "failed_replies": 0} for a in agents}

    if threaded and len(agents) > 1:
        # ── THREADED: each agent runs ALL prompts independently in parallel ──
        _lock = threading.Lock()

        def _run_agent(agent):
            for category, prompts in prompts_to_use.items():
                for prompt_key, template in prompts.items():
                    filled    = fill_prompt(template, stock_data)
                    result    = agent.fetch_data(filled)
                    is_failed = "error" in result and "signal" not in result
                    if is_failed:
                        agent_log[agent.name]["failed_replies"] += 1
                        sig, score = "SKIP", "—"
                    else:
                        agent_log[agent.name]["proper_replies"] += 1
                        sig   = result.get("signal", "HOLD")
                        score = next(
                            (v for k, v in result.items() if k.endswith("_score") and isinstance(v, (int, float))),
                            50,
                        )
                        agent_log[agent.name]["signals"].append(sig)
                        agent_log[agent.name]["scores"].append(score)
                        agent_log[agent.name]["category_raw"].setdefault(category, []).append(result)
                    with _lock:
                        print(f"    {ticker}  [{agent.name:6s}]  {category:16s}  {prompt_key:35s}  signal={sig:4s}  score={score}  [thread]")

        threads = [threading.Thread(target=_run_agent, args=(a,), name=a.name) for a in agents]
        for t in threads: t.start()
        for t in threads: t.join()

        all_signals  = [s for log in agent_log.values() for s in log["signals"]]
        category_raw = {
            cat: [r for a in agents for r in agent_log[a.name]["category_raw"].get(cat, [])]
            for cat in prompts_to_use
        }

    else:
        # ── ROUND-ROBIN: prompts distributed across agents sequentially ──────
        all_signals  = []
        category_raw = {}
        prompt_index = 0

        for category, prompts in prompts_to_use.items():
            category_results = []
            for prompt_key, template in prompts.items():
                agent     = agents[prompt_index % len(agents)]
                filled    = fill_prompt(template, stock_data)
                result    = agent.fetch_data(filled)
                is_failed = "error" in result and "signal" not in result
                if is_failed:
                    agent_log[agent.name]["failed_replies"] += 1
                    sig, score = "SKIP", "—"
                else:
                    agent_log[agent.name]["proper_replies"] += 1
                    category_results.append(result)
                    all_signals.append(result.get("signal", "HOLD"))
                    sig   = result.get("signal", "HOLD")
                    score = next(
                        (v for k, v in result.items() if k.endswith("_score") and isinstance(v, (int, float))),
                        50,
                    )
                    agent_log[agent.name]["signals"].append(sig)
                    agent_log[agent.name]["scores"].append(score)
                    agent_log[agent.name]["category_raw"].setdefault(category, []).append(result)
                print(f"    {ticker}  [{agent.name:6s}]  {category:16s}  {prompt_key:35s}  signal={sig:4s}  score={score}")
                prompt_index += 1
            category_raw[category] = category_results

    # ── SHARED: category scores, weighted score, cross-pollination ────────────
    for log in agent_log.values():
        cat_scores = {}
        for cat, results in log["category_raw"].items():
            scores = [
                next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
                for r in results
            ]
            cat_scores[cat] = round(sum(scores) / len(scores), 1) if scores else 50
        log["category_scores"] = cat_scores

    category_scores = {}
    for cat, results in category_raw.items():
        scores = [
            next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
            for r in results
        ]
        category_scores[cat] = round(sum(scores) / len(scores), 1) if scores else 50

    weighted_score = sum(
        category_scores.get(cat, 50) * w
        for cat, w in weights_to_use.items()
    )

    cross_poll_results = []
    if len(agents) >= 2:
        print(f"\n  [{ticker}] Step 2 — Cross-pollination deliberation round...")
        cross_poll_results = run_cross_pollination_for_ticker(ticker, agents, agent_log)
        for cp in cross_poll_results:
            all_signals.append(cp.get("revised_signal", cp.get("original_signal", "HOLD")))
            weighted_score += cp.get("confidence_delta", 0) * 0.3
        weighted_score = max(0.0, min(100.0, weighted_score))

    total      = len(all_signals)
    buy_count  = all_signals.count("BUY")
    sell_count = all_signals.count("SELL")

    if   buy_count  / total >= 0.50: final_signal = "BUY"
    elif sell_count / total >= 0.40: final_signal = "SELL"
    else:                             final_signal = "HOLD"

    agent_reliability = {
        name: {"proper": log["proper_replies"], "failed": log["failed_replies"]}
        for name, log in agent_log.items()
    }
    return {
        "ticker":             ticker,
        "final_signal":       final_signal,
        "weighted_score":     round(weighted_score, 1),
        "buy_count":          buy_count,
        "sell_count":         sell_count,
        "hold_count":         total - buy_count - sell_count,
        "category_scores":    category_scores,
        "currency":           "EUR" if euro else "USD",
        "cross_pollination":  cross_poll_results,
        "agent_reliability":  agent_reliability,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5b — BULK MODE: EVERY AGENT RUNS EVERY CATEGORY INDEPENDENTLY
#
# Each agent makes 5 bulk calls (one per category, each containing 5 merged
# prompts). After both agents complete a category, a per-category
# cross-pollination round fires — so each agent revises its view for that
# specific factor before moving to the next.
#
# Call count per stock with --agent all (Claude + Gemini):
#   Claude : 5 bulk  +  5 cross-poll  =  10
#   Gemini : 5 bulk  +  5 cross-poll  =  10
#   Step 1 : +1 Claude (always)        → Claude total = 11 for the run
# ══════════════════════════════════════════════════════════════════════════════
def run_bulk_prompts_for_ticker(
    ticker: str, stock_data: dict, agents: list[BaseAgent], euro: bool = False, threaded: bool = False
) -> dict:
    all_signals        = []
    category_raw       = {}
    cross_poll_results = []
    agent_log          = {a.name: {"signals": [], "scores": [], "category_raw": {}, "proper_replies": 0, "failed_replies": 0} for a in agents}

    prompts_to_use = TRADE_REPUBLIC_PROMPTS if euro else ALL_PROMPTS
    weights_to_use = TR_CATEGORY_WEIGHTS    if euro else CATEGORY_WEIGHTS

    # Build all combined prompts upfront — same for every agent
    combined_prompts = {}
    prompt_key_map   = {}
    for category, prompts in prompts_to_use.items():
        prompt_keys = list(prompts.keys())
        prompt_key_map[category] = prompt_keys
        task_blocks = []
        for i, (prompt_key, template) in enumerate(prompts.items(), 1):
            filled = fill_prompt(template, stock_data)
            task_blocks.append(f"─── TASK {i}: {prompt_key} ───\n{filled.strip()}")
        keys_preview = "\n".join(f'  "{k}": {{ ...result... }}' for k in prompt_keys)
        combined_prompts[category] = (
            f"Answer ALL {len(prompts)} analysis tasks below for {ticker} "
            f"in ONE single JSON response.\n"
            f"Return ONLY a JSON object where each key is the exact task name "
            f"and each value is the full structured JSON result for that task.\n\n"
            f"Required top-level keys:\n{{\n{keys_preview}\n}}\n\n"
            + "\n\n".join(task_blocks)
        )

    if threaded and len(agents) > 1:
        # ── THREADED: each agent runs all categories in parallel ──────────────
        _lock = threading.Lock()

        def _run_agent_bulk(agent):
            for category, combined_prompt in combined_prompts.items():
                bulk_result = agent.fetch_data(combined_prompt)
                for prompt_key in prompt_key_map[category]:
                    sub       = bulk_result.get(prompt_key, {})
                    is_failed = not sub or ("error" in sub and "signal" not in sub)
                    if is_failed:
                        agent_log[agent.name]["failed_replies"] += 1
                        sig, score = "SKIP", "—"
                    else:
                        agent_log[agent.name]["proper_replies"] += 1
                        sig   = sub.get("signal", "HOLD")
                        score = next(
                            (v for k, v in sub.items() if k.endswith("_score") and isinstance(v, (int, float))),
                            50,
                        )
                        agent_log[agent.name]["signals"].append(sig)
                        agent_log[agent.name]["scores"].append(score)
                        agent_log[agent.name]["category_raw"].setdefault(category, []).append(sub)
                    with _lock:
                        print(f"    {ticker}  [{agent.name:6s}]  {category:16s}  {prompt_key:35s}  "
                              f"signal={sig:4s}  score={score}  [bulk/thread]")

        threads = [threading.Thread(target=_run_agent_bulk, args=(a,), name=a.name) for a in agents]
        for t in threads: t.start()
        for t in threads: t.join()

        for log in agent_log.values():
            all_signals.extend(log["signals"])
        for category in prompts_to_use:
            category_raw[category] = [
                r for a in agents for r in agent_log[a.name]["category_raw"].get(category, [])
            ]

        # Per-category cross-pollination after all threads complete
        if len(agents) >= 2:
            for category in prompts_to_use:
                print(f"\n  [{ticker}] Cross-pollination: {category}...")
                cat_agent_log = {}
                for a in agents:
                    cat_results = agent_log[a.name]["category_raw"].get(category, [])
                    cat_sigs    = [r.get("signal", "HOLD") for r in cat_results]
                    cat_scores  = [
                        next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
                        for r in cat_results
                    ]
                    avg = round(sum(cat_scores) / len(cat_scores), 1) if cat_scores else 50
                    cat_agent_log[a.name] = {
                        "signals":         cat_sigs,
                        "scores":          cat_scores,
                        "category_scores": {category: avg},
                    }
                cp = run_cross_pollination_for_ticker(ticker, agents, cat_agent_log)
                for c in cp:
                    c["_category"] = category
                    all_signals.append(c.get("revised_signal", c.get("original_signal", "HOLD")))
                cross_poll_results.extend(cp)

    else:
        # ── SEQUENTIAL: per-category with immediate cross-pollination ─────────
        for category, combined_prompt in combined_prompts.items():
            category_results = []
            for agent in agents:
                bulk_result = agent.fetch_data(combined_prompt)
                for prompt_key in prompt_key_map[category]:
                    sub       = bulk_result.get(prompt_key, {})
                    is_failed = not sub or ("error" in sub and "signal" not in sub)
                    if is_failed:
                        agent_log[agent.name]["failed_replies"] += 1
                        sig, score = "SKIP", "—"
                    else:
                        agent_log[agent.name]["proper_replies"] += 1
                        category_results.append(sub)
                        all_signals.append(sub.get("signal", "HOLD"))
                        sig   = sub.get("signal", "HOLD")
                        score = next(
                            (v for k, v in sub.items() if k.endswith("_score") and isinstance(v, (int, float))),
                            50,
                        )
                        agent_log[agent.name]["signals"].append(sig)
                        agent_log[agent.name]["scores"].append(score)
                        agent_log[agent.name]["category_raw"].setdefault(category, []).append(sub)
                    print(f"    {ticker}  [{agent.name:6s}]  {category:16s}  {prompt_key:35s}  "
                          f"signal={sig:4s}  score={score}  [bulk]")
            category_raw[category] = category_results

            if len(agents) >= 2:
                print(f"\n  [{ticker}] Cross-pollination: {category}...")
                cat_agent_log = {}
                for a in agents:
                    cat_results = agent_log[a.name]["category_raw"].get(category, [])
                    cat_sigs    = [r.get("signal", "HOLD") for r in cat_results]
                    cat_scores  = [
                        next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
                        for r in cat_results
                    ]
                    avg = round(sum(cat_scores) / len(cat_scores), 1) if cat_scores else 50
                    cat_agent_log[a.name] = {
                        "signals":         cat_sigs,
                        "scores":          cat_scores,
                        "category_scores": {category: avg},
                    }
                cp = run_cross_pollination_for_ticker(ticker, agents, cat_agent_log)
                for c in cp:
                    c["_category"] = category
                    all_signals.append(c.get("revised_signal", c.get("original_signal", "HOLD")))
                cross_poll_results.extend(cp)

    # Compute combined category scores (both agents merged)
    category_scores = {}
    for cat, results in category_raw.items():
        scores = [
            next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
            for r in results
        ]
        category_scores[cat] = round(sum(scores) / len(scores), 1) if scores else 50

    weighted_score = sum(
        category_scores.get(cat, 50) * w
        for cat, w in weights_to_use.items()
    )
    for cp in cross_poll_results:
        weighted_score += cp.get("confidence_delta", 0) * 0.3
    weighted_score = max(0.0, min(100.0, weighted_score))

    total      = len(all_signals)
    buy_count  = all_signals.count("BUY")
    sell_count = all_signals.count("SELL")

    if   buy_count  / total >= 0.50: final_signal = "BUY"
    elif sell_count / total >= 0.40: final_signal = "SELL"
    else:                             final_signal = "HOLD"

    agent_reliability = {
        name: {"proper": log["proper_replies"], "failed": log["failed_replies"]}
        for name, log in agent_log.items()
    }
    return {
        "ticker":            ticker,
        "final_signal":      final_signal,
        "weighted_score":    round(weighted_score, 1),
        "buy_count":         buy_count,
        "sell_count":        sell_count,
        "hold_count":        total - buy_count - sell_count,
        "category_scores":   category_scores,
        "currency":          "EUR" if euro else "USD",
        "cross_pollination": cross_poll_results,
        "agent_reliability": agent_reliability,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — RESULTS PRINTER
# ══════════════════════════════════════════════════════════════════════════════
def print_results(results: list[dict], euro: bool = False):
    sorted_results = sorted(results, key=lambda x: x.get("weighted_score", 0), reverse=True)
    currency_label = "EUR · Trade Republic" if euro else "USD · Global"
    width = 74
    print(f"\n{'='*width}")
    print(f"  SIGNAL MESH RESULTS [{currency_label}] — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*width}")
    print(f"  {'TICKER':<8} {'SIGNAL':<6} {'SCORE':>6}  {'BUY':>4} {'SELL':>4} {'HOLD':>4}  CATEGORY BREAKDOWN")
    print(f"  {'-'*70}")
    currency_sym = "€" if euro else "$"
    for r in sorted_results:
        cats = "  ".join(
            f"{c.split('_')[-1][:4].upper()}={v}" for c, v in r.get("category_scores", {}).items()
        )
        total_votes = r["buy_count"] + r["sell_count"] + r["hold_count"]
        print(
            f"  {r['ticker']:<8} {r['final_signal']:<6} {r['weighted_score']:>6.1f}  "
            f"{r['buy_count']:>4} {r['sell_count']:>4} {r['hold_count']:>4}  {cats}"
        )
    print(f"{'='*width}")
    top = sorted_results[0] if sorted_results else None
    if top and top["final_signal"] == "BUY":
        total_votes = top["buy_count"] + top["sell_count"] + top["hold_count"]
        print(f"\n  Top pick: {top['ticker']}  (score {top['weighted_score']}, "
              f"{top['buy_count']}/{total_votes} BUY votes)  [{currency_sym}]")

    # Cross-pollination summary (only when data is present)
    any_cp = any(r.get("cross_pollination") for r in sorted_results)
    if any_cp:
        print(f"\n  {'─'*70}")
        print(f"  CROSS-POLLINATION DELIBERATION SUMMARY")
        print(f"  {'─'*70}")
        for r in sorted_results:
            for cp in r.get("cross_pollination", []):
                orig    = cp.get("original_signal", "?")
                revised = cp.get("revised_signal",  "?")
                changed = cp.get("signal_changed",  False)
                delta   = int(cp.get("confidence_delta", 0))
                strength = cp.get("peer_argument_strength", "?")
                reason  = cp.get("revision_reason", "")[:72]
                marker   = "CHANGED" if changed else "held   "
                category = cp.get("_category", "")
                cat_tag  = f"  [{category}]" if category else ""
                print(f"  {r['ticker']:<6} [{cp.get('_agent','?'):6s} saw {cp.get('_peer','?'):6s}]{cat_tag}"
                      f"  {orig:4s}→{revised:4s}  {marker}  delta={delta:+d}  peer={strength}")
                if reason:
                    print(f"         \"{reason}\"")
        print(f"  {'─'*70}\n")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6b — TELEGRAM NOTIFICATION
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment variables.
# Sends a formatted HTML message with results + per-agent reliability stats.
# ══════════════════════════════════════════════════════════════════════════════

def _send_with_retry(url: str, chat_id: str, text: str, max_attempts: int = 3) -> None:
    """Send one Telegram message with exponential backoff on 429 / transient errors."""
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    for attempt in range(max_attempts):
        try:
            data = urllib.parse.urlencode(params).encode()
            req  = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode())
            if body.get("ok"):
                print("[TELEGRAM] Notification sent.")
            else:
                print(f"[TELEGRAM] API returned ok=false: {body}")
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = json.loads(e.read().decode()).get("parameters", {}).get("retry_after", 2 ** attempt)
                except Exception:
                    wait = 2 ** attempt
                print(f"[TELEGRAM] Rate limited (429), retrying in {wait}s...")
                if attempt < max_attempts - 1:
                    time.sleep(wait)
                    continue
            print(f"[TELEGRAM] HTTP error {e.code}: {e}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"[TELEGRAM] Send error: {e}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
    print("[TELEGRAM] Failed after max retries.")


def send_telegram_notification(results: list[dict], agents_label: str, euro: bool = False):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id   = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        print("[TELEGRAM] Skipped — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable.")
        return

    from lib_telegram_format import format_batch
    messages = format_batch(results, agents_label=agents_label, euro=euro)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for text in messages:
        _send_with_retry(url, chat_id, text)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — ACTIONS
# ══════════════════════════════════════════════════════════════════════════════
def action_fetch_data(euro: bool = False, agent_name: str = "claude", bulk_prompt: bool = False, threaded: bool = False, stock: str = None):
    # Build agent list for Step 3 (Step 1 always uses Claude)
    if agent_name == "all":
        agents = [ClaudeAgent(verbose=VERBOSE), GeminiAgent(verbose=VERBOSE), MistralAgent(verbose=VERBOSE)]
    elif agent_name == "gemini":
        agents = [GeminiAgent(verbose=VERBOSE)]
    elif agent_name == "mistral":
        agents = [MistralAgent(verbose=VERBOSE)]
    else:
        agents = [ClaudeAgent(verbose=VERBOSE)]

    agents_label = " + ".join(a.name for a in agents)
    mode = "EUR · Trade Republic" if euro else "USD · Global"
    currency_sym = "€" if euro else "$"
    bulk_label   = "  [BULK MODE: 1 call/category]" if bulk_prompt else ""
    thread_label = "  [THREADED: agents run in parallel]" if threaded and len(agents) > 1 else ""
    stock_label  = f"  stock=[{stock.upper()}]" if stock else ""
    print(f"\n{'='*60}")
    print(f"  SIGNAL MESH — fetch_data  [{mode}]  agents=[{agents_label}]{bulk_label}{thread_label}{stock_label}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*60}\n")

    # Step 1 — skip when --stock is provided, otherwise discover via Claude
    if stock:
        tickers = [stock.upper()]
        print(f"[Step 1] Skipped — using provided ticker: {stock.upper()}")
    else:
        print("[Step 1] Discovering trending stocks via Claude (always)...")
        step1_agent = ClaudeAgent(verbose=VERBOSE)
        tickers = discover_trending_stocks(step1_agent)
        tickers = tickers[:NUM_STOCKS]

    # Step 2 — fetch yfinance data for each ticker
    print(f"\n[Step 2] Fetching yfinance data for: {' '.join(tickers)}")
    stock_data_map = {}
    for ticker in tickers:
        data = fetch_stock_data(ticker)
        if "error" in data:
            print(f"  {ticker} ✗ {data['error']}")
        else:
            print(f"  {ticker} ✓  price={currency_sym}{data['price']}  rsi={data['rsi']}  "
                  f"pe={data['pe_ratio']}  vol={data['vol_trend']}")
            stock_data_map[ticker] = data

    if not stock_data_map:
        print("[ERROR] No stock data fetched. Aborting.")
        sys.exit(1)

    # Step 3 — run prompts per ticker
    prompt_set = "Trade Republic (EUR)" if euro else "Global (USD)"
    if bulk_prompt:
        n_agents  = len(agents)
        n_bulk    = 5 * n_agents          # each agent × 5 categories
        n_cp      = (5 * n_agents) if n_agents >= 2 else 0   # per-category cross-poll
        n_calls   = n_bulk + n_cp
        print(f"\n[Step 3] BULK MODE — {prompt_set}  agents=[{agents_label}]")
        print(f"         Per stock: {n_bulk} bulk calls ({n_agents} agents × 5 categories)"
              + (f"  +  {n_cp} cross-poll calls (5 categories × {n_agents} agents)" if n_cp else ""))
        print(f"         Total: {len(stock_data_map)} stocks × {n_calls} = "
              f"{len(stock_data_map)*n_calls} LLM calls  (25 prompts merged per agent per category)")
        run_fn = run_bulk_prompts_for_ticker
    else:
        n_calls = 25
        print(f"\n[Step 3] Running {n_calls} {prompt_set} prompts per stock via [{agents_label}] "
              f"({len(stock_data_map)} stocks × {n_calls} prompts = {len(stock_data_map)*n_calls} calls)")
        run_fn = run_all_prompts_for_ticker

    all_results = []
    for ticker, stock_data in stock_data_map.items():
        print(f"\n  --- {ticker} ---")
        result = run_fn(ticker, stock_data, agents=agents, euro=euro, threaded=threaded)
        all_results.append(result)

    # Step 4 — display results
    print_results(all_results, euro=euro)
    send_telegram_notification(all_results, agents_label, euro=euro)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
ACTIONS = {
    "fetch_data": action_fetch_data,
}

def main():
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    global VERBOSE
    parser = argparse.ArgumentParser(
        prog="signal_mesh_orchestrator",
        description="Signal Mesh — Claude Code CLI orchestrator",
    )
    parser.add_argument(
        "action",
        choices=list(ACTIONS.keys()),
        help="Action to run",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each prompt input and Claude output",
    )
    parser.add_argument(
        "--euro", "-e",
        action="store_true",
        help="Use Trade Republic / European prompts and display prices in EUR",
    )
    parser.add_argument(
        "--agent", "-a",
        choices=["claude", "gemini", "mistral", "all"],
        default="claude",
        help="AI agent to use for per-stock prompts: claude (default), gemini, mistral, or all (round-robin across all 3)",
    )
    parser.add_argument(
        "--bulk_prompt",
        action="store_true",
        help="Combine all 5 prompts per category into 1 LLM call (5 calls/stock instead of 25)",
    )
    parser.add_argument(
        "--thread", "-t",
        action="store_true",
        help="Run agents in parallel threads (each agent runs all prompts independently) instead of round-robin",
    )
    parser.add_argument(
        "--stock", "-s",
        default=None,
        metavar="TICKER",
        help="Skip stock discovery (Step 1) and analyse this specific ticker directly (e.g. NVDA, ASML, AAPL)",
    )
    parser.add_argument(
        "--output", "-o",
        nargs="?",
        const="auto",
        metavar="FILE",
        help="Save all output to FILE (omit filename for auto-timestamped file in ./outputs/)",
    )
    args = parser.parse_args()
    VERBOSE = args.verbose

    tee = None
    if args.output:
        if args.output == "auto":
            out_dir = Path(__file__).resolve().parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"signal_mesh_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
        else:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
        tee = _Tee(str(out_path))
        print(f"[OUTPUT] Saving to: {out_path}\n")

    try:
        ACTIONS[args.action](euro=args.euro, agent_name=args.agent, bulk_prompt=args.bulk_prompt, threaded=args.thread, stock=args.stock)
    finally:
        if tee:
            tee.close()
            # print goes to real stdout again here
            print(f"\n[OUTPUT] Saved to: {out_path}")


if __name__ == "__main__":
    main()
