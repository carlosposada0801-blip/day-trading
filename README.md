# Signal Desk

A private trading research dashboard and autotrader. It blends **news**, **social media**, **corporate
insiders**, **big funds**, **members of Congress** and **price momentum** into one score per
ticker, alerts you when scores move, measures whether the score actually predicts anything,
and can trade on its own (practice account or Robinhood) under strict rules you set.

> Not financial advice. Automated trading can lose money quickly; start in practice mode.

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

## Autotrader

The Autotrader panel turns signals into trades under rules you control in `strategy.toml`.

**Modes**
- **Off**: nothing happens (default).
- **Ask me first**: during market hours it proposes trades and pings your phone. You approve
  or reject each one in the dashboard. Proposals expire after 15 minutes, and risk checks
  run again with a fresh price when you approve.
- **Automatic**: places orders itself. On Robinhood this also needs `ALLOW_LIVE_AUTO=1` in
  `.env`, so it can't be switched on by accident.

**Brokers**
- **Practice account**: simulated fills against your paper portfolio. Start here.
- **Robinhood**: uses Robinhood's official Agentic Trading MCP server (see below).

**What it does each cycle** (every 5 minutes while the market is open): check sell rules
on everything you hold (stop-loss, take-profit, score drop, max hold time, optional
end-of-day close), then look for new buys, then run every risk check, then act according
to the mode. Every decision, including blocked ones and the reasons, goes into the
decision journal, which you can download as CSV for taxes and review.

**Safety limits**, all in `strategy.toml`:
- **STOP ALL TRADING** button: turns the autotrader off, cancels pending approvals and
  open orders where possible, and pushes an alert. It stays stopped until you click Resume
  and pick a mode again.
- **Daily loss limit**: if equity falls 3% from the day's open, no new buys until tomorrow.
  Sells still run.
- **Caps**: trades per day, dollars per order, % of account per position, number of
  positions, buying power.
- **Bad data**: no new buys when more than one data source is failing.
- **Timing**: no trades in the first or last 15 minutes of the session; market holidays
  and early closes are respected (calendar in `app/trading/calendar.py` covers 2026–2027;
  the app refuses to trade in a year it doesn't know).
- **Order type**: limit orders only, never market orders (last price ±0.5%).
- **Day trades**: at most 3 in 5 business days by default. The SEC approved removing the
  pattern-day-trader rule in April 2026, but brokers have until October 2027 to switch.
  Confirm Robinhood's current policy before setting `max_day_trades_per_5d = -1`.
- **Wash sales**: won't rebuy a stock within 30 days of selling it at a loss.
- If a stop-loss sell is blocked (e.g. by the day-trade cap), you get an urgent push so you
  can decide yourself.

**Rules backtest** (bottom of the panel) replays your current rules over a year of prices
using the momentum score, or over the full scores the app has recorded, with trading costs,
and compares the result to just holding SPY. If your rules don't beat SPY, don't automate
them.

### Connecting Robinhood

Robinhood doesn't offer a general stock-trading API, and unofficial reverse-engineered
libraries aren't supported and can conflict with its terms. What it does offer (since May 2026) is **Agentic Trading**: an official
MCP server at `https://agent.robinhood.com/mcp/trading`, with these properties:
- You sign in on robinhood.com in your browser (OAuth); this app never sees your password.
- Agents can read your accounts but can **only place orders in a separate Agentic account**
  you fund for this purpose. Equities only during the beta.
- Robinhood has its own controls (trade approvals in Agent Settings, per-trade notifications,
  and a disconnect switch in the app). The disconnect switch is your kill switch from your
  phone.

Steps:
1. In the Robinhood app on desktop, open an **Agentic account** and fund it with an amount
   you're fully prepared to lose. That balance is your real risk limit.
2. In Signal Desk pick **Robinhood**, click **Connect Robinhood**, sign in on the page that
   opens, and approve. The token is saved in `DATA_DIR/robinhood_tokens.json` (owner-only
   permissions, git-ignored).
3. Run **Ask me first** for a few weeks before considering Automatic.

The adapter discovers Robinhood's tools when it connects and maps order fields onto their
input schemas. It **refuses to trade** if a required field can't be filled. Every order goes
through Robinhood's `review_equity_order` first and is blocked if the review returns
warnings or errors. If Robinhood names tools differently or needs an account number, set
them under `[robinhood]` in `strategy.toml`. This adapter was built from public
descriptions of the MCP server and tested against a simulated server; it has not yet been
run against Robinhood itself. Check the first connection and your first approved order
carefully.

## Running it all the time

Trades and alerts only happen while the app is running. Exit rules are checked by the app,
not held at Robinhood, so **if the app is down, stop-losses don't fire**. Run it on an
always-on machine:

- **Docker** (any small cloud server or home machine): `docker compose up -d`. Data and the
  Robinhood login live in `./data`. The port is bound to 127.0.0.1 only.
- **systemd**: see `deploy/signal-desk.service`.
- **Reaching it remotely**: use Tailscale, or an SSH tunnel
  (`ssh -L 8000:127.0.0.1:8000 you@server`, then open http://127.0.0.1:8000). The tunnel
  also makes the Robinhood login redirect work on a headless server. Don't open the port to
  the internet.

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
