"""
lib_market_hours.py
─────────────────────────────────────────────────────────────────────────────
Market-hours gating for the /get monitoring loop.

Determines whether a given ticker's home exchange is currently open, and
computes the next open time so the bot can sleep until then.

Exchange detection is based on ticker suffix:
  .AS  → Amsterdam / Euronext     08:00–16:30 UTC
  .DE  → XETRA Frankfurt          07:00–15:30 UTC
  .PA  → Paris / Euronext         08:00–16:30 UTC
  (no suffix) → US NYSE/NASDAQ    13:30–20:00 UTC

Optionally uses pandas_market_calendars for holiday-aware open/close times.
Falls back gracefully to a simple UTC window + weekday check if not installed
or if the calendar lookup fails.

Public API:
  is_market_open(ticker: str) -> bool
  next_market_open(ticker: str) -> datetime
"""

from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Optional dependency
# ---------------------------------------------------------------------------
try:
    import pandas_market_calendars as mcal
    _MCAL_AVAILABLE = True
except ImportError:
    _MCAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Exchange registry
# ---------------------------------------------------------------------------

# suffix → (utc_open_hour, utc_open_min, utc_close_hour, utc_close_min, mcal_name)
_EXCHANGE_MAP: dict[str, tuple[int, int, int, int, str]] = {
    ".AS": (8,  0,  16, 30, "Euronext"),
    ".DE": (7,  0,  15, 30, "XETRA"),
    ".PA": (8,  0,  16, 30, "Euronext"),
}

_US_HOURS: tuple[int, int, int, int, str] = (13, 30, 20, 0, "NYSE")


def _exchange_for(ticker: str) -> tuple[int, int, int, int, str]:
    """Return the (open_h, open_m, close_h, close_m, mcal_name) tuple for ticker."""
    upper = ticker.upper()
    for suffix, info in _EXCHANGE_MAP.items():
        if upper.endswith(suffix.upper()):
            return info
    return _US_HOURS


# ---------------------------------------------------------------------------
# pandas_market_calendars helpers
# ---------------------------------------------------------------------------

def _mcal_is_open(ticker: str) -> bool | None:
    """Return True/False using pandas_market_calendars, or None on any error."""
    if not _MCAL_AVAILABLE:
        return None
    try:
        _, _, _, _, exchange_name = _exchange_for(ticker)
        cal = mcal.get_calendar(exchange_name)
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        schedule = cal.schedule(start_date=date_str, end_date=date_str)
        if schedule.empty:
            return False
        open_t  = schedule.iloc[0]["market_open"].to_pydatetime()
        close_t = schedule.iloc[0]["market_close"].to_pydatetime()
        return open_t <= now <= close_t
    except Exception:
        return None


def _mcal_next_open(ticker: str) -> datetime | None:
    """Return next open datetime using pandas_market_calendars, or None on error."""
    if not _MCAL_AVAILABLE:
        return None
    try:
        _, _, _, _, exchange_name = _exchange_for(ticker)
        cal = mcal.get_calendar(exchange_name)
        now      = datetime.now(timezone.utc)
        end_date = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        schedule = cal.schedule(
            start_date=now.strftime("%Y-%m-%d"),
            end_date=end_date,
        )
        for _, row in schedule.iterrows():
            open_t = row["market_open"].to_pydatetime()
            if open_t > now:
                return open_t
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# UTC window fallback helpers
# ---------------------------------------------------------------------------

def _window_is_open(ticker: str) -> bool:
    """Simple UTC window + weekday check (no holiday awareness)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    open_h, open_m, close_h, close_m, _ = _exchange_for(ticker)
    open_time  = now.replace(hour=open_h,  minute=open_m,  second=0, microsecond=0)
    close_time = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return open_time <= now <= close_time


def _window_next_open(ticker: str) -> datetime:
    """Return next UTC open datetime based on window hours, skipping weekends."""
    now = datetime.now(timezone.utc)
    open_h, open_m, _, _, _ = _exchange_for(ticker)

    candidate = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    # If today's open hasn't passed yet and today is a weekday, that's the answer
    if candidate > now and now.weekday() < 5:
        return candidate

    # Otherwise scan up to 7 days ahead
    for delta_days in range(1, 8):
        future = now + timedelta(days=delta_days)
        if future.weekday() >= 5:
            continue
        return future.replace(hour=open_h, minute=open_m, second=0, microsecond=0)

    # Fallback: return 24 hours from now (should never reach here)
    return now + timedelta(hours=24)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_market_open(ticker: str) -> bool:
    """Return True if ticker's home exchange is currently open for trading."""
    # Try pandas_market_calendars first
    result = _mcal_is_open(ticker)
    if result is not None:
        return result
    # Fall back to simple UTC window
    return _window_is_open(ticker)


def next_market_open(ticker: str) -> datetime:
    """Return the next UTC datetime when ticker's home exchange opens.

    Scans up to 7 calendar days ahead, skipping weekends.
    """
    # Try pandas_market_calendars first
    result = _mcal_next_open(ticker)
    if result is not None:
        return result
    # Fall back to simple UTC window
    return _window_next_open(ticker)
