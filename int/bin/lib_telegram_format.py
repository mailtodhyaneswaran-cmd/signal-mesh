"""
lib_telegram_format.py
─────────────────────────────────────────────────────────────────────────────
Formats /get analysis results into Telegram HTML messages.

All LLM-sourced text is passed through html.escape() before inclusion.

Public API:
  format_report(parsed, run_n, total_runs, interval_min) -> list[str]
      Returns 1 or 2 HTML message strings.  Split at the THESIS section
      if the combined length would exceed 4096 chars.

  format_pulse(parsed, run_n, total_runs) -> str
      One-line quiet-mode status string.

  format_summary(session, runs) -> str
      Post-session summary: signal stability, flips, price range, score range.
"""

import html
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}

_CATEGORY_LABELS = {
    "technical":   "Technical",
    "fundamental": "Fundamental",
    "sentiment":   "Sentiment",
    "macro":       "Macro",
    "quant":       "Quant",
}


def _arrow(delta) -> str:
    """Return '↑N', '↓N', or '–' for a numeric delta."""
    if delta is None:
        return "–"
    try:
        n = int(round(float(delta)))
    except (TypeError, ValueError):
        return "–"
    if n > 0:
        return f"↑{n}"
    if n < 0:
        return f"↓{abs(n)}"
    return "–"


def _esc(val) -> str:
    """HTML-escape a value, converting None/missing to empty string."""
    if val is None:
        return ""
    return html.escape(str(val))


def _fmt_price(val) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val)


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

def format_report(
    parsed: dict,
    run_n: int,
    total_runs: int,
    interval_min: int,
) -> list[str]:
    """Build a structured HTML report for one /get run.

    Returns a list of 1 or 2 strings.  If the combined message exceeds
    4096 characters it is split at the THESIS heading.
    """
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    ticker  = _esc(parsed.get("ticker", "?"))
    signal  = str(parsed.get("signal", "HOLD")).upper()
    emoji   = _SIGNAL_EMOJI.get(signal, "⚪")

    factor_score = parsed.get("factor_score", 0) or 0
    confidence   = parsed.get("confidence",   0) or 0

    # Delta fields (present in delta runs, absent in baseline)
    score_delta_bl = parsed.get("score_delta_vs_baseline")
    price_delta_bl = parsed.get("price_delta_vs_baseline_pct")
    sig_changed    = parsed.get("signal_changed_from_previous", False)
    change_reason  = parsed.get("change_reason")

    # ── Part 1: header block ──────────────────────────────────────────────
    lines_head: list[str] = []

    # Signal flip banner
    if sig_changed and change_reason:
        lines_head.append(
            f"🔔 <b>SIGNAL FLIP → {signal}</b> — {_esc(change_reason)}"
        )
        lines_head.append("")

    # Title line
    score_arrow = _arrow(score_delta_bl) if run_n > 1 else ""
    score_str   = f"{factor_score} ({score_arrow})" if score_arrow and score_arrow != "–" else str(factor_score)
    lines_head.append(
        f"📊 <b>{ticker}</b>  ·  Run {run_n}/{total_runs}  ·  {now_str}"
    )
    lines_head.append("──────────────────────────────")
    lines_head.append(
        f"{emoji} <b>{signal}</b>  score {score_str}  conf {confidence}%"
    )

    # Baseline delta line (only on delta runs)
    if run_n > 1 and price_delta_bl is not None and score_delta_bl is not None:
        try:
            pdelta = float(price_delta_bl)
            pdelta_str = f"{'+' if pdelta >= 0 else ''}{pdelta:.1f}%"
        except (TypeError, ValueError):
            pdelta_str = str(price_delta_bl)
        lines_head.append(
            f"Δ baseline: {pdelta_str} price  ·  {_arrow(score_delta_bl)} score"
        )

    # Entry / stop / target line
    entry  = parsed.get("entry")
    stop   = parsed.get("stop_loss")
    target = parsed.get("target")
    rr     = parsed.get("risk_reward")
    horizon = parsed.get("horizon_days")

    if entry is not None or stop is not None or target is not None:
        trade_parts = []
        if entry is not None and target is not None:
            trade_parts.append(f"🎯 Entry ${_fmt_price(entry)} → Tgt ${_fmt_price(target)}")
        elif entry is not None:
            trade_parts.append(f"🎯 Entry ${_fmt_price(entry)}")
        if stop is not None:
            trade_parts.append(f"🛑 ${_fmt_price(stop)}")
        lines_head.append("  ·  ".join(trade_parts))

    if rr is not None or horizon is not None:
        rr_str      = f"R:R {rr}" if rr is not None else ""
        horizon_str = f"Horizon {horizon}d" if horizon is not None else ""
        meta_parts  = [p for p in [rr_str, horizon_str] if p]
        if meta_parts:
            lines_head.append("  ·  ".join(meta_parts))

    # Category breakdown
    scores_dict = parsed.get("scores", {})
    if scores_dict:
        lines_head.append("")
        lines_head.append("CATEGORY BREAKDOWN")
        for key, label in _CATEGORY_LABELS.items():
            cat = scores_dict.get(key, {})
            if not cat:
                continue
            cat_score   = cat.get("score", 0)
            cat_delta   = cat.get("delta")
            cat_verdict = _esc(cat.get("verdict", ""))
            delta_str   = f" ({_arrow(cat_delta)})" if cat_delta is not None else ""
            lines_head.append(
                f"▸ {label:<12} {cat_score}{delta_str}  {cat_verdict}"
            )

    part1 = "\n".join(lines_head)

    # ── Part 2: thesis + catalysts/risks/watch ────────────────────────────
    lines_body: list[str] = []

    thesis = parsed.get("thesis")
    if thesis:
        lines_body.append("")
        lines_body.append("THESIS")
        lines_body.append(_esc(thesis))

    # Catalysts (baseline uses "catalysts", delta uses "new_catalysts")
    catalysts = parsed.get("new_catalysts") or parsed.get("catalysts") or []
    if catalysts:
        lines_body.append("")
        lines_body.append("✓ CATALYSTS")
        for c in catalysts:
            lines_body.append(f"- {_esc(c)}")

    # Risks (baseline uses "risks", delta uses "new_risks")
    risks = parsed.get("new_risks") or parsed.get("risks") or []
    if risks:
        lines_body.append("")
        lines_body.append("⚠ RISKS")
        for r in risks:
            lines_body.append(f"- {_esc(r)}")

    # Watch for
    watch_for = parsed.get("watch_for") or []
    if watch_for:
        lines_body.append("")
        lines_body.append(f"👀 WATCH NEXT {interval_min} MIN")
        for w in watch_for:
            lines_body.append(f"- {_esc(w)}")

    part2 = "\n".join(lines_body)

    # ── Combine, splitting at THESIS if needed ────────────────────────────
    MAX_LEN = 4096

    combined = part1 + part2
    if len(combined) <= MAX_LEN:
        return [combined]

    # Split: part1 in first message, part2 in second
    msg1 = part1
    msg2 = part2.lstrip("\n")
    # Trim each part to the limit just in case
    if len(msg1) > MAX_LEN:
        msg1 = msg1[:MAX_LEN - 3] + "..."
    if len(msg2) > MAX_LEN:
        msg2 = msg2[:MAX_LEN - 3] + "..."
    return [msg1, msg2] if msg2 else [msg1]


