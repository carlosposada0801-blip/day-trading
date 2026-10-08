import asyncio
from types import SimpleNamespace

from app import ai
from app.models import Article, SocialPost


def _items():
    arts = [Article(ticker="X", title="X beats estimates", url="#", source="s", sentiment=0.9)]
    posts = [SocialPost(ticker="X", text="great, another 'record quarter' lol 💀", url="#", platform="demo",
                        sentiment=0.5),
             SocialPost(ticker="X", text="labelled", url="#", platform="stocktwits", sentiment=0.75, label="bullish")]
    return arts, posts


def test_rescore_uses_claude_and_caches(monkeypatch):
    calls = []

    async def fake_score(ticker, texts):
        calls.append(texts)
        return {0: 0.6, 1: -0.7}

    monkeypatch.setattr(ai, "_score", fake_score)
    arts, posts = _items()
    assert asyncio.run(ai.rescore("CACHE", arts, posts))
    assert arts[0].sentiment == 0.6 and posts[0].sentiment == -0.7
    assert posts[1].sentiment == 0.75  # author-labelled post untouched
    arts2, posts2 = _items()
    asyncio.run(ai.rescore("CACHE", arts2, posts2))
    assert len(calls) == 1 and posts2[0].sentiment == -0.7  # served from cache


def test_failure_keeps_lexicon(monkeypatch):
    async def failing(ticker, texts):
        return None

    monkeypatch.setattr(ai, "_score", failing)
    arts, posts = _items()
    assert not asyncio.run(ai.rescore("FAIL", arts, posts))
    assert arts[0].sentiment == 0.9


def test_score_handles_refusal_and_parses(monkeypatch):
    def fake_client(stop, text):
        async def create(**kw):
            assert kw["output_config"]["format"]["type"] == "json_schema"
            return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))

    monkeypatch.setattr(ai, "_get_client", lambda: fake_client("refusal", ""))
    assert asyncio.run(ai._score("X", ["a"])) is None
    monkeypatch.setattr(ai, "_get_client",
                        lambda: fake_client("end_turn", '{"scores":[{"i":0,"sentiment":3},{"i":9,"sentiment":1}]}'))
    assert asyncio.run(ai._score("X", ["a"])) == {0: 1.0}  # clamped, out-of-range index dropped


def test_missing_credentials_falls_back(monkeypatch):
    import anthropic
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(ai, "_get_client", lambda: anthropic.AsyncAnthropic(api_key=None, auth_token=None))
    assert asyncio.run(ai._score("X", ["a"])) is None
