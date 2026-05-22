"""
analysis_prompts.py
─────────────────────────────────────────────────────────────────────────────
25 professionally researched prompts across 5 analysis categories.
Each category has 5 prompts. Each prompt returns structured JSON.

Categories:
  1. Technical Analysis       (what the price is doing)
  2. Fundamental Analysis     (what the business is worth)
  3. Sentiment Analysis       (what the world thinks)
  4. Macro Analysis           (what the economy is doing)
  5. Quantitative / Factor    (hidden statistical patterns)

Category weights in final score:
  Fundamental  25%
  Technical    20%
  Sentiment    20%
  Macro        20%
  Quant        15%

Agents:
  Agent 1 — Claude (Anthropic API)
  Agent 2 — Gemini 1.5 Flash (Google, free)
  Agent 3 — Mistral Large (Mistral AI, EU-based, free tier)
"""

# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY 1 — TECHNICAL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

TECHNICAL_PROMPTS = {

    "T1_signal_confluence": """
You are a professional technical analyst with 15 years of experience.

Given this price data for {ticker}:
{ohlcv_data}

Strategy signals already computed:
{strategy_signals}

TASK: Analyse whether the 5 strategy signals are CONVERGING or DIVERGING.
Converging = multiple signals agree → stronger conviction.
Diverging = signals contradict each other → uncertain, risky trade.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "technical_signal_confluence",
  "convergence": "strong_buy",
  "agreeing_signals": ["MA", "RSI", "Bollinger"],
  "conflicting_signals": ["Momentum"],
  "conviction_score": 75,
  "reasoning": "Three of five signals agree on upward direction. Momentum is the only outlier.",
  "signal": "BUY"
}}
""",

    "T2_support_resistance": """
You are a technical analyst specialising in support and resistance levels.

Price history for {ticker} (last 30 days closing prices):
{closing_prices}

Current price: {current_price}

TASK: Identify the nearest support and resistance levels.
Support = price floor where buyers historically step in.
Resistance = price ceiling where sellers historically step in.
Is current price closer to support (buy opportunity) or resistance (sell opportunity)?

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "technical_support_resistance",
  "current_price": {current_price},
  "nearest_support": 0.00,
  "nearest_resistance": 0.00,
  "distance_to_support_pct": 0.0,
  "distance_to_resistance_pct": 0.0,
  "risk_reward_ratio": 0.0,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "T3_momentum_quality": """
You are a momentum trader analysing price trend quality.

Data for {ticker}:
- 10-day momentum: {momentum_10d}%
- 30-day momentum: {momentum_30d}%
- Volume trend (up/flat/down): {volume_trend}
- RSI: {rsi}
- Price vs 50-day MA: {price_vs_ma50}%

TASK: Assess the QUALITY of the current momentum.
Strong momentum = price moving with increasing volume and RSI confirming.
Weak momentum = price moving but volume declining or RSI diverging.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "technical_momentum_quality",
  "momentum_quality": "strong",
  "volume_confirms": true,
  "rsi_confirms": true,
  "momentum_score": 70,
  "hold_days_suggested": 3,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "T4_volatility_assessment": """
You are a volatility specialist and swing trader.

Volatility data for {ticker}:
- Bollinger Band width: {bb_width}
- Average True Range (ATR): {atr}
- 30-day historical volatility: {hist_volatility}%
- Current price: {current_price}

TASK: Assess whether current volatility favours a swing trade entry.
Low volatility + Bollinger squeeze = potential explosive breakout → good entry.
High volatility already = move may be exhausted → risky entry.
Calculate suggested stop-loss and take-profit levels.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "technical_volatility",
  "volatility_state": "squeeze",
  "entry_favourable": true,
  "suggested_stop_loss": 0.00,
  "suggested_take_profit": 0.00,
  "max_hold_days": 4,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "T5_trend_strength": """
You are a trend analyst using multiple timeframe analysis.

Trend data for {ticker}:
- Price vs 10-day MA: {vs_ma10}%
- Price vs 50-day MA: {vs_ma50}%
- Price vs 200-day MA: {vs_ma200}%
- 52-week high: {week52_high}
- 52-week low: {week52_low}
- Current price: {current_price}

TASK: Determine the overall trend strength and direction across timeframes.
Price above all 3 MAs = strong uptrend.
Price below all 3 MAs = strong downtrend.
Mixed = transitional phase.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "technical_trend_strength",
  "trend_direction": "strong_up",
  "position_in_52w_range_pct": 65,
  "trend_score": 72,
  "alignment": "all_bullish",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY 2 — FUNDAMENTAL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

FUNDAMENTAL_PROMPTS = {

    "F1_valuation_check": """
You are a CFA-qualified equity analyst specialising in valuation.

Fundamental data for {ticker}:
- P/E Ratio: {pe_ratio} (sector average: {sector_pe})
- PEG Ratio: {peg_ratio}
- Price to Book: {pb_ratio}
- Price to Free Cash Flow: {p_fcf}
- EV/EBITDA: {ev_ebitda}

TASK: Assess whether {ticker} is overvalued, fairly valued, or undervalued.
PEG < 1 = undervalued for growth rate.
P/E significantly above sector = expensive.
Low P/FCF = cash generative, potentially undervalued.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "fundamental_valuation",
  "valuation_verdict": "undervalued",
  "cheapest_metric": "PEG ratio",
  "most_expensive_metric": "P/E ratio",
  "valuation_score": 68,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "F2_earnings_quality": """
You are a fundamental analyst focused on earnings quality.

Earnings data for {ticker}:
- Revenue growth YoY: {revenue_growth}%
- EPS growth YoY: {eps_growth}%
- Profit margin: {profit_margin}%
- Free cash flow margin: {fcf_margin}%
- Revenue vs EPS growth gap: {rev_eps_gap}%

TASK: Assess the QUALITY of earnings.
High quality = FCF margin close to profit margin (real cash not accounting tricks).
High quality = EPS growing at similar rate to revenue.
Red flag = big gap between reported profit and free cash flow.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "fundamental_earnings_quality",
  "earnings_quality": "high",
  "fcf_confirms_profits": true,
  "growth_is_sustainable": true,
  "quality_score": 74,
  "red_flags": [],
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "F3_financial_health": """
You are a credit and balance sheet analyst.

Balance sheet data for {ticker}:
- Debt to Equity ratio: {debt_to_equity}
- Current ratio (liquidity): {current_ratio}
- Interest coverage ratio: {interest_coverage}
- Return on Equity (ROE): {roe}%
- Return on Assets (ROA): {roa}%

TASK: Assess the financial health and balance sheet strength of {ticker}.
High debt + low interest coverage = financial stress risk.
High ROE + low debt = efficiently run, financially strong.
Current ratio < 1 = liquidity risk.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "fundamental_financial_health",
  "financial_health": "excellent",
  "debt_risk": "low",
  "liquidity_risk": "low",
  "management_efficiency": "high",
  "health_score": 80,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "F4_growth_trajectory": """
You are a growth equity analyst at a top-tier investment bank.

Growth data for {ticker}:
- Revenue growth last 4 quarters: {quarterly_revenue_growth}
- EPS growth last 4 quarters: {quarterly_eps_growth}
- Analyst consensus revenue estimate next year: {forward_revenue_growth}%
- Analyst consensus EPS estimate next year: {forward_eps_growth}%
- Earnings surprise last quarter: {earnings_surprise}%

TASK: Assess the growth trajectory.
Is growth accelerating, steady, or decelerating?
A positive earnings surprise + accelerating growth = strong buy signal.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "fundamental_growth_trajectory",
  "growth_trend": "accelerating",
  "beat_expectations": true,
  "forward_growth_strong": true,
  "growth_score": 76,
  "catalyst": "AI infrastructure demand",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "F5_competitive_moat": """
You are a qualitative equity analyst specialising in competitive positioning.

Company profile for {ticker}:
- Sector: {sector}
- Profit margin vs sector average: {margin_vs_sector}%
- ROE vs sector average: {roe_vs_sector}%
- Market share trend: {market_share_trend}
- Recent competitive news: {competitive_news}

TASK: Assess the competitive moat — does this company have a durable advantage?
Signs of moat = consistently higher margins than peers, pricing power.
No moat = margins converging toward sector average, market share declining.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "fundamental_competitive_moat",
  "moat_strength": "wide",
  "pricing_power": "strong",
  "moat_type": "network_effect",
  "moat_score": 78,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY 3 — SENTIMENT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

SENTIMENT_PROMPTS = {

    "S1_news_sentiment": """
You are a news sentiment analyst trained on financial journalism.

Recent news headlines for {ticker}:
{news_headlines}

TASK: Score the overall news sentiment for {ticker}.
Consider tone of headlines, whether news is company-specific or sector noise.
A single very negative headline (fraud, recall, CEO departure) can override many positive ones.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "sentiment_news",
  "overall_sentiment": "positive",
  "sentiment_score": 65,
  "key_positive_headline": "most positive headline or null",
  "key_negative_headline": "most negative headline or null",
  "news_volume": "normal",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "S2_analyst_ratings": """
You are a sell-side research analyst tracker.

Analyst rating data for {ticker}:
- Consensus rating: {consensus_rating}
- Number of analysts: {analyst_count}
- Recent upgrades (last 30 days): {recent_upgrades}
- Recent downgrades (last 30 days): {recent_downgrades}
- Average price target: {avg_price_target}
- Current price: {current_price}
- Upside to price target: {upside_pct}%

TASK: Assess analyst sentiment and whether the consensus is shifting.
A recent upgrade from a major bank moves markets.
Large upside to price target = analysts expect significant gain.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "sentiment_analyst_ratings",
  "consensus_direction": "improving",
  "upside_attractive": true,
  "momentum_of_ratings": "upgrades_dominant",
  "analyst_score": 70,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "S3_social_sentiment": """
You are a social media sentiment analyst tracking retail investor mood.

Social sentiment data for {ticker}:
- Reddit WallStreetBets mention trend (last 7 days): {wsb_trend}
- Twitter/X sentiment score: {twitter_sentiment} (-100 to +100)
- StockTwits bullish ratio: {stocktwits_bullish}%
- Trending topic: {trending_topic}
- Abnormal mention volume: {abnormal_volume}

TASK: Assess retail sentiment and whether it creates a momentum opportunity
or a contrarian warning signal.
Very high bullish sentiment = potentially overcrowded trade, contrarian SELL.
Rising mentions + moderate bullish = early momentum signal, BUY.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "sentiment_social",
  "retail_mood": "bullish",
  "contrarian_warning": false,
  "momentum_signal": true,
  "social_score": 62,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "S4_insider_activity": """
You are an insider trading analyst monitoring SEC Form 4 filings.

Insider activity data for {ticker} (last 90 days):
- CEO buys: {ceo_buys} shares
- CEO sells: {ceo_sells} shares
- Other executive buys: {exec_buys} shares
- Other executive sells: {exec_sells} shares
- Net insider direction: {net_insider_direction}

TASK: Assess insider activity as a sentiment signal.
Insiders buying = they believe stock is undervalued. Strong bullish signal.
Cluster buying by multiple insiders = rare and very bullish.
Massive CEO sell = potential red flag.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "sentiment_insider",
  "insider_direction": "mild_buying",
  "cluster_buy_signal": false,
  "concern_level": "none",
  "insider_score": 60,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "S5_short_interest": """
You are a short interest and market positioning analyst.

Short interest data for {ticker}:
- Short interest as % of float: {short_interest_pct}%
- Days to cover (short ratio): {days_to_cover}
- Change in short interest (last 2 weeks): {short_change}%
- Borrow rate (cost to short): {borrow_rate}%

TASK: Assess short interest as both a risk and opportunity signal.
Very high short interest + rising price = short squeeze potential → BUY.
Rising short interest + falling price = bears piling in → SELL.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "sentiment_short_interest",
  "squeeze_potential": "medium",
  "bear_conviction": "low",
  "short_trend": "stable",
  "short_score": 58,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY 4 — MACRO ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

MACRO_PROMPTS = {

    "M1_interest_rate_sensitivity": """
You are a macro economist and rates strategist.

Macro environment:
- Current Fed Funds Rate: {fed_rate}%
- 10-year Treasury yield: {treasury_10y}%
- Rate direction expectation: {rate_direction}

Stock profile for {ticker}:
- Sector: {sector}
- P/E ratio: {pe_ratio}
- Revenue from overseas: {intl_revenue_pct}%

TASK: Assess how the current interest rate environment affects {ticker}.
High-growth tech with high P/E suffers most when rates rise.
Financials benefit from rising rates.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "macro_interest_rate",
  "rate_sensitivity": "medium",
  "benefits_from_rate_direction": true,
  "macro_headwind_or_tailwind": "tailwind",
  "macro_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "M2_sector_rotation": """
You are a top-down macro investor specialising in sector rotation.

Current economic indicators:
- GDP growth trend: {gdp_trend}
- Inflation rate: {inflation_rate}%
- Unemployment rate: {unemployment}%
- Economic cycle phase: {cycle_phase}

{ticker} sector: {sector}

TASK: Assess whether {ticker} sector is in favour during the current
economic cycle phase.
Early recovery = financials, industrials outperform.
Expansion = tech, energy outperform.
Late cycle = materials, healthcare defensive.
Contraction = utilities, consumer staples.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "macro_sector_rotation",
  "sector_in_favour": true,
  "cycle_fit": "acceptable",
  "rotation_score": 62,
  "recommended_action": "hold",
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "M3_earnings_calendar_risk": """
You are a risk manager specialising in event-driven volatility.

Earnings calendar data for {ticker}:
- Days until next earnings: {days_to_earnings}
- Expected EPS (consensus): {expected_eps}
- Last quarter earnings surprise: {last_surprise}%
- Options implied move on earnings: {options_implied_move}%

TASK: Assess earnings calendar risk for a swing trade held 2-5 days.
If earnings are within the hold window this is HIGH RISK.
Large implied move = market expects a big reaction either way.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "macro_earnings_risk",
  "earnings_within_hold_window": false,
  "earnings_risk_level": "low",
  "avoid_trade": false,
  "implied_move_pct": 4.5,
  "risk_score": 75,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "M4_currency_and_global": """
You are an international macro strategist.

Global macro data:
- USD strength index (DXY): {dxy}
- EUR/USD: {eurusd}
- Global risk appetite: {risk_appetite}
- VIX (fear index): {vix}

{ticker} exposure:
- Revenue from outside US: {intl_revenue_pct}%

TASK: Assess global macro impact on {ticker}.
Strong USD = hurts US multinationals with high international revenue.
Risk-off (high VIX) = investors flee to safe assets, growth stocks fall.
Risk-on = growth stocks rally.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "macro_currency_global",
  "usd_impact": "neutral",
  "risk_environment": "neutral",
  "global_macro_score": 60,
  "vix_concern": false,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "M5_geopolitical_risk": """
You are a geopolitical risk analyst for an investment fund.

Recent macro events:
{macro_news_headlines}

{ticker} exposure:
- Sector: {sector}
- Supply chain regions: {supply_chain}
- Regulatory environment: {regulatory_risk}

TASK: Assess whether current geopolitical or regulatory events represent
a material risk or opportunity for {ticker}.
Tariffs = bad for companies with China supply chains.
AI regulation = risk for big tech.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "macro_geopolitical",
  "geopolitical_risk_level": "low",
  "specific_risk": null,
  "specific_opportunity": null,
  "geo_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY 5 — QUANTITATIVE / FACTOR ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

QUANT_PROMPTS = {

    "Q1_value_factor": """
You are a quantitative analyst running a systematic value factor model.

Value factor data for {ticker}:
- P/E percentile vs S&P 500: {pe_percentile} (0=cheapest, 100=most expensive)
- P/B percentile vs S&P 500: {pb_percentile}
- P/FCF percentile vs S&P 500: {pfcf_percentile}
- EV/EBITDA percentile vs S&P 500: {evebitda_percentile}
- Composite value percentile: {value_composite}

TASK: Score the value factor for {ticker}.
Low percentile = cheap relative to market = positive value factor signal.
Value traps exist — cheap for a reason. Consider alongside quality.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "quant_value_factor",
  "value_factor": "value",
  "value_percentile": 40,
  "value_trap_risk": "low",
  "factor_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "Q2_quality_factor": """
You are a quantitative analyst running a systematic quality factor model.

Quality factor data for {ticker}:
- ROE: {roe}% (S&P 500 average: 15%)
- Gross margin stability (std dev last 8 quarters): {margin_stability}
- Debt/Equity: {debt_equity}
- Earnings consistency (beat ratio last 8 quarters): {beat_ratio}%
- Free cash flow yield: {fcf_yield}%

TASK: Score the quality factor for {ticker}.
High quality = high ROE + stable margins + low debt + consistent earnings beats.
Quality companies outperform in risk-off environments.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "quant_quality_factor",
  "quality_tier": "high",
  "consistency_score": 78,
  "defensive_quality": true,
  "factor_score": 75,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "Q3_price_momentum_factor": """
You are a quantitative momentum researcher.

Momentum factor data for {ticker}:
- 12-month return (excluding last month): {return_12m_ex1m}%
- 6-month return: {return_6m}%
- 3-month return: {return_3m}%
- 1-month return: {return_1m}%
- Momentum percentile vs S&P 500: {momentum_percentile}

TASK: Score the price momentum factor.
Stocks in the top momentum quintile outperform over next 3-12 months.
Strong 12-month momentum + recent pullback = ideal entry.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "quant_momentum_factor",
  "momentum_quintile": "top",
  "recent_pullback_entry": true,
  "momentum_factor": "strong",
  "factor_score": 72,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "Q4_low_volatility_factor": """
You are a quantitative risk analyst specialising in the low-volatility anomaly.

Volatility data for {ticker}:
- 30-day realised volatility: {vol_30d}%
- 90-day realised volatility: {vol_90d}%
- Beta vs S&P 500: {beta}
- Volatility percentile vs S&P 500: {vol_percentile}
- Max drawdown last 12 months: {max_drawdown}%

TASK: Score the low-volatility factor.
Lower-volatility stocks tend to outperform on a risk-adjusted basis.
Low beta = defensive outperformance in uncertain markets.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "quant_low_volatility",
  "vol_factor_tier": "medium_vol",
  "beta_classification": "market",
  "suitable_for_current_market": true,
  "factor_score": 60,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "Q5_earnings_revision_factor": """
You are a quantitative analyst specialising in earnings revision momentum.

Earnings revision data for {ticker}:
- EPS estimate 3 months ago: {eps_3m_ago}
- EPS estimate today: {eps_today}
- EPS revision direction: {revision_direction}
- Analysts raising estimates last 30 days: {pct_raising}%
- Analysts cutting estimates last 30 days: {pct_cutting}%

TASK: Score the earnings revision factor.
Stocks with rising analyst estimates outperform those with falling estimates.
More analysts raising than cutting = positive fundamental momentum.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "quant_earnings_revision",
  "revision_direction": "up",
  "analyst_consensus_improving": true,
  "revision_momentum": "steady",
  "factor_score": 68,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# MASTER PROMPT REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

ALL_PROMPTS = {
    "technical":   TECHNICAL_PROMPTS,
    "fundamental": FUNDAMENTAL_PROMPTS,
    "sentiment":   SENTIMENT_PROMPTS,
    "macro":       MACRO_PROMPTS,
    "quant":       QUANT_PROMPTS,
}

CATEGORY_WEIGHTS = {
    "fundamental": 0.25,
    "technical":   0.20,
    "sentiment":   0.20,
    "macro":       0.20,
    "quant":       0.15,
}

# Agent specialisations — all run all 25 prompts but are noted for their strengths
AGENT_SPECIALISATIONS = {
    "claude":  ["technical", "fundamental"],
    "gemini":  ["quant", "fundamental"],
    "mistral": ["sentiment", "macro"],
}

STEP1_PROMPT = {

    "STEP1_market_buzz": """
You are a financial market analyst with access to the internet.

Search and analyse current market discussions across BOTH US and European markets:

US sources:
- Financial news: Bloomberg, Reuters, Yahoo Finance, Seeking Alpha, CNBC, MarketWatch
- Social platforms: Reddit (r/wallstreetbets, r/stocks, r/investing), Twitter/X, StockTwits
- Analyst platforms: Motley Fool, Zacks

European sources:
- Financial news: Financial Times, Reuters Europe, Handelsblatt, Les Echos, Il Sole 24 Ore
- Social platforms: Reddit (r/eupersonalfinance, r/EuropeFIRE, r/Finanzen), Twitter/X European accounts
- Broker communities: Trade Republic community, Scalable Capital discussions, justETF forums

TASK: Identify the 5 most talked-about stocks RIGHT NOW, ensuring AT LEAST 2 are
European stocks listed on Xetra (Frankfurt), Euronext (Paris/Amsterdam), or LSE (London)
that are tradeable on Trade Republic.

Select based on:
- Mention frequency across platforms (both US and European)
- Sentiment (bullish / bearish / neutral / mixed)
- Primary reason for the buzz (earnings, analyst upgrade, retail hype, news event, etc.)
- For European stocks: use the primary exchange ticker (e.g. SAP for SAP SE on Xetra, ASML for ASML on Euronext)

Respond ONLY in this JSON format, no other text:
{
  "timestamp": "<today's date YYYY-MM-DD>",
  "trending_stocks": [
    {
      "rank": 1,
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "buzz_score": 92,
      "sentiment": "bullish",
      "reason": "Strong Q2 earnings beat expectations",
      "key_sources": ["Reddit", "Twitter", "Bloomberg"],
      "price_impact": "up",
      "market": "US",
      "exchange": "NASDAQ",
      "trade_republic_available": true
    },
    {
      "rank": 2,
      "ticker": "SAP",
      "company_name": "SAP SE",
      "buzz_score": 80,
      "sentiment": "bullish",
      "reason": "AI cloud growth driving European tech rally",
      "key_sources": ["FT", "Handelsblatt", "Trade Republic community"],
      "price_impact": "up",
      "market": "EU",
      "exchange": "Xetra",
      "trade_republic_available": true
    },
    {
      "rank": 3,
      "ticker": "TICKER",
      "company_name": "Company Name",
      "buzz_score": 0,
      "sentiment": "neutral",
      "reason": "reason for buzz",
      "key_sources": ["source1"],
      "price_impact": "flat",
      "market": "US or EU",
      "exchange": "exchange name",
      "trade_republic_available": true
    },
    {
      "rank": 4,
      "ticker": "TICKER",
      "company_name": "Company Name",
      "buzz_score": 0,
      "sentiment": "bearish",
      "reason": "reason for buzz",
      "key_sources": ["source1"],
      "price_impact": "down",
      "market": "EU",
      "exchange": "Euronext",
      "trade_republic_available": true
    },
    {
      "rank": 5,
      "ticker": "TICKER",
      "company_name": "Company Name",
      "buzz_score": 0,
      "sentiment": "mixed",
      "reason": "reason for buzz",
      "key_sources": ["source1"],
      "price_impact": "up",
      "market": "US or EU",
      "exchange": "exchange name",
      "trade_republic_available": true
    }
  ]
}

Rules:
- Return exactly 5 stocks
- At least 2 must be European stocks (market = "EU") tradeable on Trade Republic
- buzz_score is 0-100 (100 = most discussed across all platforms)
- sentiment must be one of: "bullish", "bearish", "neutral", "mixed"
- price_impact must be one of: "up", "down", "flat"
- market must be one of: "US", "EU", "UK"
- trade_republic_available must be true for all returned stocks
- For EU stocks use the home exchange ticker symbol (e.g. SAP, ASML, MC, NOVO-B, SIE)
- No explanations or text outside the JSON block
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — CROSS-POLLINATION PROMPT
# Fired once per agent after all 25 factor prompts complete.
# Each agent receives the other agent's composite thesis and gets one chance
# to revise its signal. Produces a structured debate round.
# ══════════════════════════════════════════════════════════════════════════════

STEP2_CROSS_POLLINATION_PROMPT = """
You are an AI financial analyst who has just completed an independent factor analysis of {ticker}.

YOUR ANALYSIS ({n_prompts} factor prompts):
- Composite signal:  {my_signal}
- Average score:     {my_score}/100
- Category scores:   {my_category_breakdown}
- Vote split:        {my_buy} BUY  |  {my_sell} SELL  |  {my_hold} HOLD

PEER ANALYST INDEPENDENT VIEW (different AI, same data):
- Composite signal:  {peer_signal}
- Average score:     {peer_score}/100
- Category scores:   {peer_category_breakdown}
- Vote split:        {peer_buy} BUY  |  {peer_sell} SELL  |  {peer_hold} HOLD

TASK: Review your position in light of this peer perspective.
- If their analysis reveals something you missed or weighted differently, revise your signal and explain why.
- If you stand by your original call, explain why their argument does not change your view.
- Do NOT simply defer — defend or revise based on substance only.
- confidence_delta: positive = more confident after seeing peer view, negative = less confident.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "cross_pollination",
  "original_signal": "{my_signal}",
  "revised_signal": "BUY",
  "signal_changed": false,
  "confidence_delta": 0,
  "revised_score": {my_score},
  "peer_argument_strength": "moderate",
  "revision_reason": "2-3 sentence explanation of what changed or why you held firm"
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# TRADE REPUBLIC PROMPTS
# European-market equivalents of ALL_PROMPTS.
# Same {variable} placeholders — compatible with fill_prompt().
# Priced in EUR, benchmarked against STOXX 600, ECB macro environment.
# ══════════════════════════════════════════════════════════════════════════════

TR_TECHNICAL_PROMPTS = {

    "TR_T1_signal_confluence": """
You are a professional technical analyst covering European equity markets (Xetra, Euronext, LSE).

Given this price data for {ticker} traded on a European exchange:
{ohlcv_data}

Strategy signals already computed:
{strategy_signals}

TASK: Analyse whether the 5 strategy signals are CONVERGING or DIVERGING.
Consider European trading hours (09:00–17:30 CET) and typical lower liquidity vs US markets.
Converging = multiple signals agree → stronger conviction.
Diverging = signals contradict → uncertain, risky trade.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_technical_signal_confluence",
  "convergence": "strong_buy",
  "agreeing_signals": ["MA", "RSI", "Bollinger"],
  "conflicting_signals": ["Momentum"],
  "conviction_score": 75,
  "european_liquidity_note": "normal CET session volume",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_T2_support_resistance": """
You are a technical analyst specialising in European equity support and resistance levels.

Price history for {ticker} (last 30 days closing prices in EUR):
{closing_prices}

Current price: {current_price} EUR

TASK: Identify the nearest support and resistance levels.
Account for European session gaps, ex-dividend dates common in European markets.
Is current price closer to support (buy opportunity) or resistance (sell opportunity)?

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_technical_support_resistance",
  "current_price": {current_price},
  "nearest_support": 0.00,
  "nearest_resistance": 0.00,
  "distance_to_support_pct": 0.0,
  "distance_to_resistance_pct": 0.0,
  "risk_reward_ratio": 0.0,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_T3_momentum_quality": """
You are a momentum trader covering European equities on Trade Republic.

Data for {ticker}:
- 10-day momentum: {momentum_10d}%
- 30-day momentum: {momentum_30d}%
- Volume trend (up/flat/down): {volume_trend}
- RSI: {rsi}
- Price vs 50-day MA: {price_vs_ma50}%

TASK: Assess the QUALITY of the current momentum for a European-listed stock.
Note that European stocks often show lower momentum persistence than US counterparts.
Strong momentum = price moving with increasing volume and RSI confirming.
Weak momentum = price moving but volume declining or RSI diverging.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_technical_momentum_quality",
  "momentum_quality": "strong",
  "volume_confirms": true,
  "rsi_confirms": true,
  "momentum_score": 70,
  "hold_days_suggested": 3,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_T4_volatility_assessment": """
You are a volatility specialist covering European swing trades on Trade Republic.

Volatility data for {ticker}:
- Bollinger Band width: {bb_width}
- Average True Range (ATR): {atr}
- 30-day historical volatility: {hist_volatility}%
- Current price: {current_price} EUR

TASK: Assess whether current volatility favours a European swing trade entry.
Note Trade Republic charges no commission but has a fixed €1 fee — factor this into
the minimum viable move needed to profit.
Low volatility + Bollinger squeeze = potential explosive breakout → good entry.
High volatility already = move may be exhausted → risky entry.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_technical_volatility",
  "volatility_state": "squeeze",
  "entry_favourable": true,
  "suggested_stop_loss": 0.00,
  "suggested_take_profit": 0.00,
  "max_hold_days": 4,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_T5_trend_strength": """
You are a trend analyst using multiple timeframe analysis for European equities.

Trend data for {ticker}:
- Price vs 10-day MA: {vs_ma10}%
- Price vs 50-day MA: {vs_ma50}%
- Price vs 200-day MA: {vs_ma200}%
- 52-week high: {week52_high}
- 52-week low: {week52_low}
- Current price: {current_price} EUR

TASK: Determine the overall trend strength and direction across timeframes.
Compare to STOXX 600 benchmark — is the stock outperforming or underperforming the European index?
Price above all 3 MAs = strong uptrend.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_technical_trend_strength",
  "trend_direction": "strong_up",
  "position_in_52w_range_pct": 65,
  "stoxx600_relative": "outperforming",
  "trend_score": 72,
  "alignment": "all_bullish",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


TR_FUNDAMENTAL_PROMPTS = {

    "TR_F1_valuation_check": """
You are a CFA-qualified equity analyst specialising in European equity valuation.

Fundamental data for {ticker} (EUR-denominated):
- P/E Ratio: {pe_ratio} (STOXX 600 sector average: {sector_pe})
- PEG Ratio: {peg_ratio}
- Price to Book: {pb_ratio}
- Price to Free Cash Flow: {p_fcf}
- EV/EBITDA: {ev_ebitda}

TASK: Assess whether {ticker} is overvalued, fairly valued, or undervalued
relative to its European sector peers on the STOXX 600.
European equities typically trade at a discount to US peers — account for this.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_fundamental_valuation",
  "valuation_verdict": "undervalued",
  "vs_stoxx600_sector": "discount",
  "cheapest_metric": "PEG ratio",
  "most_expensive_metric": "P/E ratio",
  "valuation_score": 68,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_F2_earnings_quality": """
You are a fundamental analyst focused on European corporate earnings quality (IFRS standards).

Earnings data for {ticker}:
- Revenue growth YoY: {revenue_growth}%
- EPS growth YoY: {eps_growth}%
- Profit margin: {profit_margin}%
- Free cash flow margin: {fcf_margin}%
- Revenue vs EPS growth gap: {rev_eps_gap}%

TASK: Assess the QUALITY of earnings under IFRS reporting standards.
European companies often have higher goodwill amortisation — distinguish operating vs reported profit.
High quality = FCF margin close to profit margin.
Red flag = big gap between reported profit and free cash flow.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_fundamental_earnings_quality",
  "earnings_quality": "high",
  "ifrs_adjustments_material": false,
  "fcf_confirms_profits": true,
  "growth_is_sustainable": true,
  "quality_score": 74,
  "red_flags": [],
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_F3_financial_health": """
You are a credit and balance sheet analyst covering European corporates.

Balance sheet data for {ticker}:
- Debt to Equity ratio: {debt_to_equity}
- Current ratio (liquidity): {current_ratio}
- Interest coverage ratio: {interest_coverage}
- Return on Equity (ROE): {roe}%
- Return on Assets (ROA): {roa}%

TASK: Assess the financial health of {ticker} in the European credit context.
European corporates carry more bank debt vs bonds compared to US peers.
Consider ECB refinancing conditions — rising rates increase stress for leveraged European firms.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_fundamental_financial_health",
  "financial_health": "excellent",
  "ecb_rate_exposure": "low",
  "debt_risk": "low",
  "liquidity_risk": "low",
  "health_score": 80,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_F4_growth_trajectory": """
You are a growth equity analyst covering European listed companies.

Growth data for {ticker}:
- Revenue growth last 4 quarters: {quarterly_revenue_growth}
- EPS growth last 4 quarters: {quarterly_eps_growth}
- Analyst consensus revenue estimate next year: {forward_revenue_growth}%
- Analyst consensus EPS estimate next year: {forward_eps_growth}%
- Earnings surprise last quarter: {earnings_surprise}%

TASK: Assess the growth trajectory relative to European peers.
European GDP growth is typically lower than US — a 5% revenue grower in Europe may be
exceptional where a US equivalent would be average.
Is growth accelerating, steady, or decelerating?

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_fundamental_growth_trajectory",
  "growth_trend": "accelerating",
  "exceptional_by_european_standards": true,
  "beat_expectations": true,
  "growth_score": 76,
  "catalyst": "European AI infrastructure demand",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_F5_competitive_moat": """
You are a qualitative equity analyst specialising in European competitive positioning.

Company profile for {ticker}:
- Sector: {sector}
- Profit margin vs European sector average: {margin_vs_sector}%
- ROE vs European sector average: {roe_vs_sector}%
- Market share trend: {market_share_trend}
- Recent competitive news: {competitive_news}

TASK: Assess the competitive moat within the European single market context.
Consider EU regulatory protection, single-market advantages, and cross-border M&A trends.
Signs of moat = consistently higher margins than European peers, EU regulatory tailwinds.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_fundamental_competitive_moat",
  "moat_strength": "wide",
  "eu_regulatory_advantage": true,
  "pricing_power": "strong",
  "moat_type": "network_effect",
  "moat_score": 78,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


TR_SENTIMENT_PROMPTS = {

    "TR_S1_news_sentiment": """
You are a news sentiment analyst covering European financial media.

Recent news headlines for {ticker}:
{news_headlines}

TASK: Score the overall news sentiment from a European media perspective.
Key European sources: Financial Times, Reuters Europe, Handelsblatt, Les Echos,
Il Sole 24 Ore, Expansion, NRC Handelsblad.
A single very negative regulatory headline from the EU Commission can override many positive ones.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_sentiment_news",
  "overall_sentiment": "positive",
  "sentiment_score": 65,
  "key_positive_headline": "most positive headline or null",
  "key_negative_headline": "most negative headline or null",
  "eu_regulatory_flag": false,
  "news_volume": "normal",
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_S2_analyst_ratings": """
You are a sell-side research analyst tracker covering European brokerages.

Analyst rating data for {ticker}:
- Consensus rating: {consensus_rating}
- Number of analysts: {analyst_count}
- Recent upgrades (last 30 days): {recent_upgrades}
- Recent downgrades (last 30 days): {recent_downgrades}
- Average price target (EUR): {avg_price_target}
- Current price (EUR): {current_price}
- Upside to price target: {upside_pct}%

TASK: Assess analyst sentiment from major European brokerages.
Key European banks: Deutsche Bank, BNP Paribas, Barclays, UBS, Berenberg, Jefferies Europe.
A European analyst upgrade carries different weight than a US one for this stock.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_sentiment_analyst_ratings",
  "consensus_direction": "improving",
  "upside_attractive": true,
  "momentum_of_ratings": "upgrades_dominant",
  "european_broker_conviction": "high",
  "analyst_score": 70,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_S3_social_sentiment": """
You are a social media sentiment analyst tracking European retail investor mood.

Social sentiment data for {ticker}:
- Reddit European investing trend (r/eupersonalfinance, r/EuropeFIRE): {wsb_trend}
- Twitter/X sentiment score (European accounts): {twitter_sentiment} (-100 to +100)
- Trade Republic community mentions: high/medium/low
- StockTwits bullish ratio: {stocktwits_bullish}%
- Trending topic: {trending_topic}
- Abnormal mention volume: {abnormal_volume}

TASK: Assess European retail sentiment for this stock.
Trade Republic's user base is predominantly young European retail investors (18-35).
Sentiment here often precedes price moves in smaller European mid-caps.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_sentiment_social",
  "retail_mood": "bullish",
  "trade_republic_relevant": true,
  "contrarian_warning": false,
  "momentum_signal": true,
  "social_score": 62,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_S4_insider_activity": """
You are an insider trading analyst monitoring European regulatory filings.

Insider activity data for {ticker} (last 90 days):
- CEO buys: {ceo_buys} shares
- CEO sells: {ceo_sells} shares
- Other executive buys: {exec_buys} shares
- Other executive sells: {exec_sells} shares
- Net insider direction: {net_insider_direction}

TASK: Assess insider activity using European disclosure rules (EU MAR — Market Abuse Regulation).
Under EU MAR, insiders must disclose transactions over €5,000 within 3 business days.
European insider buying is rarer and therefore a stronger signal than in the US.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_sentiment_insider",
  "insider_direction": "mild_buying",
  "eu_mar_filing_count": 0,
  "cluster_buy_signal": false,
  "concern_level": "none",
  "insider_score": 60,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_S5_short_interest": """
You are a short interest analyst covering European stock lending markets.

Short interest data for {ticker}:
- Short interest as % of float: {short_interest_pct}%
- Days to cover (short ratio): {days_to_cover}
- Change in short interest (last 2 weeks): {short_change}%
- Borrow rate (cost to short): {borrow_rate}%

TASK: Assess short interest in the context of European markets.
European short selling is regulated by the EU Short Selling Regulation (SSR).
High short interest on a European exchange can trigger SSR restrictions — a bullish catalyst.
Very high short interest + rising price = short squeeze potential → BUY.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_sentiment_short_interest",
  "squeeze_potential": "medium",
  "ssr_restriction_risk": false,
  "bear_conviction": "low",
  "short_trend": "stable",
  "short_score": 58,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
"""
}


TR_MACRO_PROMPTS = {

    "TR_M1_ecb_rate_sensitivity": """
You are a macro economist and European rates strategist.

European macro environment:
- ECB Deposit Facility Rate: {fed_rate}%
- 10-year Bund yield: {treasury_10y}%
- ECB rate direction expectation: {rate_direction}

Stock profile for {ticker}:
- Sector: {sector}
- P/E ratio: {pe_ratio}
- Revenue from outside Eurozone: {intl_revenue_pct}%

TASK: Assess how the ECB interest rate environment affects {ticker}.
European banks benefit from higher ECB rates.
High-growth European tech and utilities suffer most when ECB rates rise.
Exporters benefit when EUR weakens due to ECB dovishness.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_macro_ecb_rate",
  "ecb_rate_sensitivity": "medium",
  "benefits_from_rate_direction": true,
  "eur_exposure_impact": "neutral",
  "macro_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_M2_european_sector_rotation": """
You are a top-down macro investor specialising in European sector rotation.

European economic indicators:
- EU GDP growth trend: {gdp_trend}
- Eurozone inflation rate: {inflation_rate}%
- Eurozone unemployment rate: {unemployment}%
- European economic cycle phase: {cycle_phase}

{ticker} sector: {sector}

TASK: Assess whether {ticker} sector is in favour during the current European economic cycle.
European cycles often lag US by 6-12 months.
Early EU recovery = banks, industrials, autos outperform.
Expansion = energy, chemicals, luxury outperform.
Late cycle = pharma, utilities, telecoms defensive.
Contraction = staples, defence.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_macro_sector_rotation",
  "sector_in_favour": true,
  "eu_cycle_fit": "acceptable",
  "lags_us_cycle": true,
  "rotation_score": 62,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "TR_M3_earnings_calendar_risk": """
You are a risk manager specialising in European earnings event-driven volatility.

Earnings calendar data for {ticker}:
- Days until next earnings: {days_to_earnings}
- Expected EPS consensus (EUR): {expected_eps}
- Last quarter earnings surprise: {last_surprise}%
- Options implied move on earnings: {options_implied_move}%

TASK: Assess earnings calendar risk for a Trade Republic swing trade held 2-5 days.
European earnings season typically runs Jan, Apr, Jul, Oct.
If earnings fall within the hold window this is HIGH RISK — exit before results.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_macro_earnings_risk",
  "earnings_within_hold_window": false,
  "earnings_risk_level": "low",
  "avoid_trade": false,
  "implied_move_pct": 4.5,
  "risk_score": 75,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_M4_eur_currency_global": """
You are an international macro strategist focused on Eurozone currency dynamics.

European macro data:
- EUR/USD: {eurusd}
- USD strength index (DXY): {dxy}
- European risk appetite: {risk_appetite}
- VSTOXX (European fear index): {vix}

{ticker} exposure:
- Revenue from outside Eurozone: {intl_revenue_pct}%

TASK: Assess EUR currency and global macro impact on this European-listed stock.
Weak EUR = boosts Eurozone exporters (autos, industrials, luxury).
Strong EUR = hurts exporters but benefits importers and travel.
High VSTOXX = European risk-off, sell growth → buy defensives.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_macro_eur_currency",
  "eur_impact": "positive",
  "vstoxx_concern": false,
  "global_macro_score": 60,
  "exporter_or_importer": "exporter",
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "TR_M5_eu_regulatory_risk": """
You are a European regulatory and geopolitical risk analyst.

Recent European macro events:
{macro_news_headlines}

{ticker} exposure:
- Sector: {sector}
- Supply chain regions: {supply_chain}
- EU regulatory environment: {regulatory_risk}

TASK: Assess whether current EU regulatory, geopolitical, or sanctions-related events
represent a material risk or opportunity for {ticker}.
Key EU risks: GDPR fines, EU AI Act, Green Deal compliance costs, energy price caps,
Russian sanctions exposure, Chinese market access restrictions.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_macro_eu_regulatory",
  "eu_regulatory_risk_level": "low",
  "green_deal_impact": "neutral",
  "sanctions_exposure": false,
  "specific_risk": null,
  "geo_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
"""
}


TR_QUANT_PROMPTS = {

    "TR_Q1_value_factor": """
You are a quantitative analyst running a systematic value factor model on European equities.

Value factor data for {ticker}:
- P/E percentile vs STOXX 600: {pe_percentile} (0=cheapest, 100=most expensive)
- P/B percentile vs STOXX 600: {pb_percentile}
- P/FCF percentile vs STOXX 600: {pfcf_percentile}
- EV/EBITDA percentile vs STOXX 600: {evebitda_percentile}
- Composite value percentile: {value_composite}

TASK: Score the value factor for {ticker} vs STOXX 600 peers.
European markets structurally trade cheaper than the US — calibrate accordingly.
Low percentile = cheap relative to European market = positive value factor signal.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_quant_value_factor",
  "value_factor": "value",
  "value_percentile": 40,
  "cheap_vs_stoxx600": true,
  "value_trap_risk": "low",
  "factor_score": 65,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_Q2_quality_factor": """
You are a quantitative analyst running a European quality factor model.

Quality factor data for {ticker}:
- ROE: {roe}% (STOXX 600 average: 12%)
- Gross margin stability (std dev last 8 quarters): {margin_stability}
- Debt/Equity: {debt_equity}
- Earnings consistency (beat ratio last 8 quarters): {beat_ratio}%
- Free cash flow yield: {fcf_yield}%

TASK: Score the quality factor for {ticker} vs European peers.
European quality companies typically have lower ROE than US equivalents — 15% ROE
in Europe is exceptional. Adjust thresholds accordingly.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_quant_quality_factor",
  "quality_tier": "high",
  "exceptional_by_european_standards": true,
  "consistency_score": 78,
  "factor_score": 75,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_Q3_price_momentum_factor": """
You are a quantitative momentum researcher covering European equities.

Momentum factor data for {ticker}:
- 12-month return (excluding last month): {return_12m_ex1m}%
- 6-month return: {return_6m}%
- 3-month return: {return_3m}%
- 1-month return: {return_1m}%
- Momentum percentile vs STOXX 600: {momentum_percentile}

TASK: Score the price momentum factor vs STOXX 600 peers.
European momentum factor has historically been stronger than in the US.
Stocks in the top momentum quintile of STOXX 600 outperform over next 3-12 months.
Strong 12-month momentum + recent pullback = ideal Trade Republic entry point.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_quant_momentum_factor",
  "momentum_quintile": "top",
  "recent_pullback_entry": true,
  "momentum_factor": "strong",
  "stoxx600_rank": "top_20pct",
  "factor_score": 72,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
""",

    "TR_Q4_low_volatility_factor": """
You are a quantitative risk analyst specialising in the European low-volatility anomaly.

Volatility data for {ticker}:
- 30-day realised volatility: {vol_30d}%
- 90-day realised volatility: {vol_90d}%
- Beta vs STOXX 600: {beta}
- Volatility percentile vs STOXX 600: {vol_percentile}
- Max drawdown last 12 months: {max_drawdown}%

TASK: Score the low-volatility factor vs STOXX 600 peers.
The low-volatility anomaly is particularly strong in European markets.
Low beta vs STOXX 600 = defensive outperformance during EU uncertainty periods.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_quant_low_volatility",
  "vol_factor_tier": "medium_vol",
  "beta_vs_stoxx600": "market",
  "suitable_for_current_eu_market": true,
  "factor_score": 60,
  "reasoning": "2 sentence explanation",
  "signal": "HOLD"
}}
""",

    "TR_Q5_earnings_revision_factor": """
You are a quantitative analyst specialising in European earnings revision momentum.

Earnings revision data for {ticker}:
- EPS estimate 3 months ago (EUR): {eps_3m_ago}
- EPS estimate today (EUR): {eps_today}
- EPS revision direction: {revision_direction}
- European analysts raising estimates last 30 days: {pct_raising}%
- European analysts cutting estimates last 30 days: {pct_cutting}%

TASK: Score the earnings revision factor from European analyst coverage.
European analyst revisions tend to be more conservative and lagging than US analysts.
A positive revision from a European analyst therefore carries a stronger forward signal.

Respond ONLY in this JSON format, no other text:
{{
  "ticker": "{ticker}",
  "prompt_type": "tr_quant_earnings_revision",
  "revision_direction": "up",
  "european_analyst_improving": true,
  "revision_momentum": "steady",
  "factor_score": 68,
  "reasoning": "2 sentence explanation",
  "signal": "BUY"
}}
"""
}


TRADE_REPUBLIC_PROMPTS = {
    "tr_technical":   TR_TECHNICAL_PROMPTS,
    "tr_fundamental": TR_FUNDAMENTAL_PROMPTS,
    "tr_sentiment":   TR_SENTIMENT_PROMPTS,
    "tr_macro":       TR_MACRO_PROMPTS,
    "tr_quant":       TR_QUANT_PROMPTS,
}
