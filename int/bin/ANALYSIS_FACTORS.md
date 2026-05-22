# Signal Mesh — Analysis Factors Reference

25 prompts across 5 categories. Each prompt returns a JSON signal (BUY / SELL / HOLD) and a score (0–100).

**Category weights in final score:**

| Category | Weight |
|---|---|
| Fundamental | 25% |
| Technical | 20% |
| Sentiment | 20% |
| Macro | 20% |
| Quant | 15% |

---

## Category 1 — Technical Analysis (20%)
*"What is the price doing right now?"*

| Prompt | What it measures |
|---|---|
| **T1 Signal Confluence** | Are all indicators (MA, RSI, Bollinger, Momentum) agreeing or disagreeing? More agreement = stronger conviction to act |
| **T2 Support & Resistance** | Where are the price floors (support) and ceilings (resistance)? Is the stock closer to a buy zone or a sell zone? |
| **T3 Momentum Quality** | Is price movement backed by rising volume and RSI? Strong momentum needs both — price rising on falling volume is a red flag |
| **T4 Volatility Assessment** | Is the stock in a "squeeze" (tight Bollinger Bands) about to break out, or already volatile and risky to enter? Also calculates stop-loss/take-profit levels |
| **T5 Trend Strength** | Is price above its 10, 50, and 200-day moving averages? All 3 above = strong uptrend. All 3 below = strong downtrend |

---

## Category 2 — Fundamental Analysis (25% — highest)
*"What is the business actually worth?"*

| Prompt | What it measures |
|---|---|
| **F1 Valuation Check** | Is the stock cheap or expensive? Checks P/E, PEG, P/Book, P/FCF, EV/EBITDA. PEG < 1 = undervalued for its growth rate |
| **F2 Earnings Quality** | Are the profits real? Compares reported profit vs free cash flow. A large gap means the company may be using accounting tricks |
| **F3 Financial Health** | Can the company survive? Checks debt load, liquidity (current ratio), interest coverage, ROE, ROA. High debt + low interest coverage = danger |
| **F4 Growth Trajectory** | Is the business growing faster or slower over time? Accelerating growth + earnings beats = strong buy signal |
| **F5 Competitive Moat** | Does the company have a durable advantage? Higher margins than peers + pricing power = wide moat (e.g. network effect, brand) |

---

## Category 3 — Sentiment Analysis (20%)
*"What does the world think about this stock?"*

| Prompt | What it measures |
|---|---|
| **S1 News Sentiment** | Scans recent headlines for tone. One major bad headline (fraud, CEO leaving) can override many positives |
| **S2 Analyst Ratings** | Tracks professional sell-side upgrades/downgrades and the gap between current price and analyst price target |
| **S3 Social Sentiment** | What Reddit/Twitter/StockTwits is saying. Very high bullish sentiment = contrarian sell signal (overcrowded trade) |
| **S4 Insider Activity** | Are executives buying or selling their own stock? Multiple insiders buying = they think it's undervalued — rare and very bullish |
| **S5 Short Interest** | High short interest + rising price = short squeeze (BUY). Rising shorts + falling price = bears piling in (SELL) |

---

## Category 4 — Macro Analysis (20%)
*"What is the economy doing to this stock?"*

| Prompt | What it measures |
|---|---|
| **M1 Interest Rate Sensitivity** | Does this stock benefit or suffer from current Fed/ECB rate direction? High-P/E tech suffers when rates rise; banks benefit |
| **M2 Sector Rotation** | Is this sector in favour for the current economic cycle phase? Early recovery = financials; Expansion = tech; Late cycle = healthcare; Contraction = utilities |
| **M3 Earnings Calendar Risk** | Is an earnings announcement coming within the 2–5 day hold window? If yes = high risk, the trade could blow up on results |
| **M4 Currency & Global** | Does a strong/weak USD (or EUR) help or hurt this stock? High VIX = risk-off, growth stocks fall. Low VIX = risk-on, growth stocks rally |
| **M5 Geopolitical Risk** | Are tariffs, regulations, or geopolitical events threatening this company's supply chain or sector? (e.g. AI regulation for big tech, tariffs for China-exposed manufacturers) |

---

## Category 5 — Quantitative / Factor Analysis (15%)
*"What do the hidden statistical patterns say?"*

These are systematic "factor" signals used by quant hedge funds — they rank stocks statistically across the whole market.

| Prompt | What it measures |
|---|---|
| **Q1 Value Factor** | Where does this stock rank in cheapness vs the entire S&P 500 / STOXX 600? Bottom 20% = statistically cheap = positive signal |
| **Q2 Quality Factor** | High ROE + stable margins + low debt + consistent earnings beats = "quality" company. Quality stocks outperform in volatile/risk-off markets |
| **Q3 Price Momentum Factor** | Stocks in the top momentum quintile statistically continue outperforming. Best entry = strong long-term momentum + short-term pullback |
| **Q4 Low Volatility Factor** | Counter-intuitive finding: lower-volatility stocks outperform high-volatility ones on a risk-adjusted basis over time. Low beta = defensive edge |
| **Q5 Earnings Revision Factor** | Stocks with rising analyst EPS estimates outperform those with falling estimates. More analysts raising than cutting = positive fundamental momentum |

---

## European / Trade Republic Variants

All 25 prompts have European equivalents (prefix `TR_`) calibrated for:

| Difference | Detail |
|---|---|
| Benchmark | STOXX 600 instead of S&P 500 |
| Interest rates | ECB Deposit Rate + Bund yield instead of Fed Funds + Treasury 10y |
| Accounting | IFRS instead of GAAP (affects earnings quality interpretation) |
| Insider rules | EU MAR (€5,000 threshold, 3-day disclosure) instead of SEC Form 4 |
| Short selling | EU Short Selling Regulation (SSR) — high short interest can trigger restrictions, a bullish catalyst |
| Sector rotation | European cycles lag US by 6–12 months; luxury, autos, chemicals replace US equivalents |
| Macro risks | GDPR fines, Green Deal compliance costs, Russian sanctions exposure, Chinese market access |
| Valuation | European equities structurally trade cheaper than US — P/E and P/B thresholds adjusted accordingly |
