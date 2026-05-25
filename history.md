# Signal Mesh — Change History

---

## 2026-05-22 — `/get` monitoring command + session persistence

**Files added:** `int/bin/lib_get_state.py`, `int/bin/lib_market_hours.py`, `int/bin/lib_telegram_format.py`  
**Files changed:** `int/bin/telegram_bot.py`, `int/bin/analysis_prompts.py`, `int/bin/signal_mesh_orchestrator.py`, `.gitignore`

### What changed

**1. `/get` command — continuous stock monitoring loop**
- New bot command: `/get <STOCK> [agent] [runs=N] [interval=M] [mode=verbose|quiet]`
- Runs repeated analysis on a single stock at a configurable interval (default 30 min, min 5 min).
- Run #1 uses a baseline prompt; runs 2–N use a delta prompt that injects the baseline + previous run as context, so the LLM focuses on *what has changed*.
- In quiet mode (default), only sends a one-line pulse per run unless the signal changes or `|score_delta| >= 5`.
- In verbose mode, sends a full formatted report every run.
- Sessions survive bot restarts — incomplete sessions are resumed from SQLite on startup.
- Market-hours gating: skips analysis when the exchange is closed (weekends + outside trading window); waits until next open without counting the skipped interval against the total run count.

**2. Companion commands**
- `/stop [TICKER]` — cancel the active monitoring session (all sessions if no ticker given).
- `/status` — list all active sessions with progress.
- `/summary [TICKER]` — session summary: signal stability %, flip count, price range, score range, last signal.
- `/help` — full command reference including ticker format guide and notes.

**3. `lib_get_state.py` — SQLite session persistence**
- Two tables: `get_sessions` (one row per session) and `get_runs` (one row per analysis run).
- WAL mode for concurrent read/write safety.
- Functions: `create_session`, `save_run`, `get_baseline`, `get_previous_run`, `mark_session_complete`, `cancel_session`, `list_active_sessions`, `get_session`, `get_session_runs`, `get_run_count`, `get_active_session_for_ticker`.
- DB at `int/bin/get_state.db` (gitignored).

**4. `lib_market_hours.py` — market-hours gating**
- Exchange detection by ticker suffix: `.AS`/`.PA` → Euronext 08:00–16:30 UTC, `.DE` → XETRA 07:00–15:30 UTC, no suffix → US 13:30–20:00 UTC.
- Optionally uses `pandas_market_calendars` for holiday-aware scheduling; falls back to UTC window + weekday check if not installed.
- Public API: `is_market_open(ticker)`, `next_market_open(ticker)`.

**5. `lib_telegram_format.py` — Telegram report formatting**
- `format_report(parsed, run_n, total_runs, interval_min)` — full HTML report with signal-flip banner, score/confidence, delta vs baseline, trade levels (entry/stop/target/R:R), category breakdown with delta arrows, thesis, catalysts, risks, watch_for. Splits at 4096-char Telegram limit at the THESIS section.
- `format_pulse(parsed, run_n, total_runs)` — one-liner for quiet mode.
- `format_summary(session, runs)` — session summary table.

**6. `analysis_prompts.py` additions**
- `SINGLE_TICKER_BASELINE_PROMPT` — baseline prompt with full market data, fundamentals, sector/macro, and JSON output schema including trade levels and category breakdown.
- `SINGLE_TICKER_DELTA_PROMPT` — delta prompt injecting baseline + previous run as context; extended schema adds `signal_changed_from_baseline`, `change_reason`, `score_delta_vs_baseline`, `price_delta_vs_baseline_pct`, per-category `delta` fields.
- `build_baseline_prompt(ticker, data, total_runs, interval_min, currency)` — string builder.
- `build_delta_prompt(ticker, data, run_n, baseline, previous, total_runs, interval_min)` — string builder; computes `elapsed_min` from baseline timestamp.

