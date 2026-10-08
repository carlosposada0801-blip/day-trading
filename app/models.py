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
    counts: dict[str, int]
