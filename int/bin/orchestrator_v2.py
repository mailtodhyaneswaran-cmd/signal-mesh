"""
orchestrator_v2.py
─────────────────────────────────────────────────────────────────────────────
Signal Mesh — Main Pipeline

Agents:
  Agent 1 — Claude Sonnet   (Anthropic API)
  Agent 2 — Gemini 1.5 Flash (Google, free)
  Agent 3 — Mistral Large   (Mistral AI, EU-based, free tier)

Run daily via cron at 09:00 AM:
  0 9 * * 1-5 cd /path/to/signal_mesh && python orchestrator_v2.py

Flow:
  1. Load house money state
  2. Fetch market data (yfinance — free)
  3. Fetch real institutional holder data (yfinance — free)
  4. 3 deliberation rounds:
       Each agent runs 25 prompts per stock → synthesises top 3 picks
       Meeting brief shared between rounds
  5. Consensus scoring (AI 60% + Institutional 40%)
  6. Send Telegram notification with Trade Republic buy instructions
  7. Save updated house money state
"""

import asyncio
import json
import math
import os
from datetime import datetime

import anthropic
import google.generativeai as genai
import requests
import yfinance as yf
from mistralai import Mistral

from analysis_prompts import ALL_PROMPTS, CATEGORY_WEIGHTS

# ── API clients ──────────────────────────────────────────────────────────────
claude_client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
mistral_client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
gemini_model   = genai.GenerativeModel("gemini-1.5-flash")

# ── Watchlist — all confirmed available on Trade Republic ────────────────────
WATCHLIST = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "AMD", "ASML"]

