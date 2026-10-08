"""Broker interface plus the simulated broker used for paper trading."""
from dataclasses import dataclass
from typing import Protocol

from app import data
from app.paper import PaperAccount, TradeError


class BrokerError(Exception):
    pass


@dataclass
class Position:
    ticker: str
    qty: float
    avg_cost: float


@dataclass
class Account:
    equity: float
    cash: float


@dataclass
class OrderResult:
    status: str  # "filled" | "submitted"
    order_id: str | None = None
    fill_price: float | None = None
    detail: str = ""


class Broker(Protocol):
    name: str

    async def account(self) -> Account: ...
    async def positions(self) -> list[Position]: ...
    async def review(self, ticker: str, side: str, qty: float, limit_price: float) -> str: ...
    async def place(self, ticker: str, side: str, qty: float, limit_price: float) -> OrderResult: ...
    async def cancel_all(self) -> str: ...


class SimBroker:
    """Paper trading against the local ledger. Limit orders fill at the current price when marketable."""
    name = "sim"

    def __init__(self, ledger: PaperAccount):
        self.ledger = ledger

    async def _prices(self, tickers) -> dict[str, float]:
        out = {}
        for t in tickers:
            p = await data.get_price(t)
            if p:
                out[t] = p.price
        return out

    async def account(self) -> Account:
        held = [p["ticker"] for p in self.ledger.summary({})["positions"]]
        s = self.ledger.summary(await self._prices(held))
        return Account(equity=s["equity"], cash=s["cash"])

    async def positions(self) -> list[Position]:
        return [Position(p["ticker"], p["qty"], p["avg_cost"]) for p in self.ledger.summary({})["positions"]]

    async def review(self, ticker, side, qty, limit_price) -> str:
        return f"simulated: {side} {qty:g} {ticker} limit {limit_price:.2f}"

    async def place(self, ticker, side, qty, limit_price) -> OrderResult:
        p = await data.get_price(ticker)
        if not p:
            raise BrokerError(f"no price for {ticker}")
        marketable = p.price <= limit_price if side == "buy" else p.price >= limit_price
        if not marketable:
            raise BrokerError(f"limit {limit_price:.2f} not marketable at {p.price:.2f}")
        held = [x.ticker for x in await self.positions()]
        try:
            r = self.ledger.order(ticker, side, qty, p.price, await self._prices(held), note="autotrader",
                                  enforce_limit=False)
        except TradeError as e:
            raise BrokerError(str(e)) from e
        return OrderResult("filled", str(r["id"]), p.price)

    async def cancel_all(self) -> str:
        return "simulated orders fill instantly; nothing to cancel"

    def net_deposits(self) -> float:
        return self.ledger.contributed()
