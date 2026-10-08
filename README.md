# Signal Desk

A day-trading research dashboard that blends **news**, **social media** and **what other
portfolios are doing** into one score per ticker, with a **paper-trading** account for
testing ideas without risking money.

> Research tool, not financial advice. Signals are heuristics over public chatter and
> filings. No real orders are placed.

## What it pulls

| Signal | Source | Notes |
|---|---|---|
| News | Yahoo Finance RSS, Google News RSS | Headlines scored with a finance-tuned lexicon, newer counts more (12h half-life) |
| Social | Reddit (`r/wallstreetbets`, `r/stocks`, `r/investing`), StockTwits | Upvotes and recency weight posts; StockTwits' own Bullish/Bearish tags are trusted over the lexicon |
| Other portfolios | SEC 13F-HR filings (Berkshire, Scion/Burry, Pershing/Ackman, Bridgewater, ARK, Renaissance) | Compares each fund's two latest filings: opened / added / trimmed / exited. Quarterly and up to 45 days stale, so treat it as context, not a trigger |
| Momentum | Yahoo Finance daily closes | 5-day return |

## How the score works

Each component is in `[-1, 1]`; the score is a weighted blend scaled to `[-100, 100]`:

```
news 35% · social 30% · momentum 20% · funds 15%
```

Sources with no data are left out and the remaining weights renormalised, so a missing
feed never pulls a score toward zero. **Confidence** shows how much data backs the number.
Above +20 is labelled bullish, below −20 bearish. Tune in `app/signals.py`.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # live data
DEMO_MODE=1 uvicorn app.main:app       # synthetic data, works offline
```

Open http://localhost:8000. The header shows each source's status; hover a red one to see
why it failed. One failing source never breaks the rest.

## Configuration (env vars)

| Var | Default | |
|---|---|---|
| `WATCHLIST` | `AAPL,NVDA,TSLA,MSFT,AMD,AMZN,META,GOOGL` | Tickers on the dashboard |
| `DEMO_MODE` | `0` | `1` = synthetic data |
| `USER_AGENT` | `day-trading-signals/0.1 (contact: you@example.com)` | **Set your own email**: SEC blocks requests without contact info |
| `SUBREDDITS` | `wallstreetbets,stocks,investing` | |
| `CACHE_TTL` | `300` | Seconds to cache news/social |
| `STARTING_CASH` | `100000` | Paper account |
| `MAX_POSITION_PCT` | `0.20` | Paper risk limit: no position over 20% of equity |
| `DB_PATH` | `paper_trading.db` | SQLite ledger for paper trades |

## API

`GET /api/signals` · `GET /api/ticker/{t}` · `GET /api/trending` · `GET /api/funds` ·
`GET /api/sources` · `GET /api/paper` · `POST /api/paper/order {ticker, side, qty}` ·
`POST /api/paper/reset`. Interactive docs at `/docs`.

## Tests

```bash
pytest
```

Parsers are tested against fixture payloads, so tests never touch the network.

## Known limits / next steps

- **Unofficial endpoints.** Yahoo and StockTwits public endpoints can change or rate-limit.
  Reddit asks heavy users to register an OAuth app. For anything serious, move to keyed
  APIs (Polygon/Alpaca for prices, Reddit OAuth, a news API).
- **13F ticker mapping** matches issuer names to SEC's ticker list; abbreviated names like
  `BANK AMER CORP` are skipped rather than guessed. A CUSIP→ticker map would fix this.
- **Lexicon sentiment** misses sarcasm and context. An LLM scorer is a natural upgrade.
- **Prices are delayed** on free feeds; fine for research, not for timing fills.
- Ideas: congressional trade disclosures, SEC Form 4 insider buys, alerts on score
  changes, backtesting the score against forward returns before trusting it.