**7. `signal_mesh_orchestrator.py` additions**
- `fetch_single_ticker_data(ticker)` — richer yfinance fetch with OHLCV: day_change_pct, SMA20, MACD(12,26,9), Bollinger bands, ATR(14), today/avg volume, P/E (TTM + fwd), PEG, EPS/revenue growth, operating margin, D/E ratio, next earnings date.
- `analyze_single_ticker(ticker, stock_data, agent_name, run_n, session_id, interval_min, total_runs)` — dispatches baseline or delta prompt, handles single/multi-agent (majority vote for signal, average scores, merged catalyst/risk lists).

**8. Mistral error handling improved**
- All error returns stripped of `"signal": "HOLD"` and `"factor_score": 50` so failed responses are correctly identified as SKIP.
- Added `_parse_retry_delay(exc)` to extract retry delay from 429 responses (mirrors Gemini pattern).
- Rate-limit detection uses both "rate limit" and "too many requests" patterns.

**9. Telegram whitelist support**
- `TELEGRAM_WHITELIST` env var added: comma-separated chat IDs that can trigger the bot.
- Whitelisted users get results; `MAIN_CHAT` always receives a copy tagged "requested by @user".

### Bot usage examples
```
/get NVDA 10 interval=15       — 10 runs every 15 min, quiet mode
/get ASML.AS all runs=5 verbose — 5 runs with all agents, full report each time
/stop NVDA                     — cancel NVDA session
/status                        — list all active sessions
/summary NVDA                  — session summary for NVDA
```

---

## 2026-05-23 — `--stock` flag + Telegram bot

**Files added:** `int/bin/telegram_bot.py`
**Files changed:** `int/bin/signal_mesh_orchestrator.py`

### What changed

**1. `--stock` / `-s` CLI flag**
- Skips Step 1 (stock discovery via Claude) and runs analysis directly for the provided ticker.
- Accepts any ticker symbol recognised by yfinance (e.g. `NVDA`, `ASML.AS`, `SAP.DE`).
- All other flags (`--agent`, `--bulk_prompt`, `--thread`, `--euro`, `--output`) still apply.
- Usage:
  ```
  python int/bin/signal_mesh_orchestrator.py fetch_data --stock NVDA --agent all
  python int/bin/signal_mesh_orchestrator.py fetch_data -s ASML.AS -e --agent all --bulk_prompt
  ```

**2. `int/bin/telegram_bot.py` — interactive Telegram bot**
- Long-polling bot (no webhook needed, works from any network).
- Accepts commands only from `TELEGRAM_CHAT_ID` configured in `.env` (all other senders are silently ignored).
- **`/ticker <STOCK> [agent]`** — runs Signal Mesh analysis for that stock and replies with results.
  - `agent` defaults to `claude`; valid values: `claude · gemini · mistral · all`
  - Sends an acknowledgment immediately, runs analysis in a background thread, sends result when done.
- **`/help`** — shows usage and ticker format guide.
- Ticker format guide included in bot help:
  - US: `NVDA`, `AAPL`, `MSFT`
  - EU: `ASML.AS`, `SAP.DE`, `MC.PA` (exchange suffix required)
  - ETFs: `SPY`, `QQQ`, `IWDA.AS`
- Usage:
  ```
  python int/bin/telegram_bot.py
  ```

### Example bot interaction
```
You:  /ticker NVDA all
Bot:  🔍 Starting analysis for NVDA with [Claude + Gemini + Mistral]...
Bot:  ⏳ Fetching market data for NVDA...
Bot:  📈 Data fetched. Running 25 prompts... (This takes a few minutes)
Bot:  📊 Signal Mesh — NVDA
      2026-05-23 09:14 UTC  ·  [Claude + Gemini + Mistral]
      🟢 BUY  score: 71.4
      Votes: 32 BUY · 8 SELL · 10 HOLD (50 total)
      ...
```

---

## 2026-05-22 — Parallel Threads + NUM_STOCKS

**File changed:** `int/bin/signal_mesh_orchestrator.py`

### What changed

**1. `--thread` / `-t` flag**
- New CLI flag: `--thread` (or `-t`).
- When set with `--agent all` (or any multi-agent config), each agent is spawned in its own `threading.Thread` and runs **all prompts independently in parallel**, instead of the default round-robin distribution.
- Works for both normal mode and `--bulk_prompt` mode:
  - Normal: each agent thread loops over all 25 prompts (5 categories × 5 prompts each).
  - Bulk: each agent thread loops over all 5 categories, one bulk call per category.
