from pathlib import Path

from app.sources import news, portfolios, prices, social

FIX = Path(__file__).parent / "fixtures"


def test_parse_rss():
    arts = news.parse_rss((FIX / "yahoo_rss.xml").read_text(), "AAPL", "Yahoo Finance")
    assert [a.title for a in arts] == ["Apple stock surges after record quarter", "Apple faces EU antitrust probe"]
    assert arts[0].sentiment > 0 > arts[1].sentiment
    assert arts[0].published.year == 2026


def test_parse_stocktwits_trusts_author_label():
    data = {"messages": [
        {"id": 1, "body": "crash incoming", "user": {"username": "a"}, "likes": {"total": 3},
         "entities": {"sentiment": {"basic": "Bullish"}}, "created_at": "2026-10-08T10:00:00Z"},
        {"id": 2, "body": "great quarter, strong growth", "user": {"username": "b"}, "entities": {"sentiment": None}},
    ]}
    posts = social.parse_stocktwits(data, "AAPL")
    assert posts[0].label == "bullish" and posts[0].sentiment > 0
    assert posts[1].label is None and posts[1].sentiment > 0


def test_parse_reddit_splits_by_ticker():
    data = {"data": {"children": [
        {"data": {"title": "$NVDA and AMD calls printing 🚀", "selftext": "", "permalink": "/r/x/1",
                  "author": "u", "score": 120, "created_utc": 1_790_000_000}},
        {"data": {"title": "What is the CEO thinking?", "selftext": "", "permalink": "/r/x/2",
                  "author": "v", "score": 5, "created_utc": 1_790_000_000}},
    ]}}
    posts = social.parse_reddit(data, {"AMD"})
    assert sorted(p.ticker for p in posts) == ["AMD", "NVDA"]
    assert all(p.sentiment > 0 for p in posts)


def test_parse_chart():
    data = {"chart": {"result": [{"meta": {"regularMarketPrice": 103.0},
                                  "indicators": {"quote": [{"close": [100.0, None, 101.0, 103.0]}]}}]}}
    p = prices.parse_chart(data, "X")
    assert p.closes == [100.0, 101.0, 103.0]
    assert p.prev_close == 101.0
    assert round(p.change_pct, 3) == 1.980


def test_13f_parse_and_diff():
    latest = portfolios.parse_info_table((FIX / "infotable.xml").read_text())
    assert latest["APPLE INC"] == (300_000_000, 69_900_000_000)  # put row excluded
    tmap = portfolios.build_ticker_map({
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1, "ticker": "OXY", "title": "OCCIDENTAL PETROLEUM CORP /DE/"},
    })
    previous = {"APPLE INC": (400_000_000, 1), "OCCIDENTAL PETROLEUM CORP": (10, 1), "OCCIDENTAL PETROLEUM CORP NEW": (5, 1)}
    moves = {m.ticker: m for m in portfolios.diff_holdings("BRK", "2026-06-30", latest, previous, tmap)}
    assert moves["AAPL"].change == -100_000_000
    assert moves["OXY"].shares == 0 and moves["OXY"].prev_shares == 15  # full exit, names merged
    assert "BAC" not in moves  # no ticker mapping -> skipped rather than guessed


def test_parse_form4_keeps_only_open_market():
    from app.sources import insiders
    trades = insiders.parse_form4((FIX / "form4.xml").read_text(), "AAPL")
    assert [(t.code, t.shares) for t in trades] == [("S", 20000), ("P", 1000)]  # option exercise (M) skipped
    assert trades[0].insider == "COOK TIMOTHY D" and trades[0].title == "Chief Executive Officer"
    assert trades[0].value == 20000 * 230.5


def test_parse_congress():
    from app.sources import congress
    assert congress.parse_amount("$1,001 - $15,000") == (1001, 15000)
    assert congress.parse_amount("Over $50,000,000") == (50_000_000, 50_000_000)
    rows = [
        {"firstName": "Nancy", "lastName": "Example", "type": "Purchase", "amount": "$15,001 - $50,000",
         "transactionDate": "2026-08-01", "disclosureDate": "2026-08-20", "link": "https://x"},
        {"firstName": "Bob", "lastName": "Sample", "type": "Sale (Partial)", "amount": "$1,001 - $15,000",
         "transactionDate": "2026-08-02", "disclosureDate": "2026-08-25"},
        {"firstName": "Al", "lastName": "X", "type": "Exchange", "amount": "$1,001 - $15,000"},
    ]
    trades = congress.parse(rows, "AAPL", "House")
    assert [(t.member, t.side) for t in trades] == [("Nancy Example", "buy"), ("Bob Sample", "sell")]
    assert trades[0].amount_mid == 32500.5


def test_parse_chart_dates():
    data = {"chart": {"result": [{"meta": {}, "timestamp": [1790000000, 1790086400, 1790172800],
                                  "indicators": {"quote": [{"close": [1.0, None, 2.0]}]}}]}}
    p = prices.parse_chart(data, "X")
    assert len(p.dates) == len(p.closes) == 2 and p.dates[0] < p.dates[1]
