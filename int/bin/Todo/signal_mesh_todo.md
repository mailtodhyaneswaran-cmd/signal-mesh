# Signal Mesh — Build TODO List

> Multi-Agent AI Trading Orchestrator
> Share this file with Claude Code to work through tasks in order.

---

## Context

Signal Mesh is a Python CLI tool that:
- Uses Claude (Step 1) to discover 5 trending stocks
- Fetches market data via yfinance
- Runs 25 analysis prompts per stock across Claude + Gemini (5 categories × 5 prompts)
- Does a cross-pollination round where each agent sees the other's verdict and can revise
- Outputs a final BUY/SELL/HOLD signal with weighted score
- Sends results via Telegram

Main file: `signal_mesh_orchestrator.py`

---

## Priority Order: Do these in sequence

---

### TASK 1 — Replace fake ATR with real calculation
**File:** `signal_mesh_orchestrator.py`
**Where:** `fetch_stock_data()` function

**Problem:**
ATR is hardcoded as `price × 0.02` which is meaningless. ATR is used by agents to calculate stop-loss levels, so fake ATR = unreliable stop-loss suggestions.

**Fix:**
In `fetch_stock_data()`, yfinance already fetches `hist = stock.history(period="1y")`. Add High and Low extraction and compute real 14-day ATR:

```python
highs  = [float(h) for h in hist["High"].tolist()]
lows   = [float(l) for l in hist["Low"].tolist()]
tr_list = [
    max(highs[i] - lows[i],
        abs(highs[i] - closes[i-1]),
        abs(lows[i]  - closes[i-1]))
    for i in range(1, len(closes))
]
atr = round(sum(tr_list[-14:]) / 14, 2)
```

Then in `fill_prompt()`, replace:
```python
"atr": round(data["price"] * 0.02, 2),
```
with:
```python
"atr": data["atr"],
```

---

### TASK 2 — Fix hardcoded macro stubs
**File:** `signal_mesh_orchestrator.py`
**Where:** `MACRO_STUBS` dict (lines ~224–236) and `fill_prompt()`

**Problem:**
These values never update:
```python
MACRO_STUBS = {
    "fed_rate":      5.25,   # outdated
    "treasury_10y":  4.3,    # outdated
    "vix":           18,     # outdated
    "dxy":           104,    # outdated
    "eurusd":        1.08,   # outdated
    ...
}
```
The macro analysis category runs on stale fake data, making macro signals unreliable.

**Fix:**
Fetch live data using yfinance tickers before running analysis:
```python
import yfinance as yf

def fetch_macro_data() -> dict:
    tickers = {
        "vix":      "^VIX",
        "treasury_10y": "^TNX",
        "dxy":      "DX-Y.NYB",
        "eurusd":   "EURUSD=X",
        "sp500":    "^GSPC",
    }
    result = {}
    for key, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).fast_info
            result[key] = round(data.last_price, 2)
        except:
            result[key] = MACRO_STUBS[key]  # fallback to stub if fetch fails
    return result
```
Call this once at the start of `action_fetch_data()` and pass into `fill_prompt()`.

---

### TASK 3 — Fix empty sentiment / news data
**File:** `signal_mesh_orchestrator.py`
**Where:** `fill_prompt()` sentiment block (lines ~293–313)

**Problem:**
These are all hardcoded empty or fake:
```python
"news_headlines":       json.dumps([]),   # always empty
"macro_news_headlines": json.dumps([]),   # always empty
"wsb_trend":            "stable",         # hardcoded
"twitter_sentiment":    15,               # hardcoded
```
Agents are reasoning about sentiment with zero real news.

**Fix:**
Use yfinance `.news` property which is already available:
```python
def fetch_news_headlines(ticker: str) -> list[str]:
    try:
        stock = yf.Ticker(ticker)
        news  = stock.news or []
        return [n.get("title", "") for n in news[:5]]  # top 5 headlines
    except:
        return []
```
Add `"news_headlines": json.dumps(fetch_news_headlines(ticker))` in `fill_prompt()`.

---

### TASK 4 — Extract and surface stop-loss / take-profit in output
**File:** `signal_mesh_orchestrator.py`
**Where:** `run_all_prompts_for_ticker()`, `run_bulk_prompts_for_ticker()`, `print_results()`, `send_telegram_notification()`

**Problem:**
The volatility prompt (TR_T4_volatility_assessment) correctly generates:
- `suggested_stop_loss`
- `suggested_take_profit`
- `max_hold_days`

But the orchestrator discards them — only `signal` and `score` are extracted.