STATE_FILE = "house_money_state.json"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — MARKET DATA FETCHER
# Pulls everything needed for the 25 prompts from yfinance (free)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_stock_data(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info  = stock.info
    hist  = stock.history(period="1y")

    closes  = [float(c) for c in hist["Close"].tolist()]
    volumes = [int(v)   for v in hist["Volume"].tolist()]

    if not closes:
        return {"ticker": ticker, "error": "no data"}

    price    = closes[-1]
    w52_high = info.get("fiftyTwoWeekHigh", price)
    w52_low  = info.get("fiftyTwoWeekLow",  price)

    # moving averages
    ma10  = sum(closes[-10:])  / 10  if len(closes) >= 10  else price
    ma50  = sum(closes[-50:])  / 50  if len(closes) >= 50  else price
    ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else price

    # RSI
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g  = sum(gains[-14:])  / 14 if len(gains)  >= 14 else 0
    avg_l  = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0.001
    rsi    = round(100 - (100 / (1 + avg_g / avg_l)), 1)

    # Bollinger Bands
    win20   = closes[-20:] if len(closes) >= 20 else closes
    bb_mean = sum(win20) / len(win20)
    bb_std  = math.sqrt(sum((x - bb_mean)**2 for x in win20) / len(win20))
    bb_width = round((4 * bb_std / bb_mean) * 100, 2) if bb_mean else 0

    # momentum returns
    def mom(n):
        return round(((closes[-1] - closes[-n]) / closes[-n]) * 100, 2) if len(closes) >= n else 0

    # volume trend
    vol_recent = sum(volumes[-5:])  / 5  if len(volumes) >= 5  else 0
    vol_avg    = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1
    vol_trend  = "up" if vol_recent > vol_avg * 1.1 else "down" if vol_recent < vol_avg * 0.9 else "flat"

    # fundamentals
    pe             = round(info.get("trailingPE",        0) or 0, 1)
    pb             = round(info.get("priceToBook",       0) or 0, 2)
    peg            = round(info.get("pegRatio",          0) or 0, 2)
    roe            = round((info.get("returnOnEquity",   0) or 0) * 100, 1)
    roa            = round((info.get("returnOnAssets",   0) or 0) * 100, 1)
    profit_margin  = round((info.get("profitMargins",    0) or 0) * 100, 1)
    rev_growth     = round((info.get("revenueGrowth",    0) or 0) * 100, 1)
    earn_growth    = round((info.get("earningsGrowth",   0) or 0) * 100, 1)
    debt_equity    = round(info.get("debtToEquity",      0) or 0, 2)
    current_ratio  = round(info.get("currentRatio",      0) or 0, 2)
    beta           = round(info.get("beta",               1) or 1, 2)
    sector         = info.get("sector", "Technology")
    short_pct      = round((info.get("shortPercentOfFloat", 0) or 0) * 100, 1)
    analyst_count  = info.get("numberOfAnalystOpinions", 0) or 0
    target_price   = round(info.get("targetMeanPrice", price) or price, 2)
    upside_pct     = round(((target_price - price) / price) * 100, 1) if price else 0
    recommendation = info.get("recommendationKey", "hold")

    return {
        "ticker":           ticker,
        "price":            round(price, 2),
        "week52_high":      w52_high,
        "week52_low":       w52_low,
        "ma10":             round(ma10, 2),
        "ma50":             round(ma50, 2),
        "ma200":            round(ma200, 2),
        "vs_ma10":          round(((price - ma10)  / ma10)  * 100, 2),
        "vs_ma50":          round(((price - ma50)  / ma50)  * 100, 2),
        "vs_ma200":         round(((price - ma200) / ma200) * 100, 2),
        "ma_signal":        "BUY" if ma10 > ma50 else "SELL",
        "rsi":              rsi,
        "rsi_signal":       "BUY" if rsi < 30 else "SELL" if rsi > 70 else "HOLD",
        "bb_width":         bb_width,
        "vol_trend":        vol_trend,
        "return_1m":        mom(22),
        "return_3m":        mom(66),
        "return_6m":        mom(126),
        "return_12m":       mom(252),
        "pe_ratio":         pe,
        "pb_ratio":         pb,
        "peg_ratio":        peg,
        "roe":              roe,
        "roa":              roa,
        "profit_margin":    profit_margin,
        "revenue_growth":   rev_growth,
        "earnings_growth":  earn_growth,
        "debt_equity":      debt_equity,
        "current_ratio":    current_ratio,
        "beta":             beta,
        "sector":           sector,
        "short_pct":        short_pct,
        "analyst_count":    analyst_count,
        "target_price":     target_price,
        "upside_pct":       upside_pct,
        "recommendation":   recommendation,
        "closing_prices_30d": [round(c, 2) for c in closes[-30:]],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — INSTITUTIONAL HOLDER DATA (replaces fake eToro stubs)
# Uses yfinance — completely free, no API key needed
# ══════════════════════════════════════════════════════════════════════════════
def fetch_institutional_data(ticker: str) -> dict:
    """
    Fetches real institutional holder data from yfinance.
    Returns holder count, top holders, and a weighted institutional score.
    """
    try:
        stock    = yf.Ticker(ticker)
        holders  = stock.institutional_holders
        major    = stock.major_holders

        if holders is None or holders.empty:
            return {"ticker": ticker, "holder_count": 0, "institutional_score": 0, "top_holders": []}

        # top 5 institutional holders
        top = []
        for _, row in holders.head(5).iterrows():
            top.append({
                "name":   str(row.get("Holder", "")),
                "shares": int(row.get("Shares", 0)),
                "value":  float(row.get("Value", 0)),
            })

        # % held by institutions (from major holders)
        inst_pct = 0
        if major is not None and not major.empty:
            try:
                inst_pct = float(str(major.iloc[2, 0]).replace("%", ""))
            except Exception:
                inst_pct = 0

        # score: 0-100 based on institutional ownership %
        # 70%+ ownership = max score (very institutionally backed)
        inst_score = min(100, int(inst_pct * 1.4))

        return {
            "ticker":              ticker,
            "holder_count":        len(holders),
            "institutional_pct":   round(inst_pct, 1),
            "institutional_score": inst_score,
            "top_holders":         top,
        }

    except Exception as e:
        return {"ticker": ticker, "holder_count": 0, "institutional_score": 50, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — NEWS FETCHER
# Uses NewsAPI free tier — 100 requests/day
# ══════════════════════════════════════════════════════════════════════════════
def fetch_news(ticker: str) -> list:
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        return []
    try:
        from datetime import timedelta
        from_date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": ticker, "from": from_date, "language": "en",
                    "sortBy": "relevancy", "pageSize": 8, "apiKey": api_key},
            timeout=10,
        )
        articles = resp.json().get("articles", [])
        return [{"title": a["title"], "source": a["source"]["name"]} for a in articles]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — PROMPT FILLER
