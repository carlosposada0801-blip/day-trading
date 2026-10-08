# Signal Desk

A private day-trading research dashboard. It blends **news**, **social media**, **corporate
insiders**, **big funds**, **members of Congress** and **price momentum** into one score per
ticker, alerts you when scores move, measures whether the score actually predicts anything,
and has a **paper-trading** account for testing ideas without real money.

> Research tool, not financial advice. No real orders are placed.

## Run it (just for you)

```bash
pip install -r requirements.txt
cp .env.example .env        # then set APP_PASSWORD at minimum
python -m app               # http://127.0.0.1:8000
DEMO_MODE=1 python -m app   # synthetic data, works offline
```

### Privacy

- **Password login.** Every page and API call needs it. Five wrong tries locks logins from
  that address for 15 minutes. Sessions last 14 days (`SESSION_DAYS`). Changing
  `APP_PASSWORD` logs out every session. If `APP_PASSWORD` is unset, a random one is
  printed at startup so the app is never left open.
- **Your machine only.** `python -m app` listens on `127.0.0.1`, so other devices can't
  reach it. To use it from your phone, put it behind a private tunnel such as Tailscale
  rather than opening a port to the internet.
- **Secrets stay out of git.** `.env`, the SQLite database (paper trades, alerts, score
  history) and caches are git-ignored.
- **Keep the GitHub repo private** (Settings → General → Danger Zone → Change visibility).

## What it pulls

| Signal | Source | Weight | Notes |
|---|---|---|---|
| News | Yahoo Finance RSS, Google News RSS | 30% | Newer headlines count more (12h half-life) |
| Social | Reddit, StockTwits | 25% | Weighted by upvotes and recency; StockTwits' own Bullish/Bearish tags are trusted |
| Momentum | Yahoo Finance daily closes | 15% | 5-day return |
| Insiders | SEC Form 4 | 15% | Open-market buys vs sells over 90 days. Sales count ¼ as much: insiders sell for many reasons, buy for one. Grants and option exercises ignored |
| Funds | SEC 13F (Berkshire, Burry, Ackman, Bridgewater, ARK, Renaissance) | 10% | Quarterly, up to 45 days stale |
| Congress | House + Senate STOCK Act disclosures via Financial Modeling Prep | 5% | Needs `FMP_API_KEY`. Up to 45 days stale |

Each component is in `[-1, 1]`; the score is the weighted blend scaled to `[-100, 100]`.
Sources with no data are left out and the other weights renormalised. **Confidence** shows
how much data backs the number. Above +20 is bullish, below −20 bearish. Tune in
`app/signals.py`.

## AI sentiment (Claude)

Keyword scoring misses sarcasm ("great, another *record quarter* lol 💀") and posts about a
different company. Set `AI_SENTIMENT=1` and `ANTHROPIC_API_KEY` and new headlines/posts are
scored by Claude, one batched request per ticker. Each text is scored once and cached in
SQLite, so refreshing doesn't re-bill. If the API is down, rate-limited or unconfigured,
the app quietly falls back to keyword scoring. An "AI sentiment" badge shows when it's on.
Default model is `claude-opus-5-5` at low effort; `AI_MODEL=claude-haiku-5-5` is far
cheaper.

## Alerts

Every `ALERT_INTERVAL_MIN` (15) minutes the watchlist is re-scored and saved. An alert fires
when a score moves `ALERT_DELTA` (25) points within `ALERT_LOOKBACK_HOURS` (24), or turns
bullish/bearish. At most one alert per ticker per 2 hours. Alerts show in the dashboard
(🔔), as browser notifications (click the bell once to allow), and on your phone if you set
`ALERT_WEBHOOK_URL`:

- **ntfy** (simplest): install the ntfy app, subscribe to a long random topic name, set
  `ALERT_WEBHOOK_URL=https://ntfy.sh/<that-topic>`. Anyone who guesses the topic can read
  it, so make it long and random, or self-host ntfy.
- **Discord/Slack**: paste an incoming-webhook URL.

## Backtest: does the score work?

The Backtest panel compares scores with what the stock did over the next 1, 5 or 20
trading days:

- **Full score (recorded):** every snapshot the alert loop saves. This is the honest test
  of the blended score, but it starts empty because past news and social posts can't be
  fetched for free. Let it run a few weeks before reading anything into it.
- **Momentum, past year:** the price-only part replayed over a year of daily data,
  available immediately.

How to read it: **IC** is the rank correlation between score and later return; for real
markets anything consistently above ~0.05 is good, and around 0 means no edge. **Hit
rate** is how often bullish/bearish calls got the direction right; 50% is a coin flip.
**Long − short** is the average return after bullish calls minus after bearish ones.
Trading costs and slippage are ignored, so real results would be worse.

## Configuration

All settings are environment variables; see `.env.example` for the full list. Key ones:
`APP_PASSWORD`, `WATCHLIST`, `USER_AGENT` (include your email: the SEC blocks requests
without contact info), `FMP_API_KEY`, `AI_SENTIMENT`, `ANTHROPIC_API_KEY`, `AI_MODEL`,
`ALERT_*`, `STARTING_CASH`, `MAX_POSITION_PCT` (paper risk limit, default 20% of equity).

## Tests

```bash
pytest
```

Parsers are tested against saved sample payloads and Claude calls are mocked, so tests
never touch the network or spend money.

## Known limits

- **Unofficial endpoints.** Yahoo and StockTwits public endpoints can change or rate-limit;
  Reddit prefers registered OAuth apps for heavy use. The live connectors were written
  against documented response formats but haven't been run against the real services
  yet. Check the source status dots in the header the first time you run it live.
- **Congress data** depends on Financial Modeling Prep's `senate-trades` / `house-trades`
  endpoints; if they rename them, update `app/sources/congress.py`.
- **13F name matching** skips abbreviated issuer names (e.g. `BANK AMER CORP`) rather than
  guess.
- **Free price feeds are delayed**: fine for research, not for timing fills.
