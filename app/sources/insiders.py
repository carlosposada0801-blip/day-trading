"""Corporate insider trades from SEC Form 4 filings.

Open-market purchases (code P) are the informative ones: insiders sell for many
reasons (taxes, diversification) but buy for one. Grants and option exercises
(codes A, M, F, ...) are ignored.
"""
import xml.etree.ElementTree as ET

from app.models import InsiderTrade
from app.sources.http import client

_cik_cache: dict[str, str] = {}


def _text(el, path: str) -> str:
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def parse_form4(xml_text: str, ticker: str, url: str = "") -> list[InsiderTrade]:
    root = ET.fromstring(xml_text)
    owner = _text(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    rel = root.find("reportingOwner/reportingOwnerRelationship")
    title = ""
    if rel is not None:
        title = (_text(rel, "officerTitle")
                 or ("Director" if _text(rel, "isDirector") in ("1", "true") else "")
                 or ("10% owner" if _text(rel, "isTenPercentOwner") in ("1", "true") else ""))
    out = []
    for tx in root.iter("nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = float(_text(tx, "transactionAmounts/transactionShares/value") or 0)
        price = float(_text(tx, "transactionAmounts/transactionPricePerShare/value") or 0)
        out.append(InsiderTrade(ticker=ticker, insider=owner, title=title, code=code, shares=shares,
                                price=price, date=_text(tx, "transactionDate/value"), url=url))
    return out


async def _cik_for(c, ticker: str) -> str | None:
    if not _cik_cache:
        r = await c.get("https://www.sec.gov/files/company_tickers.json")
        r.raise_for_status()
        for row in r.json().values():
            _cik_cache[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return _cik_cache.get(ticker)


async def fetch(ticker: str, max_filings: int = 15) -> list[InsiderTrade]:
    async with client() as c:
        cik = await _cik_for(c, ticker)
        if not cik:
            return []
        sub = await c.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        sub.raise_for_status()
        recent = sub.json()["filings"]["recent"]
        trades: list[InsiderTrade] = []
        rows = [(a, d) for f, a, d in zip(recent["form"], recent["accessionNumber"], recent["primaryDocument"])
                if f == "4"][:max_filings]
        for acc, doc in rows:
            # primaryDocument points at the XSL-rendered view; the raw XML drops the xsl folder.
            raw = doc.split("/")[-1]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{raw}"
            r = await c.get(url)
            if r.status_code == 200:
                trades += parse_form4(r.text, ticker, url)
        return trades
