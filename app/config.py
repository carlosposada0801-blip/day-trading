"""Runtime settings, read from environment variables."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=value lines from .env without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


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
    # Congressional trades come from Financial Modeling Prep (free key at financialmodelingprep.com).
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")
    # Alerts: re-score the watchlist every N minutes and flag big moves.
    alerts_enabled: bool = os.getenv("ALERTS_ENABLED", "1") == "1"
    alert_interval_min: int = int(os.getenv("ALERT_INTERVAL_MIN", "15"))
    alert_delta: float = float(os.getenv("ALERT_DELTA", "25"))  # score points within the lookback
    alert_lookback_hours: float = float(os.getenv("ALERT_LOOKBACK_HOURS", "24"))
    # Optional push: an ntfy.sh topic URL (e.g. https://ntfy.sh/your-secret-topic) or any webhook.
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")
    # AI sentiment via the Claude API (needs ANTHROPIC_API_KEY). Lexicon is used when off or on error.
    ai_sentiment: bool = os.getenv("AI_SENTIMENT", "0") == "1"
    ai_model: str = os.getenv("AI_MODEL", "claude-opus-5-5")


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
