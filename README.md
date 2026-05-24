# Signal Mesh

A multi-agent AI stock analysis system. Three LLM backends (Claude, Gemini, Mistral) independently analyse stocks, deliberate with each other, and produce a consensus BUY / SELL / HOLD signal. Results are delivered via Telegram notification and saved to a timestamped output file.

---

## How It Works

```
Step 1 — Claude discovers 3 trending stocks (ticker + buzz score + sentiment)
Step 2 — yfinance fetches market data for each ticker
            (price, RSI, MAs, Bollinger Bands, fundamentals, volume trend)
Step 3 — Each agent answers 25 analysis prompts across 5 categories
            Technical · Fundamental · Sentiment · Macro · Quant
Step 4 — Cross-pollination: each agent sees its peer's thesis and may revise its signal
Step 5 — Votes are tallied → weighted score → final signal per stock
Step 6 — Results printed to terminal + saved to file + Telegram notification sent
```

### The 5 Analysis Categories

| Category | Weight | What it measures |
|---|---|---|
| Technical | 25% | Price action, RSI, moving averages, Bollinger Bands, momentum |
| Fundamental | 25% | P/E, P/B, PEG, revenue/earnings growth, margins, debt |
| Sentiment | 20% | Analyst ratings, price targets, insider activity, short interest |
| Macro | 15% | Fed rate, yield curve, DXY, sector cycle, earnings calendar |
| Quant | 15% | Factor composites, momentum percentiles, earnings revision |

### Signal Decision Rule

```
BUY  — ≥ 50% of all votes are BUY
SELL — ≥ 40% of all votes are SELL
HOLD — everything else
```

---

## Features

| Feature | Status |
|---|---|
| Trending stock discovery via Claude (Step 1) | ✅ |
| yfinance market data fetcher | ✅ |
| 25 prompts per stock across 5 categories | ✅ |
| Three agent backends: Claude, Gemini, Mistral | ✅ |
| Round-robin prompt distribution across agents | ✅ |
| Parallel threaded agents (`--thread`) | ✅ |
| Bulk mode — 1 LLM call per category (`--bulk_prompt`) | ✅ |
| Cross-pollination deliberation round | ✅ |
| EUR / Trade Republic prompt set (`--euro`) | ✅ |
| Per-agent reliability stats (proper vs failed replies) | ✅ |
| Output saved to timestamped file (`--output`) | ✅ |
| Telegram notification with results + reliability | ✅ |
| Automated daily run Mon–Fri 09:00 AM (Windows Task Scheduler) | ✅ |
| Configurable stock count (`NUM_STOCKS`) | ✅ |
| Single-stock mode — skip discovery, analyse one ticker directly (`--stock`) | ✅ |
| Telegram bot — trigger analysis on demand via `/ticker` command | ✅ |

---

## Project Structure

```
signal_mesh/
├── .env                          # API keys (gitignored — never commit)
├── .gitignore
├── pyproject.toml
├── run_signal_mesh.bat           # Windows Task Scheduler launcher
├── history.md                    # Detailed change log
├── signal_mesh_spec.md           # Full system specification
└── int/bin/
    ├── signal_mesh_orchestrator.py   # Main entry point
    ├── analysis_prompts.py           # All 25 prompts + category weights
    ├── lib_agents.py                 # BaseAgent abstract class
    ├── lib_agents_claude.py          # Claude agent (Claude Code CLI)
    ├── lib_agents_gemini.py          # Gemini agent (Google AI SDK)
    ├── lib_agents_mistral.py         # Mistral agent (mistralai SDK)
    ├── lib_env.py                    # .env loader (no external deps)
    ├── ask_gemini.py                 # CLI wrapper to test Gemini directly
    ├── ask_mistral.py                # CLI wrapper to test Mistral directly
    ├── telegram_bot.py               # Interactive Telegram bot (/ticker command)
    ├── test_telegram.py              # Sends a sample Telegram notification
    └── outputs/                      # Timestamped run output files (gitignored)
```

---

## Setup

### 1. Prerequisites

- Python 3.11+
- A virtual environment (recommended)
- Claude Code CLI installed and authenticated

### 2. Install dependencies

```bash
pip install yfinance
pip install google-generativeai
pip install mistralai
```

### 3. Configure API keys

Create a `.env` file in the project root (copy the template below — never commit this file):

