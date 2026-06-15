"""
test_ibkr_endpoint.py
─────────────────────────────────────────────────────────────────────────────
Standalone test script for the IbkrClient.

Run:
    python int/bin/test_ibkr_endpoint.py

Requires TWS or IB Gateway running and accepting connections on the
configured host/port (see IBKR_* vars in .env, or defaults: 127.0.0.1:4002).

Sections:
  1. Connection
  2. Account Summary
  3. Current Positions
  4. Price Check (AAPL)
  5. Recent Executions (7 days)
  6. Paper Order Test  (paper mode only)
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_ibkr import IbkrClient, IBKR_AVAILABLE


def _load_dotenv() -> None:
    current = Path(__file__).resolve().parent
    for _ in range(6):
        env_file = current / ".env"
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        val = val.strip().strip('"').strip("'").strip()
                        os.environ.setdefault(key.strip(), val)
            return
        parent = current.parent
        if parent == current:
            break
        current = parent


_load_dotenv()


def _header(n: int, title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  TEST {n}: {title}")
    print(f"{'─' * 60}")


def main() -> None:
    if not IBKR_AVAILABLE:
        print("[ERROR] ib_insync is not installed. Run: pip install ib_insync")
        sys.exit(1)

    client  = IbkrClient()
    passed  = 0
    total   = 6
    results = []

    # ── 1. Connection ──────────────────────────────────────────────────────────
    _header(1, "Connection")
    try:
        ok = client.connect(timeout=15)
        if not ok:
            raise RuntimeError("connect() returned False")
        mode = "PAPER" if client.paper_mode else "LIVE"
        print(f"  host      : {client.host}")
        print(f"  port      : {client.port}")
        print(f"  client_id : {client.client_id}")
        print(f"  mode      : {mode}")
        print(f"  account   : {client.account or '(not configured)'}")
        print("  PASS")
        passed += 1
        results.append(("Connection", "PASS"))
    except Exception as exc:
        print(f"  FAIL — {exc}")
        results.append(("Connection", f"FAIL — {exc}"))
        print("\nCannot continue without a connection.")
        _print_summary(results, passed, total)
        return

    # ── 2. Account Summary ─────────────────────────────────────────────────────
    _header(2, "Account Summary")
    try:
        summary = client.account_summary()
        if not summary:
            raise ValueError("account_summary() returned empty dict")
        for key, value in summary.items():
            print(f"  {key:<22}: {value}")
        print("  PASS")
        passed += 1
        results.append(("Account Summary", "PASS"))
    except Exception as exc:
        print(f"  FAIL — {exc}")
        results.append(("Account Summary", f"FAIL — {exc}"))

    # ── 3. Current Positions ───────────────────────────────────────────────────
    _header(3, "Current Positions")
    try:
        positions = client.get_all_positions()
        if not positions:
            print("  (no open positions)")
        else:
            fmt = "  {:<12} {:>10} {:>12} {:>14}"
            print(fmt.format("TICKER", "QTY", "AVG_COST", "MKT_VALUE"))
            print("  " + "-" * 52)
            for pos in positions:
                print(fmt.format(
                    pos["ticker"],
                    f"{pos['quantity']:.4f}",
                    f"{pos['avg_cost']:.4f}",
                    f"{pos['market_value']:.2f}",
                ))
        print("  PASS")
        passed += 1
        results.append(("Current Positions", "PASS"))
    except Exception as exc:
        print(f"  FAIL — {exc}")
        results.append(("Current Positions", f"FAIL — {exc}"))

    # ── 4. Price Check (AAPL) ──────────────────────────────────────────────────
    _header(4, "Price Check (AAPL)")
    try:
        price = client.last_price("AAPL", wait=4.0)
        if not isinstance(price, float) or price <= 0:
            raise ValueError(f"Expected a positive float, got {price!r}")
        print(f"  AAPL last price: ${price:.2f}")
        print("  PASS")
        passed += 1
        results.append(("Price Check (AAPL)", "PASS"))
    except Exception as exc:
        print(f"  FAIL — {exc}")
        results.append(("Price Check (AAPL)", f"FAIL — {exc}"))

    # ── 5. Recent Executions (7 days) ──────────────────────────────────────────
    _header(5, "Recent Executions (7 days)")
    try:
        executions = client.get_recent_executions(days=7)
        if not executions:
            print("  (no recent trades)")
        else:
            fmt = "  {:<12} {:<6} {:>10} {:>10}  {}"
            print(fmt.format("TICKER", "SIDE", "QTY", "PRICE", "TIMESTAMP"))
            print("  " + "-" * 60)
            for ex in executions:
                print(fmt.format(
                    ex["ticker"],
                    ex["action"],
                    f"{ex['quantity']:.4f}",
                    f"{ex['price']:.4f}",
                    ex["timestamp"][:19],
                ))
        print("  PASS")
        passed += 1
        results.append(("Recent Executions", "PASS"))
    except Exception as exc:
        print(f"  FAIL — {exc}")
        results.append(("Recent Executions", f"FAIL — {exc}"))

    # ── 6. Paper Order Test ────────────────────────────────────────────────────
    _header(6, "Paper Order Test")
    if not client.paper_mode:
        print("  SKIP — live mode detected; skipping test order to avoid real fills.")
        results.append(("Paper Order Test", "SKIP (live mode)"))
    else:
        try:
            from ib_insync import Stock, LimitOrder

            contract = Stock("AAPL", "SMART", "USD")
            client._ib.qualifyContracts(contract)

            order = LimitOrder("BUY", 1, 1.00)
            trade = client._ib.placeOrder(contract, order)
            print(f"  Order placed — order_id: {trade.order.orderId}")

            time.sleep(2)
            status = client.get_order_status(trade.order.orderId)
            print(f"  Status after 2s: {status}")

            valid_statuses = {"Submitted", "PreSubmitted", "PendingSubmit", "PendingCancel"}
            if status not in valid_statuses:
                raise ValueError(
                    f"Expected a submitted status, got {status!r}. "
                    "Is IB Gateway accepting orders?"
                )

            client._ib.cancelOrder(trade.order)
            time.sleep(1)
            cancelled_status = client.get_order_status(trade.order.orderId)
            print(f"  Status after cancel: {cancelled_status}")
            print("  PASS")
            passed += 1
            results.append(("Paper Order Test", "PASS"))
        except Exception as exc:
            print(f"  FAIL — {exc}")
            results.append(("Paper Order Test", f"FAIL — {exc}"))

    # ── Summary ────────────────────────────────────────────────────────────────
    _print_summary(results, passed, total)
    client.disconnect()


def _print_summary(results: list, passed: int, total: int) -> None:
    print(f"\n{'═' * 60}")
    print(f"  RESULTS: {passed}/{total} tests passed")
    print(f"{'═' * 60}")
    for name, outcome in results:
        icon = "PASS" if outcome == "PASS" else ("SKIP" if "SKIP" in outcome else "FAIL")
        prefix = {
            "PASS": "[PASS]",
            "SKIP": "[SKIP]",
            "FAIL": "[FAIL]",
        }[icon]
        print(f"  {prefix}  {name}")
        if icon == "FAIL":
            detail = outcome.replace("FAIL — ", "", 1)
            print(f"          {detail}")
    print()


if __name__ == "__main__":
    main()
