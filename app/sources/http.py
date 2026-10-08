import httpx

from app.config import settings


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent, "Accept-Encoding": "gzip, deflate"},
    )
