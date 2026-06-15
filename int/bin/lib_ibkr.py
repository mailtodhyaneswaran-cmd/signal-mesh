"""
lib_ibkr.py
─────────────────────────────────────────────────────────────────────────────
Interactive Brokers client via ib_insync.

Connects to a locally-running TWS or IB Gateway over TCP.
No API keys — authentication is handled by the IB application itself.

Configuration (read from .env):
  IBKR_HOST        default 127.0.0.1
  IBKR_PORT        default 4002  (IB Gateway paper)
  IBKR_CLIENT_ID   default 1
  IBKR_PAPER       default true
  IBKR_ACCOUNT     optional — account ID for account updates

Public API:
  IbkrClient(host, port, client_id, paper_mode)
  get_client() -> IbkrClient   (module-level singleton)
  IBKR_AVAILABLE: bool
"""

import math
import os
import threading
import time
from pathlib import Path


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

try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder, ExecutionFilter
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False


# Exchange suffix → (ibkr_exchange, currency)
_EXCHANGE_MAP: dict[str, tuple[str, str]] = {
    ".AS": ("AEB",  "EUR"),
    ".DE": ("IBIS", "EUR"),
    ".PA": ("SBF",  "EUR"),
}


def _ibkr_contract_params(ticker: str) -> tuple[str, str, str]:
    """Return (base_symbol, exchange, currency) for a ticker string."""
    upper = ticker.upper()
    for suffix, (exchange, currency) in _EXCHANGE_MAP.items():
        if upper.endswith(suffix.upper()):
            base = upper[: -len(suffix)]
            return base, exchange, currency
    return upper, "SMART", "USD"


