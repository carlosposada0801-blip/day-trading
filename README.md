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

## Using the dashboard

- **Theme:** the header button cycles Auto (follows your device) → Light → Dark. Your
  choice is remembered and applied before the page draws, so there's no white flash.
- **Look up any ticker** with the search box, even ones not on your watchlist.
- **Edit watchlist** adds or removes stocks; saved on the server and used by alerts and
  the autotrader.
- **Click a column header** to sort; the sort is remembered. Hover the price and backtest
  charts for exact values.
- **Auto-refresh** runs every minute but pauses while the tab is in the background and
  catches up when you return. The header shows when data was last updated.
- The tab title shows a count of unseen alerts plus trades waiting for approval, e.g.
  `(2) Signal Desk`. When the autotrader is on, a **STOP** button stays in the header.

**Keyboard shortcuts** (press `?` in the app): `/` search · `j`/`k` next/previous stock ·
`Esc` close · `r` refresh · `p` pause auto-refresh · `a` alerts · `g` autotrader ·
`t` theme.

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

## Autopilot (hands-off)

Put money into the account and let it run. The Autopilot panel sits at the top of the
dashboard.

**What it does every cycle while the market is open:**
1. **Finds deposits and withdrawals.** It compares the account's cash with what its own
   orders explain. A jump up is a deposit, a drop is a withdrawal. You get a phone alert
   either way, and "You've put in" stays accurate so profit is measured honestly.
2. **Invests in a core index fund.** By default 60% of the money goes into VOO and is
   rebalanced only when it drifts more than 5%. Big deposits are invested in steps of up to
   $5,000 per cycle.
3. **Trades the rest on signals.** 35% goes to the signal strategy, under all the Autotrader
   limits below, and never beyond its own budget. 5% always stays in cash.
4. **Sets profit aside for you.** Once you're up 10% on what you've put in, half the profit
   is set aside as cash. If there isn't enough cash, it sells some holdings (the core fund
   first). That cash is never reinvested, and you get a phone alert to withdraw it. Later
   profits are set aside the same way, but only above the previous high, so a dip never
   re-triggers it. Withdrawing the money in the Robinhood app clears it automatically, or
   click **Keep it invested** to put it back to work.
5. **Weekly summary** to your phone after Friday's close: value, profit, set-aside cash,
   number of orders.

**Starting it:** click **Start autopilot**. It runs a pre-flight checklist first and won't
start until every required item passes. For Robinhood the required items are:
- the broker connection works and the account has money in it
- `ALLOW_LIVE_AUTO=1` is set
- phone notifications are configured
- the kill switch is off
- the market calendar covers the current year

It also warns (without blocking) if your signal rules didn't beat holding SPY in the
backtest, and reminds you the app has to run on an always-on machine.

**Practice first:** with the practice account selected, the panel has Deposit and
Withdraw buttons for pretend money, so you can watch the whole cycle before using
Robinhood.

**Why it won't move money to your bank on its own:** the Robinhood connection is built for
trading, and an app that can send money out of your account is a much bigger risk if
anything goes wrong (a bug, a stolen login token). Withdrawing stays a two-tap step in the
Robinhood app; Autopilot does the deciding and tells you when.

All of the numbers above are settings under `[autopilot]` in `strategy.toml`. Set
`core_pct = 0` to have everything follow signals, or raise it to be more conservative.

### Small accounts ($100 a paycheck)

The shipped `strategy.toml` is set up for small regular deposits:
- **Fractional shares** (`fractional = true`): $60 buys 0.11 of a $525 VOO share, so every
  dollar is invested from the first paycheck. Quantities go down to 1/10,000 of a share.
- **No dust orders**: nothing smaller than `min_order_usd` ($5) is bought or rebalanced.
- **Few positions** (`max_positions = 3`, 15% each), since $100 split five ways is pointless.
- **Paycheck schedule**: `expected_deposit_usd = 100` every `deposit_every_days = 14`. The
  dashboard shows when the next one is expected, and you get a nudge if it's 3+ days late.
- Money that the signal or penny rules don't have a use for stays as cash until something
  qualifies. With a small account that can be a good share of it at first.

Fractional orders through Robinhood's agent connection haven't been verified. If its order
review rejects fractional limit orders, the app blocks the trade and alerts you. Set
`fractional = false` to fall back to whole shares, and consider a lower-priced core fund.

## Penny stocks

On in the shipped settings (`[penny] enabled = true`), with 10% of your money. **These are the
riskiest thing the app can buy**: prices swing 20–50% in days, many trade so thinly you
can't sell at a fair price, and they're the favourite target of pump-and-dump schemes run on
the same social media this app reads. In the demo data, the pump example has the highest
score of any stock on the board; without the guard below, the app would buy it first.

So penny stocks get their own sleeve with stricter rules:
- **Exchange-listed only**: no OTC / pink-sheet stocks.
- **$0.50 to $5.00** price range.
- **Liquidity**: at least $1M traded per day on average over 20 days, so you can get out.
- **Higher bar**: score 50+ (vs 40 for regular buys).
- **Pump guard**:
  - Refuses a stock up 50%+ in 5 days on social hype with no supporting news.
  - Refuses a volume spike over 5x normal during a 30%+ run-up.
- **Own budget and count**: 10% of money, at most 2 positions.
- **Own exits**: −15% stop, +30% target, 10-day max hold. Penny stocks are noisy, so a tight
  stop would trigger constantly.
- **Re-checked at approval**: an approved buy is re-checked against these rules with a fresh
  price.
- **Regular buys skip them**: stocks under $5 never come in through the regular signal rules
  while the penny sleeve is on.

Candidates come from your `[penny] watchlist` plus penny tickers trending on Reddit. The
Penny stocks panel shows each one and exactly why it can or can't be bought. Set
`enabled = false` to turn the whole sleeve off.

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
