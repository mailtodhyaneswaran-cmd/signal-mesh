# Signal Mesh — Change History

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