```
# .env — project root
GEMINI_API_KEY=your_gemini_key_here
MISTRAL_API_KEY=your_mistral_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

Where to get keys:
- **Gemini** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Mistral** — [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys)
- **Telegram** — create a bot via [@BotFather](https://t.me/BotFather), get chat ID via `https://api.telegram.org/bot<TOKEN>/getUpdates`
- **Claude** — no API key needed; uses the Claude Code CLI already authenticated on your machine

---

## Usage

All commands are run from the project root.

### Basic run (Claude only, USD mode)

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data
```

### All three agents, EUR mode, verbose output

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data --agent all --euro --verbose
```

### Bulk mode — faster, 1 LLM call per category instead of 25

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data --agent all --bulk_prompt
```

### Threaded mode — agents run all prompts in parallel

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data --agent all --thread
```

### Save output to a timestamped file

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data --agent all --output
# saves to int/bin/outputs/signal_mesh_YYYY-MM-DD_HHMMSS.txt
```

### Analyse a specific stock (skip discovery)

```bash
# Analyse NVDA with all agents
python int/bin/signal_mesh_orchestrator.py fetch_data --stock NVDA --agent all

# Analyse a European stock in EUR mode
python int/bin/signal_mesh_orchestrator.py fetch_data --stock ASML.AS --euro --agent all

# Quick single-stock check with Claude only
python int/bin/signal_mesh_orchestrator.py fetch_data -s AAPL
```

### Full production run (all flags)

```bash
python int/bin/signal_mesh_orchestrator.py fetch_data -v -e --agent all --bulk_prompt --thread --output
```

---

## CLI Flags

| Flag | Short | Description |
|---|---|---|
| `fetch_data` | | Action to run (required) |
| `--agent` | `-a` | `claude` (default) · `gemini` · `mistral` · `all` |
| `--stock` | `-s` | Skip discovery — analyse this specific ticker directly |
| `--euro` | `-e` | Use Trade Republic / EUR prompt set |
| `--verbose` | `-v` | Print every prompt input and agent output |
| `--bulk_prompt` | | 1 LLM call per category instead of 25 |
| `--thread` | `-t` | Agents run all prompts in parallel threads |
| `--output` | `-o` | Save output to file (auto-timestamped) |

### Ticker format for `--stock`

Uses yfinance ticker symbols:

| Market | Example tickers |
|---|---|
| US stocks | `NVDA`, `AAPL`, `MSFT`, `TSLA` |
| Amsterdam (AEX) | `ASML.AS`, `HEIA.AS`, `PHIA.AS` |
| Frankfurt (XETRA) | `SAP.DE`, `BMW.DE`, `SIE.DE` |
| Paris (Euronext) | `MC.PA`, `TTE.PA`, `AIR.PA` |
| ETFs | `SPY`, `QQQ`, `IWDA.AS` |

EU stocks require the exchange suffix (`.AS`, `.DE`, `.PA`). Without it yfinance falls back to the US-listed ADR, which may have different pricing data.

---

## Agent Modes Explained

### Round-robin (default)

Prompts are distributed one-by-one across agents in order. With 3 agents and 25 prompts, each agent handles ~8-9 prompts. Total votes: 25 + cross-pollination.

```
Prompt 1 → Claude
Prompt 2 → Gemini
Prompt 3 → Mistral
Prompt 4 → Claude
...
```

### Threaded (`--thread`)

Each agent runs **all 25 prompts independently** in a separate thread. Threads run in parallel. Total votes: 75 (25 per agent) + cross-pollination. More votes, more robust signal — slower to return first output but all agents finish at the same time.

### Bulk + Threaded (`--bulk_prompt --thread`)

Each agent processes all 5 categories in parallel. Each bulk call contains 5 merged prompts. Total: 5 calls per agent instead of 25, all running simultaneously.

---

## Cross-Pollination

When two or more agents are active, a deliberation round fires after all prompts complete:

1. Each agent receives the other agent's composite thesis (signal, score, category breakdown, vote counts).
2. The agent may revise its signal or hold its original position.
3. Revised signals are added to the vote pool.
4. `confidence_delta` from each revision adjusts the weighted score by `delta × 0.3`.

In bulk mode, cross-pollination fires per category immediately after each category completes (sequential mode) or after all threads join (threaded mode).

---

## Configurable Constants

At the top of `int/bin/signal_mesh_orchestrator.py`:

```python
VERBOSE    = False   # set True to always print prompts (same as --verbose flag)
NUM_STOCKS = 3       # how many stocks to analyse per run
```

Change `NUM_STOCKS` to analyse more or fewer stocks. Claude's discovery prompt always asks for 5 candidates; the list is sliced to `NUM_STOCKS` after discovery.

---

## Telegram Notifications

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. The notification is sent automatically at the end of every run and includes:

- Ranked results table with signal emoji (🟢 BUY · 🔴 SELL · 🟡 HOLD), score, and vote counts
- Top pick highlight (when final signal is BUY)
- Per-agent reliability stats (proper replies / total, with ✅ / ⚠️ / ❌ icon)

To test Telegram without running a full analysis:

```bash
python int/bin/test_telegram.py
```

---

## Telegram Bot (On-Demand Analysis)

`telegram_bot.py` is a persistent bot that listens for commands and triggers analysis on demand, replying directly in the chat.

### Start the bot

```bash
python int/bin/telegram_bot.py
```

Leave it running in a terminal. The bot uses long-polling — no webhook or public URL needed.

### Commands

| Command | Description |
|---|---|
| `/ticker <STOCK>` | Analyse with Claude (default) |
| `/ticker <STOCK> all` | Analyse with all 3 agents |
| `/ticker <STOCK> gemini` | Analyse with Gemini only |
| `/ticker <STOCK> mistral` | Analyse with Mistral only |
| `/ticker <STOCK> claude` | Analyse with Claude only |
| `/help` | Show usage and ticker format guide |

### Example

```
You:  /ticker NVDA all
Bot:  🔍 Starting analysis for NVDA with [Claude + Gemini + Mistral]...
Bot:  ⏳ Fetching market data for NVDA...
Bot:  📈 Data fetched. Running 25 prompts... (This takes a few minutes)

      — 2–5 minutes later —