**Fix:**
In the prompt loop where results are processed, also check for and collect these fields:
```python
# After extracting sig and score, also check for trade levels
if "suggested_stop_loss" in result:
    stock_trade_levels["stop_loss"].append(result["suggested_stop_loss"])
if "suggested_take_profit" in result:
    stock_trade_levels["take_profit"].append(result["suggested_take_profit"])
if "max_hold_days" in result:
    stock_trade_levels["hold_days"].append(result["max_hold_days"])
```

Average the collected values and add to the final result dict:
```python
"stop_loss":  round(min(stock_trade_levels["stop_loss"]), 2),   # use most conservative
"take_profit": round(sum(stock_trade_levels["take_profit"]) / len(...), 2),
"max_hold_days": min(stock_trade_levels["hold_days"]),
```

Update `print_results()` to show:
```
NVDA  BUY  65.7   stop=€217.87  target=€230.00  hold=3 days
```

Update `send_telegram_notification()` to include the same in the Telegram message.

---

### TASK 5 — Add trend classification gate
**File:** `signal_mesh_orchestrator.py`
**Where:** After `fetch_stock_data()`, before running prompts

**Problem:**
MA data (ma10, ma50, ma200) is fetched but never used as a hard filter. A BUY signal in a downtrending stock is dangerous — the market disagrees with the agents.

**Fix:**
Add a `classify_trend()` function:
```python
def classify_trend(data: dict) -> str:
    price = data["price"]
    ma50  = data["ma50"]
    ma200 = data["ma200"]
    if price > ma50 and ma50 > ma200:
        return "UPTREND"
    elif price < ma50 and ma50 < ma200:
        return "DOWNTREND"
    else:
        return "SIDEWAYS"
```

Apply a score multiplier in the weighted score calculation:
```python
trend = classify_trend(stock_data)
multiplier = {"UPTREND": 1.0, "SIDEWAYS": 0.85, "DOWNTREND": 0.65}
weighted_score = weighted_score * multiplier[trend]
```

Add trend to output:
```
NVDA  BUY  65.7  [UPTREND]   stop=€217.87  target=€230.00
```

---

### TASK 6 — Add macro gate (pre-trade safety check)
**File:** `signal_mesh_orchestrator.py`
**Where:** After scoring, before printing results

**Problem:**
Signal Mesh can issue confident BUY signals right before earnings (huge volatility risk) or when VIX is spiking (market panic). No safety check exists.

**Fix:**
After computing `weighted_score` and `final_signal`, apply a macro gate:
```python
def apply_macro_gate(result: dict, stock_data: dict, vix: float) -> dict:
    warnings = []
    if vix > 25:
        warnings.append(f"VIX={vix} (market stress)")
        result["weighted_score"] *= 0.80
    if stock_data.get("days_to_earnings", 99) <= 3:
        warnings.append(f"Earnings in {stock_data['days_to_earnings']} days")
        result["weighted_score"] *= 0.70
        result["final_signal"] = "HOLD"  # never buy into earnings
    result["macro_warnings"] = warnings
    return result
```

Show warnings in output and Telegram:
```
MU  BUY  57.7  [UPTREND]  ⚠️ Earnings in 2 days → overridden to HOLD
```

---

### TASK 7 — Add minimum 3:1 risk/reward gate
**File:** `signal_mesh_orchestrator.py`
**Where:** After stop-loss/take-profit are extracted (requires Task 4 done first)

**Problem:**
Paul Tudor Jones principle — never take a trade where potential reward is less than 3× the risk. Currently Signal Mesh outputs BUY with no regard for whether the trade setup is actually worth taking.

**Fix:**
```python
def check_risk_reward(entry: float, stop: float, target: float) -> float:
    risk   = entry - stop
    reward = target - entry
    if risk <= 0:
        return 0
    return round(reward / risk, 2)

rr = check_risk_reward(stock_data["price"], result["stop_loss"], result["take_profit"])
if rr < 3.0 and result["final_signal"] == "BUY":
    result["final_signal"] = "HOLD"
    result["rr_warning"] = f"R:R = {rr} (below 3:1 minimum)"
```

---

### TASK 8 — Build house money tracking system
**File:** `house_money.py` (new file)

**Problem:**
No system exists to track trades, P&L, or the house money balance. The core strategy (only reinvest profits, protect principal) cannot be implemented without this.

**Fields to track per trade:**
```
date, ticker, signal_score, entry_price, exit_price,
shares_or_units, profit_eur, fees_eur, net_profit_eur,
house_money_balance, notes
```

**Starting values:**
- Principal: €300 (never touched)
- Profit pool: €0 (grows from winning trades)
- Target: €30 profit minimum