# ---------------------------------------------------------------------------
# format_pulse
# ---------------------------------------------------------------------------

def format_pulse(parsed: dict, run_n: int, total_runs: int) -> str:
    """One-line quiet mode pulse message."""
    ticker       = _esc(parsed.get("ticker", "?"))
    signal       = str(parsed.get("signal", "HOLD")).upper()
    emoji        = _SIGNAL_EMOJI.get(signal, "⚪")
    factor_score = parsed.get("factor_score", 0) or 0
    score_delta  = parsed.get("score_delta_vs_baseline")
    sig_changed  = parsed.get("signal_changed_from_previous", False)

    score_str = f"{factor_score} ({_arrow(score_delta)})" if score_delta is not None else str(factor_score)
    change_str = "SIGNAL CHANGED" if sig_changed else "no change"

    return f"Run {run_n}/{total_runs}  ·  {emoji} {signal} {score_str}  ·  {change_str}"


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------

def format_summary(session: dict, runs: list) -> str:
    """Post-session summary message.

    Args:
        session: dict from get_session() — must have ticker, total_runs, agent, started_at.
        runs:    list of dicts each with keys: signal, price, factor_score.
    """
    ticker     = _esc(session.get("ticker", "?"))
    total_runs = session.get("total_runs", len(runs))
    agent      = _esc(session.get("agent", "?"))
    started_at = str(session.get("started_at", ""))[:16]

    if not runs:
        return (
            f"📋 <b>{ticker}</b> — Session Summary\n"
            f"No runs completed."
        )

    signals     = [r.get("signal", "HOLD") for r in runs]
    prices      = [float(r.get("price", 0) or 0) for r in runs]
    scores      = [int(r.get("factor_score", 50) or 50) for r in runs]
    n_completed = len(runs)

    # Signal stability
    last_signal = signals[-1] if signals else "HOLD"
    signal_counts: dict[str, int] = {}
    for s in signals:
        signal_counts[s] = signal_counts.get(s, 0) + 1
    dominant_signal = max(signal_counts, key=signal_counts.__getitem__)
    stability_pct   = round(signal_counts.get(dominant_signal, 0) / n_completed * 100)

    # Flip count: number of times signal changed vs previous
    flip_count = sum(
        1 for i in range(1, len(signals)) if signals[i] != signals[i - 1]
    )

    price_min = min(prices) if prices else 0
    price_max = max(prices) if prices else 0
    score_min = min(scores) if scores else 0
    score_max = max(scores) if scores else 0

    last_emoji = _SIGNAL_EMOJI.get(last_signal, "⚪")

    lines = [
        f"📋 <b>{ticker}</b> — Session Summary",
        f"Agent: [{agent}]  ·  Started: {started_at} UTC",
        f"Runs completed: {n_completed}/{total_runs}",
        "",
        f"Last signal:      {last_emoji} <b>{last_signal}</b>",
        f"Signal stability: {stability_pct}% ({dominant_signal} dominant)",
        f"Signal flips:     {flip_count}",
        f"Price range:      ${price_min:.2f} – ${price_max:.2f}",
        f"Score range:      {score_min} – {score_max}",
    ]

    return "\n".join(lines)
