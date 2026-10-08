"""Push notifications to your phone (ntfy) or a chat webhook (Discord/Slack)."""
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


async def push(title: str, message: str, priority: str = "default", extra: dict | None = None) -> None:
    url = settings.alert_webhook_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if "ntfy" in url:
                await c.post(url, content=message.encode(),
                             headers={"Title": title, "Priority": priority, "Tags": "chart_with_upwards_trend"})
            else:  # "content" for Discord, "text" for Slack
                text = f"**{title}**\n{message}"
                await c.post(url, json={"text": text, "content": text, **(extra or {})})
    except httpx.HTTPError as e:
        log.warning("push notification failed: %s", e)