Bot:  📊 Signal Mesh — NVDA
      2026-05-24 09:14 UTC  ·  [Claude + Gemini + Mistral]

      🟢 BUY  score: 71.4
      Votes: 32 BUY · 8 SELL · 10 HOLD (50 total)

      Category Breakdown:
        TECH: 74.1
        FUND: 68.3
        SENT: 71.0
        MACR: 69.5
        QUAN: 72.8

      Agent Reliability:
        ✅ Claude: 25/25 (100%)
        ✅ Gemini: 24/25 (96%)
        ⚠️ Mistral: 18/25 (72%)
```

The bot only responds to your configured `TELEGRAM_CHAT_ID` — messages from any other chat are silently ignored.

---

## Automated Daily Run (Windows)

`run_signal_mesh.bat` is registered as a Windows Task Scheduler task named `SignalMesh_Daily`.  
It runs every **Monday–Friday at 09:00 AM** and executes:

```
fetch_data -v -e --agent all --bulk_prompt --output
```

To remove the task:

```powershell
schtasks /delete /tn SignalMesh_Daily /f
```

To re-register it manually, open PowerShell as Administrator and run:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\...\run_signal_mesh.bat"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:00AM
Register-ScheduledTask -TaskName "SignalMesh_Daily" -Action $action -Trigger $trigger -RunLevel Highest
```

---

## Testing Individual Agents

```bash
# Test Gemini directly
python int/bin/ask_gemini.py "Analyse NVDA and return JSON with signal and factor_score"

# Test Mistral directly
python int/bin/ask_mistral.py "What is the current macroeconomic outlook for tech stocks?"
```

---

## Output Example

```
======================================================================
  SIGNAL MESH RESULTS [EUR · Trade Republic] — 2026-05-22 09:14 UTC
======================================================================
  TICKER   SIGNAL  SCORE   BUY SELL HOLD  CATEGORY BREAKDOWN
  ──────────────────────────────────────────────────────────────────
  MU       BUY      68.3    29    8   16  TECH=71.2  FUND=65.4  SENT=68.1  MACR=66.0  QUAN=70.5
  ANET     BUY      61.7    24   10   19  TECH=63.0  FUND=60.1  SENT=59.8  MACR=62.5  QUAN=63.4
  APP      HOLD     52.1    18   14   21  TECH=51.2  FUND=53.0  SENT=50.4  MACR=52.8  QUAN=53.1
======================================================================

  Top pick: MU  (score 68.3, 29/53 BUY votes)  [€]
```

---

## Disclaimer

This tool is for research and educational purposes only. It does not constitute financial advice. Always do your own research before making investment decisions.