class IbkrClient:
    """Thread-safe wrapper around ib_insync.IB."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        paper_mode: bool | None = None,
    ) -> None:
        if not IBKR_AVAILABLE:
            raise ImportError(
                "ib_insync is not installed. Run: pip install ib_insync"
            )

        self.host      = host      or os.environ.get("IBKR_HOST",      "127.0.0.1")
        self.port      = port      or int(os.environ.get("IBKR_PORT",  "4002"))
        self.client_id = client_id or int(os.environ.get("IBKR_CLIENT_ID", "1"))
        self.account   = os.environ.get("IBKR_ACCOUNT", "").strip()

        if paper_mode is not None:
            self.paper_mode = paper_mode
        else:
            raw = os.environ.get("IBKR_PAPER", "true").strip().lower()
            self.paper_mode = raw not in ("false", "0", "no")

        self._ib         = IB()
        self._order_lock = threading.Lock()

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self, timeout: float = 15.0) -> bool:
        """Connect to TWS/Gateway. Returns True on success."""
        try:
            self._ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                timeout=timeout,
                readonly=False,
            )
        except Exception as exc:
            print(f"[IBKR] Connection failed: {exc}")
            return False

        if self.account:
            try:
                self._ib.reqAccountUpdates(True, self.account)
            except Exception:
                pass

        mode_label = "PAPER" if self.paper_mode else "LIVE"
        print(f"[IBKR] Connected  host={self.host}  port={self.port}  "
              f"clientId={self.client_id}  mode={mode_label}")
        if self.account:
            print(f"[IBKR] Account: {self.account}")
        return True

    def disconnect(self) -> None:
        try:
            self._ib.disconnect()
            print("[IBKR] Disconnected.")
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    # ── Account ────────────────────────────────────────────────────────────────

    def account_summary(self) -> dict:
        """Return selected account metrics from reqAccountValues."""
        keys_wanted = {
            "TotalCashValue", "NetLiquidation", "AvailableFunds",
            "BuyingPower", "UnrealizedPnL", "RealizedPnL",
        }
        result: dict = {}
        for av in self._ib.accountValues():
            if av.tag in keys_wanted and av.currency in ("USD", "BASE", ""):
                try:
                    result[av.tag] = float(av.value)
                except (ValueError, TypeError):
                    result[av.tag] = av.value
        return result

    def get_cash_balance(self) -> float:
        """Return AvailableFunds, falling back to TotalCashValue."""
        summary = self.account_summary()
        for key in ("AvailableFunds", "TotalCashValue"):
            if key in summary:
                return float(summary[key])
        return 0.0

    # ── Positions ──────────────────────────────────────────────────────────────

    def get_all_positions(self) -> list[dict]:
        """Return all open positions as a list of dicts."""
        positions = []
        for pos in self._ib.positions():
            contract = pos.contract
            positions.append({
                "ticker":       contract.symbol,
                "exchange":     contract.exchange or contract.primaryExch or "",
                "currency":     contract.currency,
                "quantity":     pos.position,
                "avg_cost":     pos.avgCost,
                "market_value": pos.position * pos.avgCost,
            })
        return positions

    def get_position(self, ticker: str) -> dict | None:
        """Return the position dict for a specific ticker, or None."""
        base, _, _ = _ibkr_contract_params(ticker)
        for pos in self.get_all_positions():
            if pos["ticker"].upper() == base.upper():
                return pos
        return None

    # ── Market data ────────────────────────────────────────────────────────────

    def last_price(self, ticker: str, wait: float = 3.0) -> float:
        """Request a snapshot price for ticker. Raises ValueError if unavailable."""
        base, exchange, currency = _ibkr_contract_params(ticker)
        contract = Stock(base, exchange, currency)
        self._ib.qualifyContracts(contract)

        ticker_obj = self._ib.reqMktData(contract, "", False, False)
        time.sleep(wait)
        self._ib.cancelMktData(contract)

        price = ticker_obj.last
        if price is None or (isinstance(price, float) and math.isnan(price)):
            price = ticker_obj.close
        if price is None or (isinstance(price, float) and math.isnan(price)):
            raise ValueError(f"No price available for {ticker}")
        return float(price)

    # ── Order placement ────────────────────────────────────────────────────────

    def buy_dollars(self, ticker: str, dollar_amount: float, wait: float = 10.0) -> dict:
        """
        Place a market buy for approximately dollar_amount USD of ticker.

        US stocks on SMART support fractional shares via cashQty.
        EU stocks require whole-share calculation using last_price first.
        """
        if self.paper_mode:
            print(f"[IBKR] WARNING: PAPER MODE — placing buy order for ${dollar_amount:.2f} of {ticker}")

        base, exchange, currency = _ibkr_contract_params(ticker)
        contract = Stock(base, exchange, currency)
        self._ib.qualifyContracts(contract)

        with self._order_lock:
            if exchange == "SMART" and currency == "USD":
                order = MarketOrder("BUY", 0)
                order.cashQty = dollar_amount
            else:
                price    = self.last_price(ticker)
                quantity = math.floor(dollar_amount / price)
                if quantity < 1:
                    raise ValueError(
                        f"dollar_amount ${dollar_amount:.2f} is less than one share "
                        f"of {ticker} at {price:.2f}"
                    )
                order = MarketOrder("BUY", quantity)

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(wait)

        fill_price = 0.0
        filled_qty = order.totalQuantity
        status     = trade.orderStatus.status

        if trade.fills:
            total_cost  = sum(f.execution.price * f.execution.shares for f in trade.fills)
            total_shares = sum(f.execution.shares for f in trade.fills)
            fill_price  = total_cost / total_shares if total_shares else 0.0
            filled_qty  = total_shares

        return {
            "ticker":        ticker,
            "action":        "BUY",
            "order_id":      trade.order.orderId,
            "quantity":      filled_qty,
            "fill_price":    fill_price,
            "dollar_amount": dollar_amount,
            "status":        status,
        }

    def sell_position(self, ticker: str, wait: float = 10.0) -> dict:
        """
        Sell the entire position for ticker.
        Raises ValueError if no position exists.
        """
        if self.paper_mode:
            print(f"[IBKR] WARNING: PAPER MODE — placing sell order for {ticker}")

        pos = self.get_position(ticker)
        if pos is None or pos["quantity"] == 0:
            raise ValueError(f"No open position for {ticker}")

        base, exchange, currency = _ibkr_contract_params(ticker)
        contract = Stock(base, exchange, currency)
        self._ib.qualifyContracts(contract)

        quantity = abs(pos["quantity"])

        with self._order_lock:
            order = MarketOrder("SELL", quantity)
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(wait)

        fill_price = 0.0
        status     = trade.orderStatus.status

        if trade.fills:
            total_proceeds = sum(f.execution.price * f.execution.shares for f in trade.fills)
            total_shares   = sum(f.execution.shares for f in trade.fills)
            fill_price     = total_proceeds / total_shares if total_shares else 0.0

        avg_cost = pos["avg_cost"]
        pnl      = (fill_price - avg_cost) * quantity if fill_price else 0.0

        return {
            "ticker":    ticker,
            "action":    "SELL",
            "order_id":  trade.order.orderId,
            "quantity":  quantity,
            "fill_price": fill_price,
            "status":    status,
            "avg_cost":  avg_cost,
            "pnl":       pnl,
        }

    # ── Order status & history ─────────────────────────────────────────────────

    def get_order_status(self, order_id: int) -> str:
        """Return the status string for order_id, or 'Unknown' if not found."""
        for trade in self._ib.trades():
            if trade.order.orderId == order_id:
                return trade.orderStatus.status
        return "Unknown"

    def get_recent_executions(self, days: int = 7) -> list[dict]:
        """
        Return filled executions from the past N days, newest first.
        Uses ib.reqExecutions with an empty filter to fetch all recent fills.
        """
        from datetime import datetime, timezone, timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        fills  = self._ib.reqExecutions(ExecutionFilter())
        result = []

        for fill in fills:
            exec_obj = fill.execution
            try:
                ts = datetime.strptime(exec_obj.time, "%Y%m%d  %H:%M:%S")
                ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                ts = datetime.now(timezone.utc)

            if ts < cutoff:
                continue

            result.append({
                "ticker":    fill.contract.symbol,
                "action":    exec_obj.side.upper(),
                "quantity":  exec_obj.shares,
                "price":     exec_obj.price,
                "timestamp": ts.isoformat(),
                "order_id":  exec_obj.orderId,
            })

        result.sort(key=lambda x: x["timestamp"], reverse=True)
        return result


# ── Module-level singleton ─────────────────────────────────────────────────────

_client: "IbkrClient | None" = None
_client_lock = threading.Lock()


def get_client() -> "IbkrClient":
    """Return the shared IbkrClient instance, creating it on first call."""
    global _client
    with _client_lock:
        if _client is None:
            _client = IbkrClient()
    return _client