**Implementation:**
- Store in `trade_log.csv` in the `outputs/` folder
- Add CLI command: `python signal_mesh_orchestrator.py log_trade`
- On each run, load and display current house money balance at the top of output

---

### TASK 9 — Add conviction-based position sizing
**File:** `house_money.py` (new file, builds on Task 8)

**Problem:**
No guidance on how much to allocate per trade. Druckenmiller principle: position size should match your conviction level.

**Fix — map weighted_score to position size from profit pool:**
```
Score >= 80  → allocate 50% of profit pool
Score 70–79  → allocate 30% of profit pool
Score 55–69  → allocate 15% of profit pool
Score < 55   → SKIP (not worth the risk)
```

Output in results:
```
NVDA  BUY  65.7  → allocate €15.00 from profit pool (15%)
```

---

### TASK 10 — Add consensus penalty for near-identical agent scores
**File:** `signal_mesh_orchestrator.py`
**Where:** weighted_score calculation block

**Problem:**
When Claude and Gemini scores differ by less than 5 points and both say BUY, it likely means the trade is already priced in (Soros reflexivity — everyone sees the same signal). This was validated in the ETF savings plan experiment.

**Fix:**
```python
agent_scores = [log["scores"] for log in agent_log.values() if log["scores"]]
if len(agent_scores) >= 2:
    avg_scores = [sum(s)/len(s) for s in agent_scores]
    score_diff = abs(avg_scores[0] - avg_scores[1])
    if score_diff < 5.0 and final_signal == "BUY":
        weighted_score -= 7.5  # consensus penalty
        consensus_penalty_applied = True
```

---

### TASK 11 — Add Mistral as third agent
**File:** `lib_agents_mistral.py` (new file)

**Problem:**
Original Signal Mesh design had 3 agents. Only Claude + Gemini implemented. Two-agent cross-pollination risks echo chamber behaviour.

**Fix:**
Create `lib_agents_mistral.py` following the same `BaseAgent` interface as `lib_agents_claude.py` and `lib_agents_gemini.py`. Add `--agent mistral` and update `--agent all` to include all three.

---

### TASK 12 — Fix approximated quant fields
**File:** `signal_mesh_orchestrator.py`
**Where:** `fill_prompt()` quant block (lines ~335–358)

**Problem:**
Several fields are rough estimates:
- `ev_ebitda = pe_ratio × 0.75` (made up)
- `p_fcf = pe_ratio × 0.85` (made up)
- `pe_percentile = min(100, pe_ratio / 0.5)` (nonsense formula)

**Fix:**
Replace with real yfinance fields where available:
```python
info.get("enterpriseToEbitda", 0)   # real EV/EBITDA
info.get("freeCashflow", 0)         # real FCF (compute p_fcf from this)
```

---

### TASK 13 — Add trade execution log CLI command
**File:** `signal_mesh_orchestrator.py`

**Problem:**
When a trade is manually executed on IBKR based on Signal Mesh output, there is no way to record it against the original signal.

**Fix:**
Add CLI action `log_trade` that prompts:
```
Ticker:       NVDA
Entry price:  222.32
Exit price:   229.80
Shares:       0.45
Fees (EUR):   1.00
```
Writes to `outputs/trade_log.csv` and prints updated house money balance.

---

## Summary Table

| # | Task | Priority | File | Status |
|---|------|----------|------|--------|
| 1 | Real ATR calculation | HIGH | orchestrator | ⬜ TODO |
| 2 | Fix macro stubs (live data) | HIGH | orchestrator | ⬜ TODO |
| 3 | Fix empty sentiment/news | HIGH | orchestrator | ⬜ TODO |
| 4 | Extract stop-loss/take-profit | HIGH | orchestrator | ⬜ TODO |
| 5 | Trend classification gate | HIGH | orchestrator | ⬜ TODO |
| 6 | Macro gate (VIX + earnings) | HIGH | orchestrator | ⬜ TODO |
| 7 | Minimum 3:1 risk/reward gate | MEDIUM | orchestrator | ⬜ TODO |
| 8 | House money tracking system | MEDIUM | house_money.py | ⬜ TODO |
| 9 | Conviction-based position sizing | MEDIUM | house_money.py | ⬜ TODO |
| 10 | Consensus penalty | MEDIUM | orchestrator | ⬜ TODO |
| 11 | Mistral as third agent | MEDIUM | lib_agents_mistral.py | ⬜ TODO |
| 12 | Fix approximated quant fields | LOW | orchestrator | ⬜ TODO |
| 13 | Trade execution log CLI | LOW | orchestrator | ⬜ TODO |

---

*Generated from Signal Mesh session — May 2026*
