"""US House and Senate members' stock trades (STOCK Act disclosures).

Uses Financial Modeling Prep, which normalizes the official filings. Members
have up to 45 days to disclose, so this is a slow signal like 13F.
"""
import re

from app.config import settings
from app.models import CongressTrade
from app.sources.http import client

ENDPOINTS = {
    "Senate": "https://financialmodelingprep.com/stable/senate-trades?symbol={t}&apikey={k}",
    "House": "https://financialmodelingprep.com/stable/house-trades?symbol={t}&apikey={k}",
}


def parse_amount(text: str) -> tuple[int, int]:
    """'$1,001 - $15,000' -> (1001, 15000); 'Over $50,000,000' -> (50000000, 50000000)."""
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text or "")]
    if not nums:
        return 0, 0
    return nums[0], nums[-1]


def parse(rows: list[dict], ticker: str, chamber: str) -> list[CongressTrade]:
    out = []
    for r in rows:
        kind = (r.get("type") or "").lower()
        if kind.startswith("purchase"):
            side = "buy"
        elif kind.startswith("sale"):
            side = "sell"
        else:  # exchanges, unknown
            continue
        low, high = parse_amount(r.get("amount", ""))
        name = " ".join(filter(None, [r.get("firstName"), r.get("lastName")])) or r.get("office") or "Unknown"
        out.append(CongressTrade(ticker=ticker, member=name, chamber=chamber, side=side,
                                 amount_low=low, amount_high=high,
                                 traded=r.get("transactionDate", ""), disclosed=r.get("disclosureDate", ""),
                                 url=r.get("link", "")))
    return out


async def fetch(ticker: str) -> list[CongressTrade]:
    if not settings.fmp_api_key:
        raise RuntimeError("set FMP_API_KEY to enable congressional trades")
    trades: list[CongressTrade] = []
    async with client() as c:
        for chamber, url in ENDPOINTS.items():
            r = await c.get(url.format(t=ticker, k=settings.fmp_api_key))
            r.raise_for_status()
            trades += parse(r.json(), ticker, chamber)
    return sorted(trades, key=lambda t: t.traded, reverse=True)