- Cross-pollination runs sequentially after all threads join (requires all agents' results).
- A `threading.Lock` serialises `print()` calls to prevent interleaved output.
- With 3 agents + `--thread`, the vote pool grows to 75 signals (vs 25 round-robin) — each agent votes on every question.

**2. `NUM_STOCKS` — configurable stock count**
- Added `NUM_STOCKS = 3` constant after `VERBOSE = False` at the top of the file.
- After STEP1 discovers tickers, the list is sliced to `tickers[:NUM_STOCKS]` so only 3 stocks are analysed even though Claude discovers 5.
- Change the constant to analyse more or fewer stocks without touching the prompt.

**3. Thread label in header**
- When `--thread` is active and there are multiple agents, the run header now prints `[THREADED: agents run in parallel]` alongside the existing bulk/agent labels.

### Usage examples
```
# Parallel threads, all 3 agents, EUR mode, bulk prompts, output file
python int/bin/signal_mesh_orchestrator.py fetch_data -v -e --agent all --bulk_prompt --thread --output

# Parallel threads, all 3 agents, USD mode, normal prompts
python int/bin/signal_mesh_orchestrator.py fetch_data --agent all --thread
```

### Current capabilities of the script

| Feature | Status |
|---|---|
| Step 1: Discover trending stocks via Claude | ✅ |
| Step 2: Fetch yfinance data (price, RSI, MA, fundamentals, …) | ✅ |
| Step 3: Run 25 prompts per stock across 5 categories | ✅ |
| Agent backends: Claude, Gemini, Mistral, or all (round-robin) | ✅ |
| Bulk mode (`--bulk_prompt`): 1 LLM call per category instead of 25 | ✅ |
| Threaded mode (`--thread`): agents run all prompts in parallel | ✅ |
| Cross-pollination deliberation round (multi-agent only) | ✅ |
| EUR / Trade Republic mode (`--euro`) | ✅ |
| Output to file (`--output`) with tee to stdout | ✅ |
| Failed agent responses marked SKIP, excluded from vote pool | ✅ |
| Per-agent reliability stats tracked and returned per stock | ✅ |
| Telegram notification with results + reliability stats at run end | ✅ |
| Automated daily run Mon–Fri 09:00 AM via Windows Task Scheduler | ✅ |
| Telegram smoke-test script (`test_telegram.py`) | ✅ |
| Configurable stock count via `NUM_STOCKS` constant | ✅ |

---

## 2026-05-22 — Mistral Agent fixed + working

**Root cause of install issues:**
- `mistralai` v2.4.5 is a Speakeasy-generated SDK — it does NOT put `Mistral` at the top-level namespace. The correct import is `from mistralai.client import Mistral`, not `from mistralai import Mistral` (which the docs show but doesn't work with this release).
- A failed `--force-reinstall` had left a `~-stralai-2.4.5.dist-info` ghost directory. Deleting the stale dist-info and reinstalling fixed the package directory.
- `ask_mistral.py` needed the same `sys.stdout.reconfigure(encoding="utf-8")` fix as the orchestrator (box-drawing chars fail on cp1252 terminals).

**Verified working:** `python int/bin/ask_mistral.py "your prompt"` ✅

---

## 2026-05-22 — Mistral Agent (3rd LLM backend)

**Files added:** `int/bin/lib_agents_mistral.py`, `int/bin/ask_mistral.py`
**Files changed:** `int/bin/signal_mesh_orchestrator.py`, `.env`

### What changed

**`lib_agents_mistral.py`**
- `MistralAgent(BaseAgent)` — calls Mistral AI via the `mistralai` SDK (`pip install mistralai`).
- Default model: `mistral-small-latest` (change `MISTRAL_MODEL` constant to swap models).
- Reads `MISTRAL_API_KEY` from `.env` (same walk-up loader pattern as Gemini).
- Handles rate-limit 429 with countdown retry (same UX as Gemini agent).
- Strips markdown code fences from responses before JSON parsing.
- Get a key at: https://console.mistral.ai/api-keys

**`ask_mistral.py`**
- CLI wrapper identical in shape to `ask_gemini.py`.
- Usage: `python int/bin/ask_mistral.py "Your prompt here"`

**`signal_mesh_orchestrator.py`**
- `--agent` now accepts `claude | gemini | mistral | all`.
- `--agent all` now creates all 3 agents: Claude + Gemini + Mistral (round-robin, cross-pollination between all).
- Prompts are distributed round-robin across whichever agents are active.

**`.env`**
- Added `MISTRAL_API_KEY=` placeholder — paste your key there.

### Setup
```
pip install mistralai
# add to .env:
MISTRAL_API_KEY=your_key_here
```

---

## 2026-05-17 — Bug Fixes (UTF-8 encoding + float confidence_delta)

**File changed:** `int/bin/signal_mesh_orchestrator.py`
**Discovered during:** first end-to-end test run

### What changed

**1. Windows stdout UTF-8 encoding**
- The verbose Claude agent output uses Unicode box-drawing characters (─, ═).
- Windows terminal defaults to cp1252 which can't encode them, causing a crash in `_Tee.write()`.
- Fix: `sys.stdout.reconfigure(encoding="utf-8")` called at the top of `main()`, before `_Tee` captures stdout.

**2. `confidence_delta` float formatting**
- The LLM occasionally returns `confidence_delta` as a float (e.g. `5.0`) instead of an int.
- The format string `{delta:+d}` requires an int, raising `ValueError`.
- Fix: `int(result.get("confidence_delta", 0))` in both `run_cross_pollination_for_ticker` and `print_results`.

**First successful end-to-end run: 2026-05-17**
- Stocks discovered: MU, ANET, APP (EUR · Trade Republic mode)
- Top pick: MU (BUY, score 68.3, 29/53 BUY votes)
- Telegram notification confirmed delivered ✅
- Output saved to `int/bin/outputs/signal_mesh_2026-05-17_122848.txt`

---

## 2026-05-17 — .env Credentials Loading for Telegram

**Files added:** `int/bin/lib_env.py`
**Files changed:** `int/bin/signal_mesh_orchestrator.py`, `int/bin/test_telegram.py`

### What changed

**`lib_env.py` — shared .env loader (no external dependencies)**
- Reads `<project_root>/.env` and injects values into `os.environ`.
- Handles quoted values, whitespace around `=`, and blank/comment lines.
- Skips keys already present in the environment (env vars take precedence).
- Both `signal_mesh_orchestrator.py` and `test_telegram.py` call `load_dotenv()` at startup via this module.
- No need to set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` as system environment variables — just keep them in `.env`.

**How to get your Telegram chat ID**
1. Send any message to your bot in Telegram (e.g. "hi")
2. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser
3. Find `"chat":{"id": 123456789}` in the response
4. Add `TELEGRAM_CHAT_ID=123456789` to `.env`

**Status:** ✅ Verified working — test message successfully received on 2026-05-17.

---

## 2026-05-17 — Telegram Notifications + Error Handling Overhaul

**File changed:** `int/bin/signal_mesh_orchestrator.py`

### What changed

**1. Error handling — SKIP instead of default JSON**
- Previously: when an agent returned an error with no `signal` field, the orchestrator silently substituted `{"signal": "HOLD", "factor_score": 50}`, padding the vote pool with phantom HOLDs.
- Now: failed responses are counted as `SKIP`, printed as such in the terminal, and excluded entirely from the signal vote pool and category score calculations. Only real agent replies influence the final signal.
- Applies to both `run_all_prompts_for_ticker` and `run_bulk_prompts_for_ticker`.

**2. Agent reliability tracking**
- Both run functions now count `proper_replies` and `failed_replies` per agent throughout a run.
- Each per-stock result dict now includes an `agent_reliability` key: `{agent_name: {proper: N, failed: N}}`.

**3. Telegram notifications**
- New function: `send_telegram_notification(results, agents_label, euro)`.
- Called automatically at the end of every `action_fetch_data` run, after `print_results`.
- Reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from environment variables. Prints a skip message if either is unset.
- Uses only stdlib (`urllib.request`, `urllib.parse`) — no new dependencies.
- Message format (HTML parse mode):
  - Header with currency label, UTC timestamp, and active agents
  - Ranked results table: 🟢/🔴/🟡 emoji, ticker, signal, weighted score, B/S/H vote counts, ⚠️Nsk tag if any prompts were skipped for that stock
  - Top pick highlight (only shown when final signal is BUY)
  - Agent Reliability section: per-agent proper/total reply count and percentage, with ✅/⚠️/❌ icon

### Current capabilities of the script

| Feature | Status |
|---|---|
| Step 1: Discover 5 trending stocks via Claude | ✅ |
| Step 2: Fetch yfinance data (price, RSI, MA, fundamentals, …) | ✅ |
| Step 3: Run 25 prompts per stock across 5 categories | ✅ |
| Agent backends: Claude, Gemini, or both (round-robin) | ✅ |
| Bulk mode (`--bulk_prompt`): 1 LLM call per category instead of 25 | ✅ |
| Cross-pollination deliberation round (multi-agent only) | ✅ |
| EUR / Trade Republic mode (`--euro`) | ✅ |
| Output to file (`--output`) with tee to stdout | ✅ |
| Failed agent responses marked SKIP, excluded from vote pool | ✅ |
| Per-agent reliability stats tracked and returned per stock | ✅ |
| Telegram notification with results + reliability stats at run end | ✅ |

### How to enable Telegram
```
set TELEGRAM_BOT_TOKEN=your_bot_token
set TELEGRAM_CHAT_ID=your_chat_id
python int/bin/signal_mesh_orchestrator.py fetch_data
```

---

## 2026-05-17 — Scheduled Task + Telegram Test Script

**Files added:** `run_signal_mesh.bat`, `int/bin/test_telegram.py`
**System change:** Windows Task Scheduler task `SignalMesh_Daily` registered

### What changed

**1. Windows Scheduled Task — `SignalMesh_Daily`**
- Runs every **Monday–Friday at 09:00 AM** local time.
- Executes `run_signal_mesh.bat`, which calls the orchestrator with:
  `fetch_data -v -e --agent all --bulk_prompt --output`
- Settings: starts if missed (StartWhenAvailable), requires network, 3-hour execution limit.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be set as **user environment variables** (not just shell variables) so the task can read them at runtime.
- To remove: `schtasks /delete /tn SignalMesh_Daily /f`

**2. `run_signal_mesh.bat` — launcher wrapper**
- Sets working directory to the project root before running the script.
- Uses absolute paths to the venv Python and the orchestrator.
- Can also be double-clicked manually to trigger a run.

**3. `int/bin/test_telegram.py` — Telegram smoke test**
- Sends a fake but realistically formatted Signal Mesh notification.
- Reads the same env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) as the main script.
- Prints `✅ Test message sent! message_id=...` on success, or a detailed error on failure.
- Usage:
  ```
  set TELEGRAM_BOT_TOKEN=your_token
  set TELEGRAM_CHAT_ID=your_chat_id
  python int/bin/test_telegram.py
  ```

### Current capabilities of the script

| Feature | Status |
|---|---|
| Step 1: Discover 5 trending stocks via Claude | ✅ |
| Step 2: Fetch yfinance data (price, RSI, MA, fundamentals, …) | ✅ |
| Step 3: Run 25 prompts per stock across 5 categories | ✅ |
| Agent backends: Claude, Gemini, or both (round-robin) | ✅ |
| Bulk mode (`--bulk_prompt`): 1 LLM call per category instead of 25 | ✅ |
| Cross-pollination deliberation round (multi-agent only) | ✅ |
| EUR / Trade Republic mode (`--euro`) | ✅ |
| Output to file (`--output`) with tee to stdout | ✅ |
| Failed agent responses marked SKIP, excluded from vote pool | ✅ |
| Per-agent reliability stats tracked and returned per stock | ✅ |
| Telegram notification with results + reliability stats at run end | ✅ |
| Automated daily run Mon–Fri 09:00 AM via Windows Task Scheduler | ✅ |
| Telegram smoke-test script (`test_telegram.py`) | ✅ |

---