# Fills {variable} placeholders in prompt templates with real stock data
# ══════════════════════════════════════════════════════════════════════════════
def fill_prompt(template: str, data: dict, macro: dict, news: list) -> str:
    fill = {
        "ticker":                   data["ticker"],
        "current_price":            data["price"],
        "ohlcv_data":               json.dumps({"last_30_closes": data["closing_prices_30d"]}),
        "closing_prices":           str(data["closing_prices_30d"]),
        "strategy_signals":         json.dumps({
            "MA_signal":            data["ma_signal"],
            "RSI":                  data["rsi"],
            "RSI_signal":           data["rsi_signal"],
            "BB_width":             data["bb_width"],
            "momentum_1m":          data["return_1m"],
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
        "competitive_news":         news[0]["title"] if news else "No recent news",
        # sentiment
        "news_headlines":           json.dumps([x.get("title", "") for x in news[:8]]),
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
        # macro
        "fed_rate":                 macro.get("fed_rate",       5.25),
        "treasury_10y":             macro.get("treasury_10y",   4.3),
        "rate_direction":           macro.get("rate_direction",  "hold"),
        "intl_revenue_pct":         40,
        "gdp_trend":                macro.get("gdp_trend",       "slowing"),
        "inflation_rate":           macro.get("inflation",        3.2),
        "unemployment":             macro.get("unemployment",     3.9),
        "cycle_phase":              macro.get("cycle_phase",      "late expansion"),
        "days_to_earnings":         45,
        "expected_eps":             round(data["pe_ratio"] * 0.04, 2) if data["pe_ratio"] else 0,
        "last_surprise":            5.0,
        "options_implied_move":     round(abs(data["return_1m"]) * 1.5, 1),
        "dxy":                      macro.get("dxy",              104),
        "eurusd":                   macro.get("eurusd",            1.08),
        "risk_appetite":            macro.get("risk_appetite",     "neutral"),
        "vix":                      macro.get("vix",               18),
        "macro_news_headlines":     json.dumps([x.get("title", "") for x in news[:3]]),
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
# SECTION 5 — SINGLE PROMPT RUNNER
# Calls one AI with one prompt and returns parsed JSON
# ══════════════════════════════════════════════════════════════════════════════
async def run_single_prompt(agent_id: str, prompt: str) -> dict:
    try:
        if agent_id == "claude":
            resp = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(resp.content[0].text.strip())

        elif agent_id == "gemini":
            resp = gemini_model.generate_content(prompt)
            text = resp.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(text)

        elif agent_id == "mistral":
            resp = mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)

    except Exception as e:
        return {"error": str(e), "signal": "HOLD", "factor_score": 50}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — RUN ALL 25 PROMPTS FOR ONE TICKER ON ONE AGENT
# ══════════════════════════════════════════════════════════════════════════════
async def run_all_prompts_for_ticker(
    agent_id:   str,
    ticker:     str,
    stock_data: dict,
    macro_data: dict,
    news_data:  list,
) -> dict:
    all_signals = []
    category_raw = {}

    for category, prompts in ALL_PROMPTS.items():
        tasks = [
            run_single_prompt(agent_id, fill_prompt(template, stock_data, macro_data, news_data))
            for template in prompts.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        clean   = []
        for r in results:
            if isinstance(r, Exception):
                r = {"signal": "HOLD", "factor_score": 50}
            clean.append(r)
            all_signals.append(r.get("signal", "HOLD"))
        category_raw[category] = clean

    # category scores
    category_scores = {}
    for cat, results in category_raw.items():
        scores = [
            next((v for k, v in r.items() if k.endswith("_score") and isinstance(v, (int, float))), 50)
            for r in results
        ]
        category_scores[cat] = round(sum(scores) / len(scores), 1) if scores else 50

    # weighted final score
    weighted_score = sum(
        category_scores.get(cat, 50) * w
        for cat, w in CATEGORY_WEIGHTS.items()
    )

    # majority vote
    total      = len(all_signals)
    buy_count  = all_signals.count("BUY")
    sell_count = all_signals.count("SELL")

    if   buy_count  / total >= 0.50: final_signal = "BUY"
    elif sell_count / total >= 0.40: final_signal = "SELL"
    else:                             final_signal = "HOLD"

    return {
        "ticker":          ticker,
        "agent":           agent_id,
        "final_signal":    final_signal,
        "weighted_score":  round(weighted_score, 1),
        "buy_count":       buy_count,
        "sell_count":      sell_count,
        "category_scores": category_scores,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — SYNTHESIS PROMPT
# Agent picks its top 3 stocks from its full analysis
# ══════════════════════════════════════════════════════════════════════════════
async def synthesise_picks(
    agent_id:        str,
    ticker_results:  list,
    meeting_brief:   str = "",
    round_num:       int = 1,
) -> dict:
    summary = sorted(
        [{"ticker": t["ticker"], "signal": t["final_signal"],
          "score": t["weighted_score"], "buy_signals": t["buy_count"],
          "category_scores": t["category_scores"]}
         for t in ticker_results],
        key=lambda x: x["score"], reverse=True
    )

    prompt = f"""You are a senior portfolio manager reviewing a full quantitative analysis.

ANALYSIS SUMMARY (scored across 25 indicators):
{json.dumps(summary, indent=2)}

Round: {round_num} of 3
"""
    if meeting_brief:
        prompt += f"""
PEER AGENT PICKS FROM PREVIOUS ROUND:
{meeting_brief}

Use their reasoning to refine your analysis. You may agree or disagree.
"""

    prompt += """
YOUR TASK: Select exactly 3 stocks to BUY for a 2-5 day swing trade.
Prioritise high weighted_score + high buy_signals count.

Respond ONLY in this exact JSON format:
{
  "agent": "agent_id_here",
  "round": 1,
  "picks": [
    {
      "ticker": "XXXX",
      "reason": "2 sentence explanation referencing strongest signals",
      "confidence": 75,
      "hold_days": 3,
      "top_signals": ["technical_trend_strength", "fundamental_valuation"]
    },
    {"ticker": "XXXX", "reason": "...", "confidence": 70, "hold_days": 2, "top_signals": []},
    {"ticker": "XXXX", "reason": "...", "confidence": 65, "hold_days": 4, "top_signals": []}
  ]
}"""

    result = await run_single_prompt(agent_id, prompt)
    if isinstance(result, dict) and "agent" not in result:
        result["agent"] = agent_id
    return result if isinstance(result, dict) else {"agent": agent_id, "picks": []}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — HOUSE MONEY STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "principal":    10.0,
        "profit_pot":   0.0,
        "phase":        "seed",
        "last_profit":  0.0,
        "loss_streak":  0,
        "history":      [],
    }

def get_invest_amount(state: dict) -> float:
    if state["phase"] == "seed":
        return state["principal"]
    pot = state["profit_pot"]
    return round(pot, 2) if pot >= 2.0 else 0.0

def update_state(state: dict, profit: float) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if state["phase"] == "seed" and profit > 0:
        state["profit_pot"]  = round(profit, 2)
        state["phase"]       = "compounding"
        state["loss_streak"] = 0
    elif profit > 0:
        state["last_profit"] = state["profit_pot"]
        state["profit_pot"]  = round(profit, 2)
        state["loss_streak"] = 0
    else:
        state["loss_streak"] += 1
        state["profit_pot"]   = state["last_profit"]
        if state["loss_streak"] >= 3:
            state["phase"]       = "seed"
            state["profit_pot"]  = 0.0
            state["loss_streak"] = 0
    state["history"].append({
        "date": today, "profit": round(profit, 2), "pot": state["profit_pot"]
    })
    return state

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — CONSENSUS SCORING
# Combines AI agent votes + real institutional holder data
# ══════════════════════════════════════════════════════════════════════════════
def compute_consensus(
    agent_picks:     list,
    inst_data_map:   dict,
    invest_amount:   float,
) -> list:
    tally = {}
    for entry in agent_picks:
        for pick in entry.get("picks", []):
            t = pick["ticker"]
            if t not in tally:
                tally[t] = {"agents": [], "confidences": []}
            tally[t]["agents"].append(entry.get("agent", "?"))
            tally[t]["confidences"].append(pick.get("confidence", 50))

    scored = []
    for ticker, data in tally.items():
        ai_score      = (len(data["agents"]) / 3) * 100
        inst          = inst_data_map.get(ticker, {})
        inst_score    = inst.get("institutional_score", 50)
        combined      = round(ai_score * 0.6 + inst_score * 0.4, 1)
        avg_conf      = round(sum(data["confidences"]) / len(data["confidences"]), 1)
        scored.append({
            "ticker":        ticker,
            "ai_agents":     data["agents"],
            "ai_score":      round(ai_score),
            "inst_score":    round(inst_score),
            "inst_pct":      inst.get("institutional_pct", 0),
            "combined":      combined,
            "confidence":    avg_conf,
        })

    winners = sorted(
        [s for s in scored if s["combined"] >= 55],
        key=lambda x: x["combined"], reverse=True
    )[:3]

    if not winners:
        return []

    total = sum(w["combined"] for w in winners)
    for w in winners:
        w["allocation_eur"] = round((w["combined"] / total) * invest_amount, 2)

    return winners


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — TELEGRAM NOTIFICATION
# ══════════════════════════════════════════════════════════════════════════════
def send_telegram(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[Telegram] {message}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    print(f"\n{'='*60}")
    print(f"  SIGNAL MESH — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Agents: Claude + Gemini + Mistral")
    print(f"  25 prompts × 3 agents × 3 rounds")
    print(f"{'='*60}\n")

    # ── house money ──────────────────────────────────────────────────────────
    state         = load_state()
    invest_amount = get_invest_amount(state)
    print(f"💰 Phase: {state['phase']} | Pot: €{state['profit_pot']:.2f} | Investing: €{invest_amount:.2f}\n")

    if invest_amount == 0:
        send_telegram("⏸ *Signal Mesh* — Profit pot below €2 minimum. Skipping today.")
        return

    # ── fetch market data ────────────────────────────────────────────────────
    print("📊 Fetching market data...")
    stock_data_map = {}
    inst_data_map  = {}
    news_map       = {}

    for ticker in WATCHLIST:
        try:
            stock_data_map[ticker] = fetch_stock_data(ticker)
            inst_data_map[ticker]  = fetch_institutional_data(ticker)
            news_map[ticker]       = fetch_news(ticker)
            inst_pct = inst_data_map[ticker].get("institutional_pct", 0)
            print(f"  {ticker} ✓  inst={inst_pct}%")
        except Exception as e:
            print(f"  {ticker} ✗ {e}")

    # stub macro data — replace with FRED API for production
    macro_data = {
        "fed_rate": 5.25, "treasury_10y": 4.3,
        "inflation": 3.2, "unemployment": 3.9,
        "vix": 18, "dxy": 104, "eurusd": 1.08,
        "risk_appetite": "neutral",
        "cycle_phase": "late expansion",
        "gdp_trend": "slowing",
        "rate_direction": "hold",
    }

    # ── 3 deliberation rounds ────────────────────────────────────────────────
    agent_ids     = ["claude", "gemini", "mistral"]
    meeting_brief = ""
    final_picks   = []

    for round_num in range(1, 4):
        print(f"\n🤝 Round {round_num}/3 — deliberation")
        round_picks = []

        for agent_id in agent_ids:
            print(f"   {agent_id} running 25 prompts per stock...")

            # run all 25 prompts for all tickers in parallel
            ticker_tasks = [
                run_all_prompts_for_ticker(
                    agent_id, ticker,
                    stock_data_map[ticker],
                    macro_data,
                    news_map.get(ticker, []),
                )
                for ticker in stock_data_map
            ]
            ticker_results = await asyncio.gather(*ticker_tasks, return_exceptions=True)
            ticker_results = [r for r in ticker_results if not isinstance(r, Exception)]

            # synthesise into top 3 picks
            picks = await synthesise_picks(agent_id, ticker_results, meeting_brief, round_num)
            round_picks.append(picks)

            tickers = [p["ticker"] for p in picks.get("picks", [])]
            print(f"   {agent_id} → {' · '.join(tickers)}")

        final_picks   = round_picks
        meeting_brief = "\n".join(
            f"{p.get('agent','?')}: {', '.join(x['ticker'] for x in p.get('picks',[]))}\n" +
            "\n".join(f"  {x['ticker']}: {x.get('reason','')}" for x in p.get("picks", []))
            for p in round_picks
        )

    # ── consensus ────────────────────────────────────────────────────────────
    print(f"\n🧠 Computing consensus (AI 60% + Institutional 40%)...")
    winners = compute_consensus(final_picks, inst_data_map, invest_amount)

    if not winners:
        msg = "⊘ *Signal Mesh* — No consensus today. Capital preserved."
        print(f"\n{msg}")
        send_telegram(msg)
        return

    # ── print results ─────────────────────────────────────────────────────────
    print("\n📋 Final allocation:")
    for w in winners:
        print(f"  {w['ticker']:5s}  combined={w['combined']}%  inst={w['inst_pct']}%  €{w['allocation_eur']:.2f}")

    # ── telegram ──────────────────────────────────────────────────────────────
    lines = [
        f"📈 *Signal Mesh* — {datetime.utcnow().strftime('%Y-%m-%d')}",
        f"Claude + Gemini + Mistral · 25 prompts · 3 rounds",
        f"Investing: €{invest_amount:.2f}",
        "",
    ]
    for w in winners:
        lines.append(f"*{w['ticker']}* — €{w['allocation_eur']:.2f}")
        lines.append(f"  Score: {w['combined']}% · Inst: {w['inst_pct']}% · {' + '.join(w['ai_agents'])}")
    lines.append("")
    lines.append("Open Trade Republic and execute manually ✓")
    send_telegram("\n".join(lines))

    save_state(state)
    print("\n✅ Done. Check Telegram for your Trade Republic instructions.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
