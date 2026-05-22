# Signal Mesh — Full Technical Specification
### Semi-Autonomous AI Trading System with Android Monitoring App

**Version:** 1.0  
**Author:** Dhyanes  
**Date:** May 2026

---

## Table of Contents

1. [Vision & Overview](#1-vision--overview)
2. [System Architecture](#2-system-architecture)
3. [Three Operating Modes](#3-three-operating-modes)
4. [Android App — Full Screen Specification](#4-android-app--full-screen-specification)
5. [Laptop Server — Full Component Specification](#5-laptop-server--full-component-specification)
6. [Signal Mesh Deliberation Engine](#6-signal-mesh-deliberation-engine)
7. [API Contracts](#7-api-contracts)
8. [Human-in-the-Loop (HITL) Flow](#8-human-in-the-loop-hitl-flow)
9. [Notification System](#9-notification-system)
10. [Database Schema](#10-database-schema)
11. [Subscriptions & Costs](#11-subscriptions--costs)
12. [Honest Assessment](#12-honest-assessment)
13. [Build Hours Estimate](#13-build-hours-estimate)
14. [Break-Even Analysis](#14-break-even-analysis)
15. [Recommended Build Order](#15-recommended-build-order)

---

## 1. Vision & Overview

Signal Mesh is a **semi-autonomous swing trading system** built around a multi-agent AI deliberation engine. Three AI models (Claude, Gemini, Grok) independently analyse stocks, debate their findings, and reach a consensus before any trade is executed. The human owner retains full veto power and can also interact with the system conversationally.

### Core Philosophy

- **Server = The Swing Trader** — thinks, decides, executes autonomously
- **Android App = The Portfolio Monitor** — observes, alerts, and allows human override
- **Human = The Risk Manager** — sets rules, vetoes when needed, asks questions

### Capital Preservation Rules (baked into system)

- Principal amount is sacred — never risked in full
- Only profits are compounded back into the trading account
- Weekly P&L review cycle, not daily
- Monthly principal boost from profits only
- Max 100 trades per day hard limit

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ANDROID APP                          │
│                                                         │
│  📊 Dashboard      🤖 Chat / Consult                   │
│  📋 Trade Log      👁️  Agent Debate View               │
│  ⚙️  Settings       🛑 Halt / Kill Switch              │
│  📈 Manual Trade   🔔 Approval Notifications           │
│  📉 Weekly P&L     💼 Portfolio Overview               │
└──────────────────────────┬──────────────────────────────┘
                           │
              WebSocket (real-time feed)
              REST API (commands, queries)
              FCM Push (trade approvals)
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  LAPTOP SERVER                          │
│                                                         │
│  🔄 Autonomous Swing Trader Loop                       │
│  💬 Interactive Query Handler                          │
│  🧠 Signal Mesh Deliberation Engine                    │
│  ⚖️  State Machine (pending/halt/run/veto)             │
│  📦 Trade Executor (broker API)                        │
│  🗄️  Database (trades, signals, chat, P&L)            │
│  📡 FCM Notification Dispatcher                        │
│  🌐 Market Data Fetcher                                │
└──────────────────────────┬──────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       Claude API     Gemini API      Grok API
       (Analyst 1)   (Analyst 2)   (Analyst 3)
```

### Network Connectivity

- **Tailscale** (recommended) — private VPN mesh, phone reaches laptop securely from anywhere
- Alternative: **ngrok** with a stable domain ($10/month)
- All traffic over HTTPS even on Tailscale

---

## 3. Three Operating Modes

### Mode 1 — Autonomous (Default)

The server runs its swing trader loop continuously during trading hours. It scans the watchlist, runs Signal Mesh deliberation, and sends approval notifications before executing.

```
Every 15 minutes during trading hours:
  1. Fetch price + volume + news data for watchlist
  2. Send context to Claude, Gemini, Grok independently
  3. Collect individual signals (BUY / SELL / HOLD + confidence)
  4. Run deliberation round (agents see each other's reasoning)
  5. Apply 60/40 scoring formula
  6. If consensus threshold met → enter PENDING_APPROVAL state
  7. Push FCM notification to phone with 3-minute approval window
  8. On approval or timeout → execute trade via broker API
  9. Log to database, update WebSocket feed
```

### Mode 2 — Manual Override

User initiates a trade directly from the app, bypassing AI consensus entirely.

```
User opens Manual Trade screen
  → Selects stock, quantity, direction (BUY/SELL), price type
  → Confirms on app
  → Server receives manual trade instruction
  → Executes immediately via broker API
  → Logged as "MANUAL" type (separate from bot trades in P&L)
```

### Mode 3 — Interactive Consultation

User chats with the system naturally. The three AIs deliberate and respond with a consensus recommendation.

```
User types: "What do you think about semiconductor stocks right now?"

Server receives query
  → Identifies query type (sector scan / specific stock / portfolio question)
  → Sends to Claude, Gemini, Grok with context:
      - Current portfolio positions
      - User's risk profile
      - Watchlist
      - Recent trade history
  → Each AI responds independently
  → Deliberation round: AIs see each other's picks
  → Server synthesises consensus summary
  → Returns to app as chat response with action buttons:
      [Add to Watchlist]  [Initiate Buy Analysis]  [Dismiss]
```

---

## 4. Android App — Full Screen Specification

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Kotlin |
| UI Framework | Jetpack Compose |
| HTTP Client | Retrofit + OkHttp |
| Real-time | WebSocket (OkHttp) |
| Push Notifications | Firebase Cloud Messaging (FCM) |
| Charts | Vico or MPAndroidChart |
| Local Storage | Room Database |
| Navigation | Jetpack Navigation Compose |
| DI | Hilt |

### Screen 1 — Dashboard (Home)

- System status pill: RUNNING / PAUSED / HALTED
- Current open positions with live P&L
- Consensus meter: live bar showing current agent agreement level
- Active watchlist with last signal per stock
- Recent activity feed (last 5 actions)
- Prominent red HALT ALL button
- Weekly P&L summary card
- Principal gauge (visual showing principal is intact)

### Screen 2 — Live Agent Feed

- Real-time stream of what each agent is doing
- Three columns: Claude / Gemini / Grok
- Each column shows current analysis state, signal, and confidence
- Deliberation thread view — see the "debate" as it happens
- Consensus result banner when threshold is reached

### Screen 3 — Trade Approval Screen

Opened via notification tap when a trade is pending.

- Stock name, ticker, direction (BUY/SELL)
- Quantity and price
- Which agents voted what
- News catalyst that triggered the signal
- Confidence score
- Countdown timer (3 minutes)
- [APPROVE] and [VETO] buttons — large, thumb-friendly
- If timer expires with no action: auto-executes (configurable)

### Screen 4 — Trade Log

- Full history of all trades
- Filter by: Manual / Bot / Vetoed
- Each entry: timestamp, stock, direction, price, P&L outcome, agents' consensus score
- Tap any trade to see full agent debate for that decision

### Screen 5 — Chat / Consultation

- Chat interface (similar to messaging app)
- Type naturally: stock tickers, sectors, portfolio questions
- Responses show consensus summary + individual agent breakdowns
- Action buttons inline in chat: Add to Watchlist, Initiate Analysis, Manual Trade
- Chat history persisted locally

### Screen 6 — Manual Trade

- Stock search (ticker or name)
- Direction: BUY / SELL
- Quantity input
- Order type: Market / Limit / Stop
- Price input (for limit/stop orders)
- Pre-trade summary with estimated cost
- Confirmation screen before submission

### Screen 7 — Watchlist Manager

- Add stocks by ticker or sector keyword
- Remove from watchlist
- Set per-stock alerts (e.g. only notify if 2/3 agents agree)
- Sector watchlists (e.g. "Semiconductors", "Healthcare")

### Screen 8 — Weekly P&L Review

- Week selector
- Total profit/loss for the week
- Trade-by-trade breakdown
- Bot trades vs manual trades comparison
- Principal status (protected / at risk indicator)
- Monthly compounding summary

### Screen 9 — Settings

- API Key management (Claude, Gemini, Grok, Broker)
- Keys stored encrypted on server — app only sends them over HTTPS
- Risk parameters: max trades/day, approval window duration, auto-execute on timeout toggle
- Notification preferences
- Trading hours configuration
- Server connection settings (Tailscale address)

### Screen 10 — Kill Switch / Halt Screen

- Accessible from any screen via persistent button
- HALT ALL: cancels all pending trades, pauses loop
- RESUME: restarts autonomous loop
- Emergency sell all positions button (with double-confirm)
- Server status diagnostics

### Notification Types

| Notification | Content | Action on Tap |
|---|---|---|
| Trade Approval | "Bot wants to BUY 10x ASML — 3 min to respond" | Opens Trade Approval Screen |
| Trade Executed | "Bought 10x ASML at €742 ✓" | Opens Trade Log |
| Trade Vetoed | "Your veto cancelled ASML buy" | Opens Trade Log |
| Consensus Alert | "3/3 agents agree on NVDA — analysis ready" | Opens Agent Feed |
| Weekly Summary | "Week P&L: +€340 | Principal: Safe" | Opens Weekly P&L |
| System Alert | "Server halted — connection lost" | Opens Kill Switch Screen |

---

## 5. Laptop Server — Full Component Specification

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| API Framework | FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL (or SQLite for solo use) |
| WebSocket | FastAPI native WebSocket |
| FCM Dispatcher | firebase-admin SDK |
| Scheduler | APScheduler |
| Broker Integration | ccxt (crypto) or Alpaca/IBKR (stocks) |
| Market Data | yfinance, Alpha Vantage, or Polygon.io |
| Tunneling | Tailscale (recommended) |

### Server Components

#### 5.1 Swing Trader Loop (Autonomous Engine)

```python
# Runs every 15 minutes during trading hours
async def swing_trader_loop():
    stocks = get_watchlist()
    market_data = fetch_market_data(stocks)
    news = fetch_news(stocks)
    
    for stock in stocks:
        context = build_context(stock, market_data, news, portfolio)
        signals = await run_signal_mesh(context)
        
        if signals.consensus_reached:
            await enter_pending_approval(stock, signals)
```

#### 5.2 State Machine

States: `IDLE` → `ANALYSING` → `PENDING_APPROVAL` → `EXECUTING` → `COMPLETED`  
Interrupt states: `VETOED`, `HALTED`, `FAILED`

#### 5.3 Interactive Query Handler

```python
# Receives chat queries from app
async def handle_consultation(query: str, user_context: dict):
    enriched = enrich_query(query, portfolio, watchlist, history)
    responses = await asyncio.gather(
        ask_claude(enriched),
        ask_gemini(enriched),
        ask_grok(enriched)
    )
    debate = await run_deliberation(responses)
    return synthesise_response(debate)
```

#### 5.4 Trade Executor

- Connects to broker API (Alpaca, IBKR, Trade Republic if API available)
- Validates trade against risk parameters before submission
- Logs all executions with broker confirmation reference
- Handles partial fills, rejections, and retries

#### 5.5 FCM Dispatcher

- Sends actionable notifications with approval/veto buttons
- Tracks notification delivery and read status
- Handles approval responses from app

#### 5.6 REST API Endpoints

```
GET  /status                  — Server health, current mode, active state
GET  /portfolio               — Current positions, P&L
GET  /trades                  — Trade history (paginated)
GET  /watchlist               — Current watchlist
POST /watchlist               — Add stock or sector
DELETE /watchlist/{ticker}    — Remove from watchlist
GET  /signals/live            — Current agent signals
POST /trade/manual            — Submit manual trade
POST /trade/{id}/approve      — Approve pending trade
POST /trade/{id}/veto         — Veto pending trade
POST /halt                    — Halt all activity
POST /resume                  — Resume autonomous loop
POST /chat                    — Send consultation query
GET  /pnl/weekly              — Weekly P&L summary
GET  /pnl/monthly             — Monthly summary + compounding status
POST /settings/apikeys        — Update AI/broker API keys
WS   /ws/feed                 — WebSocket: real-time event stream
```

---

## 6. Signal Mesh Deliberation Engine

### Phase 1 — Independent Analysis

Each AI receives identical context:
- Stock data (OHLCV, volume, technicals)
- Recent news headlines and sentiment
- Current portfolio context
- User risk profile
- Historical performance of this signal type

Each AI returns:
```json
{
  "signal": "BUY | SELL | HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "catalysts": ["..."],
  "risk_factors": ["..."],
  "target_price": 0.0,
  "stop_loss": 0.0
}
```

### Phase 2 — Deliberation Round

Each AI sees the other two agents' signals and reasoning. They can:
- Maintain their position
- Revise their confidence
- Flag a disagreement with specific reasoning

### Phase 3 — Consensus Scoring (60/40 Formula)

```
Score = (AI Consensus Weight × 0.60) + (Technical/Fundamental Data Weight × 0.40)

AI Consensus Weight:
  - 3/3 agreement = 1.0
  - 2/3 agreement = 0.67
  - 1/3 agreement = 0.33 (no trade)

Consensus threshold to trade: Score ≥ 0.70
```

### Phase 4 — Decision

- Score ≥ 0.70 → Enter PENDING_APPROVAL, notify user
- Score < 0.70 → Log as INSUFFICIENT_CONSENSUS, continue monitoring

---

## 7. API Contracts

### WebSocket Feed Event Types

```json
{ "type": "AGENT_SIGNAL", "agent": "claude", "ticker": "ASML", "signal": "BUY", "confidence": 0.82 }
{ "type": "CONSENSUS_REACHED", "ticker": "ASML", "score": 0.78, "direction": "BUY" }
{ "type": "TRADE_PENDING", "id": "t_001", "ticker": "ASML", "expires_at": "2026-05-11T10:15:00Z" }
{ "type": "TRADE_EXECUTED", "id": "t_001", "ticker": "ASML", "price": 742.50, "qty": 10 }
{ "type": "TRADE_VETOED", "id": "t_001", "reason": "user_veto" }
{ "type": "SERVER_HALTED", "reason": "user_command" }
{ "type": "LOOP_TICK", "timestamp": "...", "stocks_scanned": 12 }
```

---

## 8. Human-in-the-Loop (HITL) Flow

```
Signal Mesh reaches consensus (score ≥ 0.70)
          ↓
Server enters PENDING_APPROVAL — no trade yet
          ↓
FCM notification pushed to phone:
  "⚠️ Bot wants to BUY 10x ASML at €742
   3/3 agents in agreement — Score: 78%
   [APPROVE]  [VETO]  — 3 minutes to respond"
          ↓
    ┌─────┴──────┐──────────────┐
    ↓            ↓              ↓
[APPROVE]     [VETO]      [No response]
    ↓            ↓              ↓
Execute      Cancel        Auto-execute
  trade       trade         (configurable:
  now        log veto       can also be
                            auto-cancel)
```

### Kill Switch Behaviour

1. User taps HALT ALL from any screen
2. All PENDING_APPROVAL trades immediately cancelled
3. Running deliberation cycles terminated
4. No new scan cycles started
5. Server enters HALTED state
6. All open broker orders optionally cancelled (configurable)
7. Server stays HALTED until explicit RESUME from app

---

## 9. Notification System

### Implementation Stack

- **Firebase Cloud Messaging (FCM)** — push delivery
- **firebase-admin** Python SDK on server
- **Android FCM SDK** in app
- Actionable notifications with inline buttons (Android 7+)

### Approval Notification Deep Link

```
Notification tap → deep link → app navigates to TradeApprovalScreen(tradeId)
Inline [APPROVE] tap → POST /trade/{id}/approve (no app open required)
Inline [VETO] tap → POST /trade/{id}/veto (no app open required)
```

---

## 10. Database Schema

### Tables

```sql
trades          — id, ticker, direction, qty, price, status, type(BOT/MANUAL), 
                  consensus_score, broker_ref, created_at, executed_at

signals         — id, trade_id, agent, signal, confidence, reasoning, created_at

deliberations   — id, trade_id, round, agent_from, agent_to, content, created_at

chat_history    — id, role(user/assistant), content, created_at

watchlist       — id, ticker, sector, added_at, alert_threshold

portfolio       — id, ticker, qty, avg_price, current_price, updated_at

pnl_snapshots   — id, period(weekly/monthly), profit, loss, net, principal_status,
                  compounded_amount, created_at

server_events   — id, type, payload, created_at
```

---

## 11. Subscriptions & Costs

### Essential (Cannot Skip)

| Service | Purpose | Cost |
|---|---|---|
| **Tailscale** | Secure tunnel: phone → laptop | Free (personal) |
| **Firebase** | FCM push notifications | Free tier sufficient |
| **Anthropic (Claude API)** | AI Agent 1 | Pay-per-use ~€10-30/month |
| **Google (Gemini API)** | AI Agent 2 | Free tier or ~€10-20/month |
| **xAI (Grok API)** | AI Agent 3 | ~€10-20/month |
| **Broker API** | Trade execution | Depends (see below) |

### Market Data (Pick One)

| Service | Quality | Cost |
|---|---|---|
| **yfinance** | Delayed, good for testing | Free |
| **Alpha Vantage** | Near real-time, 500 req/day free | Free / €40/month premium |
| **Polygon.io** | Professional quality | €25/month (Starter) |
| **Quiver Quant** | Political trading data bonus | Free tier / €25/month |

### Broker API (Pick One)

| Broker | Market | API Cost | Notes |
|---|---|---|---|
| **Alpaca** | US stocks | Free | Best API for retail algo trading |
| **Interactive Brokers** | Global incl. AEX | Free with account | Complex but powerful |
| **Trade Republic** | EU stocks | No public API yet | Manual execution only for now |
| **DEGIRO** | EU stocks | Unofficial API only | Not recommended for automation |

### Optional But Useful

| Service | Purpose | Cost |
|---|---|---|
| Google Play Developer | Publish app publicly | €25 one-time |
| **Redis Cloud** | Task queue (if not running locally) | Free tier |
| **ngrok** | Alternative to Tailscale | Free / €10/month |

### Total Monthly Cost Estimate

| Scenario | Monthly Cost |
|---|---|
| **Minimum (testing, paper trading)** | €0-5 |
| **Active trading, free tiers** | €20-40 |
| **Full production setup** | €60-100 |

---

## 12. Honest Assessment

### What Is Strong About This Idea

This is a genuinely well-architected concept. The multi-agent deliberation with a consensus threshold is a meaningful structural advantage over single-model or pure technical analysis systems. The capital preservation mandate and house money compounding are the right psychological guardrails. The HITL approval window is smart — it keeps you in the loop without requiring constant attention. Most retail algo trading systems are either too simple (single indicator bots) or too complex to maintain. This sits in a practical middle ground.

### Real Risks to Name Honestly

**The AI models are not trained on financial data in real-time.** Claude, Gemini, and Grok will reason about stocks using general knowledge and whatever context you provide — not live order flow, dark pool data, or institutional positioning. Their edge is reasoning quality, not information speed.

**Consensus does not equal correctness.** Three AIs agreeing can mean three models sharing the same bias, not three independent validations. The "consensus penalty" concept you explored earlier is the right antidote — you should weight disagreement as a signal too.

**Execution speed is a real limitation.** Swing trading is forgiving on this — you are not competing with HFT firms for milliseconds. But if your market data is delayed, your entry and exit prices will suffer.

**Broker API availability in the Netherlands is a genuine constraint.** Trade Republic does not yet have a public API. DEGIRO's unofficial API is fragile. Interactive Brokers is the most reliable choice for EU-listed stocks and ETFs.

**The laptop must be on and connected during trading hours.** Power cuts, laptop sleep, VPN drops — all of these stop the system. A cheap VPS or cloud server would be more reliable long-term.

### Overall Verdict

This is a serious, buildable project with a coherent philosophy. The risk is not whether the idea is good — it is. The risk is that **building it to a production-ready standard takes significant time**, and **the market does not care how well-engineered your system is**. Paper trade for at minimum 3 months before putting real money in.

---

## 13. Build Hours Estimate

### Phase 1 — Backend Foundation (Server)

| Task | Hours |
|---|---|
| FastAPI project setup, DB schema, basic endpoints | 15 |
| Signal Mesh deliberation engine (3 agents, scoring) | 25 |
| Autonomous swing trader loop + state machine | 20 |
| Broker API integration (Alpaca or IBKR) | 15 |
| Market data fetcher + watchlist scanner | 10 |
| FCM notification dispatcher | 8 |
| Interactive consultation handler (chat mode) | 15 |
| Tailscale setup + HTTPS configuration | 4 |
| **Phase 1 Total** | **112 hours** |

### Phase 2 — Android App

| Task | Hours |
|---|---|
| Project setup, navigation, architecture (MVVM) | 10 |
| Dashboard screen + WebSocket connection | 15 |
| Agent feed / debate view screen | 12 |
| Trade approval screen + notification deep link | 15 |
| Trade log screen | 8 |
| Chat / consultation screen | 15 |
| Manual trade screen | 10 |
| Watchlist manager | 8 |
| Weekly P&L screen | 10 |
| Settings + API key management | 8 |
| Kill switch / halt screen | 5 |
| FCM integration + actionable notifications | 10 |
| **Phase 2 Total** | **126 hours** |

### Phase 3 — Integration, Testing, Paper Trading

| Task | Hours |
|---|---|
| End-to-end integration testing | 20 |
| Paper trading (no real money) — 3 months observation | 0 build hours |
| Bug fixes and refinements | 25 |
| Performance tuning | 10 |
| **Phase 3 Total** | **55 hours** |

### Total Build Hours Summary

| Phase | Hours |
|---|---|
| Backend (server) | 112 |
| Android app | 126 |
| Integration + testing | 55 |
| **Grand Total** | **~293 hours** |

### Realistic Timeline

Given your full-time role at ASML, assuming **10 hours/week** of focused evening and weekend work:

- Phase 1 complete: ~11 weeks
- Phase 2 complete: ~24 weeks (cumulative)
- Phase 3 + paper trading: ~30 weeks (cumulative)
- **First real trade: approximately 8-9 months from today**

If you use Claude Code to accelerate scaffolding, you can likely cut 30-40% off build time — bringing it closer to **5-6 months**.

---

## 14. Break-Even Analysis

### Monthly Costs at Full Production

| Item | Cost |
|---|---|
| AI APIs (3 models) | €50 |
| Market data (Polygon.io starter) | €25 |
| Miscellaneous (Redis, domains) | €10 |
| **Total monthly overhead** | **~€85/month** |

### What You Need to Break Even

To cover €85/month in costs, you need the trading account to generate at minimum **€85/month in net profit after broker commissions**.

### Scenario Modelling

| Account Size | Monthly Return Needed | % Return Needed |
|---|---|---|
| €1,000 | €85 | 8.5% — very aggressive, high risk |
| €3,000 | €85 | 2.8% — achievable but demanding |
| €5,000 | €85 | 1.7% — realistic for a good month |
| €10,000 | €85 | 0.85% — comfortable and sustainable |

### Honest Probability Estimate

**With paper trading validation first + disciplined risk management:**

- Months 1-3 (paper): Learning phase, no profit or cost
- Months 4-6 (real, small size): Break-even is uncertain — some months yes, some no
- Months 7-12 (refined system): Realistic to cover costs consistently with €5k+ account

**Key insight:** The system does not need to be highly profitable to be valuable. If it generates 1-2% monthly on a €5k account, that is €50-100/month — enough to cover costs and slowly compound. The real value is removing emotion from decisions, not beating hedge funds.

### The Path to Profitability

1. Paper trade 3 months — validate the consensus model actually works on your watchlist
2. Start with €1,000-2,000 real capital — expect to lose some, treat it as tuition
3. Only scale up after 3 consecutive profitable months
4. Reinvest profits to grow account, never add to a losing strategy

---

## 15. Recommended Build Order

### Week 1-2: Foundation
- Set up Python/FastAPI project structure
- PostgreSQL schema
- Basic watchlist and market data fetching
- Connect one AI (Claude) and get a signal back

### Week 3-5: Signal Mesh Core
- Add Gemini and Grok
- Build deliberation engine
- Implement scoring formula
- Test consensus logic with historical data

### Week 6-8: State Machine + HITL
- Build full state machine (PENDING → EXECUTE → COMPLETE)
- FCM notification setup
- Approval/veto logic
- Halt/resume logic

### Week 9-11: Broker Integration
- Connect Alpaca (paper trading account first)
- Execute test trades
- Validate P&L logging

### Week 12-17: Android App
- Build screens in order: Dashboard → Trade Log → Notifications → Chat → Manual Trade → Settings

### Week 18-20: Integration
- Connect app to server end-to-end
- Test all notification flows
- Paper trade on real market data

### Month 5-7: Paper Trading Observation
- Run system autonomously, observe decisions
- Track how often you would have vetoed
- Refine consensus threshold and scoring

### Month 8+: Go Live
- Start with small real capital
- Review weekly P&L religiously
- Scale only after proven consistent results

---

*This document is a living specification. Update it as the system evolves.*
