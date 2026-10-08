"""Runtime settings, read from environment variables."""
import os
from dataclasses import dataclass, field


def _list(name: str, default: str) -> list[str]:
    return [s.strip().upper() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass
class Settings:
    # Tickers shown on the dashboard.
    watchlist: list[str] = field(default_factory=lambda: _list("WATCHLIST", "AAPL,NVDA,TSLA,MSFT,AMD,AMZN,META,GOOGL"))
    # Use synthetic data instead of hitting live sources (offline dev, demos, tests).
    demo_mode: bool = os.getenv("DEMO_MODE", "0") == "1"
    # SEC requires a descriptive User-Agent with contact info.
    user_agent: str = os.getenv("USER_AGENT", "day-trading-signals/0.1 (contact: you@example.com)")
    subreddits: list[str] = field(default_factory=lambda: [
        s.strip() for s in os.getenv("SUBREDDITS", "wallstreetbets,stocks,investing").split(",") if s.strip()
    ])
    cache_ttl: int = int(os.getenv("CACHE_TTL", "300"))
    db_path: str = os.getenv("DB_PATH", "paper_trading.db")
    starting_cash: float = float(os.getenv("STARTING_CASH", "100000"))
    # Paper-trading guardrail: no single position may exceed this share of equity.
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.20"))


settings = Settings()

# Well-known funds whose 13F filings we track ("other portfolios"). CIKs from SEC EDGAR.
TRACKED_FUNDS: dict[str, str] = {
    "Berkshire Hathaway": "0001067983",
    "Scion Asset Management (Burry)": "0001649339",
    "Pershing Square (Ackman)": "0001336528",
    "Bridgewater Associates": "0001350694",
    "ARK Investment Management": "0001697748",
    "Renaissance Technologies": "0001037389",
}
