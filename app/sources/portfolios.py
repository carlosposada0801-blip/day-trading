"""What notable funds hold and how that changed, from SEC 13F-HR filings.

13F filings are quarterly and published up to 45 days after quarter end, so
this is a slow "smart money" signal: useful context, not a day-trading trigger.
"""
import re
import xml.etree.ElementTree as ET

from app.config import TRACKED_FUNDS
from app.models import FundMove
from app.sources.http import client

_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "PLC", "LP", "LLC", "HLDGS", "HOLDINGS",
    "GROUP", "GRP", "CL", "CLASS", "A", "B", "C", "COM", "NEW", "DE", "DEL", "MD", "NY", "THE", "SA", "NV", "AG", "SHS", "ORD",
}


def normalize_name(name: str) -> str:
    words = re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split()
    while words and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def build_ticker_map(company_tickers: dict) -> dict[str, str]:
    """Map normalized company names to tickers using SEC's company_tickers.json."""
    out: dict[str, str] = {}
    for row in company_tickers.values():
        out.setdefault(normalize_name(row["title"]), row["ticker"].upper())
    return out


def parse_info_table(xml_text: str) -> dict[str, tuple[int, int]]:
    """Return {issuer name: (shares, value_usd)} for common-stock rows (options excluded)."""
    root = ET.fromstring(xml_text)
    holdings: dict[str, tuple[int, int]] = {}
    for row in root.iter():
        if not row.tag.endswith("infoTable"):
            continue
        fields = {el.tag.split("}")[-1]: (el.text or "").strip() for el in row.iter()}
        if fields.get("putCall"):
            continue
        name = fields.get("nameOfIssuer", "")
        shares = int(float(fields.get("sshPrnamt") or 0))
        value = int(float(fields.get("value") or 0))
        prev = holdings.get(name, (0, 0))
        holdings[name] = (prev[0] + shares, prev[1] + value)
    return holdings


def diff_holdings(fund: str, period: str, latest: dict, previous: dict,
                  ticker_map: dict[str, str]) -> list[FundMove]:
    """Compare two filings. Issuers we can't map to a ticker are skipped rather than guessed."""
    by_ticker: dict[str, dict] = {}
    for snapshot, key in ((latest, "now"), (previous, "prev")):
        for name, (shares, value) in snapshot.items():
            ticker = ticker_map.get(normalize_name(name))
            if not ticker:
                continue
            row = by_ticker.setdefault(ticker, {"issuer": name, "now": 0, "prev": 0, "value": 0})
            row[key] += shares
            if key == "now":
                row["value"] += value
    return [FundMove(fund=fund, ticker=t, issuer=r["issuer"], shares=r["now"], prev_shares=r["prev"],
                     value_usd=r["value"], period=period) for t, r in by_ticker.items()]


async def _info_table(c, cik: str, accession: str) -> dict[str, tuple[int, int]]:
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    idx = (await c.get(f"{base}/index.json")).json()
    xml_files = [i["name"] for i in idx["directory"]["item"]
                 if i["name"].lower().endswith(".xml") and i["name"].lower() != "primary_doc.xml"]
    r = await c.get(f"{base}/{xml_files[0]}")
    r.raise_for_status()
    return parse_info_table(r.text)


async def fetch_all() -> list[FundMove]:
    moves: list[FundMove] = []
    async with client() as c:
        r = await c.get("https://www.sec.gov/files/company_tickers.json")
        r.raise_for_status()
        ticker_map = build_ticker_map(r.json())
        for fund, cik in TRACKED_FUNDS.items():
            sub = (await c.get(f"https://data.sec.gov/submissions/CIK{cik}.json")).json()
            recent = sub["filings"]["recent"]
            filings = [(acc, rd) for f, acc, rd in zip(recent["form"], recent["accessionNumber"], recent["reportDate"])
                       if f == "13F-HR"][:2]
            if len(filings) < 2:
                continue
            latest = await _info_table(c, cik, filings[0][0])
            previous = await _info_table(c, cik, filings[1][0])
            moves += diff_holdings(fund, filings[0][1], latest, previous, ticker_map)
    return moves
