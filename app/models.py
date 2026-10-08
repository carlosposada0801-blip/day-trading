from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class Article(BaseModel):
    ticker: str
    title: str
    url: str
    source: str
    published: Optional[datetime] = None
    sentiment: float = 0.0


class SocialPost(BaseModel):
    ticker: str
    text: str
    url: str
    platform: Literal["reddit", "stocktwits", "demo"]
    author: str = ""
    score: int = 0  # upvotes / likes
    created: Optional[datetime] = None
    sentiment: float = 0.0
    # Explicit label from the platform when it has one (StockTwits Bullish/Bearish).
    label: Optional[Literal["bullish", "bearish"]] = None


class FundMove(BaseModel):
    fund: str
    ticker: str
    issuer: str
    shares: int
    prev_shares: int
    value_usd: int
    period: str  # report date of the latest filing

    @property
    def change(self) -> int:
        return self.shares - self.prev_shares


class PriceInfo(BaseModel):
    ticker: str
    price: float
    prev_close: float
    closes: list[float]  # recent daily closes, oldest first
    dates: list[str] = []  # ISO dates matching closes

    @property
    def change_pct(self) -> float:
        return (self.price / self.prev_close - 1) * 100 if self.prev_close else 0.0


class Signal(BaseModel):
    ticker: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    score: float  # -100 (bearish) .. +100 (bullish)
    stance: Literal["bullish", "bearish", "neutral"]
    confidence: float  # 0..1, how much data backs the score
    components: dict[str, Optional[float]]  # each -1..1, None when no data
    ai: bool = False  # True when Claude scored the text sentiment
    counts: dict[str, int]


class InsiderTrade(BaseModel):
    ticker: str
    insider: str
    title: str  # officer title / "Director" / "10% owner"
    code: str  # SEC transaction code: P = open-market buy, S = open-market sale
    shares: float
    price: float
    date: str
    url: str = ""

    @property
    def value(self) -> float:
        return self.shares * self.price


class CongressTrade(BaseModel):
    ticker: str
    member: str
    chamber: str  # "House" / "Senate"
    side: Literal["buy", "sell"]
    amount_low: int
    amount_high: int
    traded: str
    disclosed: str
    url: str = ""

    @property
    def amount_mid(self) -> float:
        return (self.amount_low + self.amount_high) / 2
