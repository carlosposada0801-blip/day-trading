"""Score snapshots + alerts when a ticker's score moves sharply or its stance flips."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app import engine, store
from app.config import settings

log = logging.getLogger(__name__)
COOLDOWN = timedelta(hours=2)  # at most one alert per ticker per window


def evaluate(ticker: str, score: float, stance: str, recent: list[dict]) -> list[tuple[str, str]]:
    """Decide which alerts fire given the new score and this ticker's recent snapshots (oldest first)."""
    if not recent:
        return []
    fired = []
    ref = max(recent, key=lambda r: abs(score - r["score"]))
    delta = score - ref["score"]
    if abs(delta) >= settings.alert_delta:
        hours = (datetime.now(timezone.utc) - datetime.fromisoformat(ref["ts"])).total_seconds() / 3600
        verb = "jumped" if delta > 0 else "dropped"
        fired.append(("move", f"{ticker} score {verb} {ref['score']:+.0f} → {score:+.0f} in {hours:.0f}h"))
    last = recent[-1]["stance"]
    if stance != last and stance != "neutral":
        fired.append(("flip", f"{ticker} turned {stance} (was {last}), score {score:+.0f}"))
    return fired


async def notify(alert: dict) -> None:
    url = settings.alert_webhook_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if "ntfy" in url:
                await c.post(url, content=alert["message"].encode(),
                             headers={"Title": f"Signal Desk: {alert['ticker']}", "Tags": "chart_with_upwards_trend"})
            else:  # generic webhook; "content" for Discord, "text" for Slack
                await c.post(url, json={"text": alert["message"], "content": alert["message"], **alert})
    except httpx.HTTPError as e:
        log.warning("alert webhook failed: %s", e)


async def run_cycle() -> list[dict]:
    """Score the watchlist once, store snapshots, and raise any alerts."""
    new_alerts = []
    for sig in await engine.compute_watchlist():
        recent = store.history(sig.ticker, since_hours=settings.alert_lookback_hours)
        store.record_score(sig.ticker, sig.score, sig.stance, sig.price, json.dumps(sig.components))
        last = store.last_alert(sig.ticker)
        if last and datetime.now(timezone.utc) - datetime.fromisoformat(last["ts"]) < COOLDOWN:
            continue
        for kind, message in evaluate(sig.ticker, sig.score, sig.stance, recent):
            alert = store.add_alert(sig.ticker, kind, message, sig.score,
                                    recent[-1]["score"] if recent else None)
            new_alerts.append(alert)
            await notify(alert)
    return new_alerts


async def loop() -> None:
    while True:
        try:
            fired = await run_cycle()
            if fired:
                log.info("alerts: %s", [a["message"] for a in fired])
        except Exception:  # noqa: BLE001 - keep the loop alive whatever happens
            log.exception("alert cycle failed")
        await asyncio.sleep(settings.alert_interval_min * 60)
