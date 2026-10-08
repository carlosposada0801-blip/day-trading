"""Robinhood via its official Agentic Trading MCP server (https://agent.robinhood.com/mcp/trading).

You sign in on robinhood.com in your own browser (OAuth); this app never sees your password.
Orders can only be placed in the separate Agentic account you fund for this purpose.

Robinhood doesn't publish a stable tool list here, so the adapter discovers tools at connect
time, maps order fields onto each tool's input schema, and refuses to trade if a required
field can't be mapped. Override names or add fixed arguments in strategy.toml [robinhood].
Every order is run through Robinhood's review tool first and blocked if it reports problems.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx2
from mcp import Client
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from app.config import settings
from app.trading.brokers import Account, BrokerError, OrderResult, Position
from app.trading.strategy import Strategy

log = logging.getLogger(__name__)
CALLBACK_PATH = "/broker/robinhood/callback"

# Candidate tool names per capability. Money-moving tools are never fuzzy-matched.
TOOL_CANDIDATES = {
    "review": ["review_equity_order"],
    "place": ["place_equity_order"],
    "cancel": ["cancel_equity_order", "cancel_order"],
    "positions": ["get_equity_positions", "get_positions", "list_positions", "get_holdings"],
    "account": ["get_account", "get_accounts", "get_portfolio", "get_buying_power"],
    "orders": ["get_equity_orders", "get_orders", "list_orders"],
}
READ_KEYWORDS = {"positions": "position", "account": "account", "orders": "order"}

# Our order fields -> names Robinhood's schema might use.
SYNONYMS = {
    "symbol": ["symbol", "ticker", "instrument_symbol", "stock_symbol"],
    "side": ["side", "direction", "action", "order_side"],
    "quantity": ["quantity", "qty", "shares", "share_quantity"],
    "type": ["type", "order_type"],
    "limit_price": ["limit_price", "price", "limitprice"],
    "time_in_force": ["time_in_force", "tif", "duration"],
}


class AuthRequired(BrokerError):
    pass


class FileTokenStorage(TokenStorage):
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.is_file() else {}

    def _write(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(d))
        os.chmod(self.path, 0o600)

    async def get_tokens(self):
        t = self._read().get("tokens")
        return OAuthToken.model_validate(t) if t else None

    async def set_tokens(self, tokens) -> None:
        self._write({**self._read(), "tokens": tokens.model_dump(mode="json")})

    async def get_client_info(self):
        c = self._read().get("client")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, info) -> None:
        self._write({**self._read(), "client": info.model_dump(mode="json")})

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class Login:
    """Bridges the OAuth flow to the dashboard: the auth URL is shown there, the callback lands here."""

    def __init__(self):
        self.url: str | None = None
        self.future: asyncio.Future | None = None
        self.interactive = False

    async def redirect(self, url: str) -> None:
        if not self.interactive:
            raise AuthRequired("Robinhood login needed: click 'Connect Robinhood' in the dashboard")
        self.url = url
        self.future = asyncio.get_running_loop().create_future()

    async def callback(self) -> AuthorizationCodeResult:
        try:
            code, state = await asyncio.wait_for(self.future, timeout=300)
        finally:
            self.url = None
        return AuthorizationCodeResult(code=code, state=state)

    def complete(self, query: str) -> bool:
        params = parse_qs(query)
        if not self.future or self.future.done() or "code" not in params:
            return False
        self.future.set_result((params["code"][0], params.get("state", [None])[0]))
        return True


login = Login()


def _payload(result):
    if result.is_error:
        raise BrokerError(" ".join(getattr(c, "text", "") for c in result.content) or "tool error")
    if result.structured_content:
        return result.structured_content
    texts = [c.text for c in result.content if getattr(c, "text", None)]
    for t in texts:
        try:
            return json.loads(t)
        except ValueError:
            pass
    return " ".join(texts)


def _leaf(eg: BaseExceptionGroup) -> BaseException:
    """The most useful single exception inside a (possibly nested) exception group."""
    leaves = []

    def collect(e):
        if isinstance(e, BaseExceptionGroup):
            for x in e.exceptions:
                collect(x)
        else:
            leaves.append(e)

    collect(eg)
    return next((e for e in leaves if isinstance(e, BrokerError)), leaves[0] if leaves else eg)


def _walk(obj):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _num(d: dict, keys: list[str]) -> float | None:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            try:
                return float(d[k])
            except (TypeError, ValueError):
                pass
    return None


def parse_positions(payload) -> list[Position]:
    out = []
    for node in _walk(payload):
        if isinstance(node, dict):
            sym = node.get("symbol") or node.get("ticker")
            qty = _num(node, ["quantity", "qty", "shares"])
            if isinstance(sym, str) and qty:
                cost = _num(node, ["average_buy_price", "average_cost", "avg_cost", "average_price", "cost_basis_per_share"])
                out.append(Position(sym.upper(), qty, cost or 0.0))
    return out


def parse_account(payload) -> Account:
    for node in _walk(payload):
        if isinstance(node, dict):
            equity = _num(node, ["equity", "total_equity", "portfolio_value", "total_value", "market_value"])
            cash = _num(node, ["buying_power", "cash", "cash_available", "withdrawable_amount"])
            if equity is not None and cash is not None:
                return Account(equity=equity, cash=cash)
    raise BrokerError(f"couldn't find equity and buying power in Robinhood's account response: {str(payload)[:300]}")


def problems_in(payload) -> list[str]:
    """Collect non-empty warning/error/rejection fields from a review response."""
    found = []
    for node in _walk(payload):
        if isinstance(node, dict):
            for k, v in node.items():
                if any(w in k.lower() for w in ("warning", "error", "reject", "alert")) and v:
                    found.append(f"{k}: {v}")
    return found


def map_order_args(schema: dict, values: dict, extra: dict) -> dict:
    props = schema.get("properties", {})
    args = dict(extra)
    for canon, value in values.items():
        name = next((n for n in SYNONYMS[canon] if n in props), None)
        if name is None:
            continue
        enum = props[name].get("enum")
        if enum and isinstance(value, str):
            match = next((e for e in enum if str(e).lower() == value.lower()), None)
            if match is None:
                raise BrokerError(f"Robinhood field '{name}' doesn't accept '{value}' (allowed: {enum})")
            value = match
        args[name] = value
    missing = [r for r in schema.get("required", []) if r not in args]
    if missing:
        raise BrokerError(f"can't fill required Robinhood order field(s) {missing}; "
                          "add them under [robinhood] order_args in strategy.toml")
    return args


class RobinhoodBroker:
    name = "robinhood"

    def __init__(self, cfg: Strategy, client_factory=None):
        self.cfg = cfg
        self.storage = FileTokenStorage(Path(settings.data_dir) / "robinhood_tokens.json")
        self._client_factory = client_factory or self._default_client
        self.tools: dict[str, dict] = {}

    def _default_client(self):
        provider = OAuthClientProvider(
            server_url=self.cfg.robinhood.mcp_url,
            client_metadata=OAuthClientMetadata(
                client_name="Signal Desk (personal)",
                redirect_uris=[settings.public_url.rstrip("/") + CALLBACK_PATH],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="none",
            ),
            storage=self.storage,
            redirect_handler=login.redirect,
            callback_handler=login.callback,
        )
        http = httpx2.AsyncClient(auth=provider, timeout=httpx2.Timeout(30, read=120))
        return Client(streamable_http_client(self.cfg.robinhood.mcp_url, http_client=http))

    @asynccontextmanager
    async def _session(self):
        try:
            async with self._client_factory() as c:
                if not self.tools:
                    listing = await c.list_tools()
                    self.tools = {t.name: t.input_schema for t in listing.tools}
                yield c
        except BaseExceptionGroup as eg:  # the MCP client's task group wraps errors; surface the real one
            raise _leaf(eg) from eg

    def tool(self, capability: str) -> str:
        override = self.cfg.robinhood.tools.get(capability)
        if override:
            if override not in self.tools:
                raise BrokerError(f"strategy.toml maps {capability} to '{override}' but Robinhood has no such tool")
            return override
        for name in TOOL_CANDIDATES[capability]:
            if name in self.tools:
                return name
        kw = READ_KEYWORDS.get(capability)
        if kw:
            for name in self.tools:
                if kw in name and name.startswith(("get", "list")):
                    return name
        raise BrokerError(f"no Robinhood tool found for '{capability}'. Available: {sorted(self.tools)}. "
                          f"Map one under [robinhood] tools in strategy.toml.")

    async def _call(self, capability: str, args: dict | None = None):
        async with self._session() as c:
            return _payload(await c.call_tool(self.tool(capability), args or {}))

    async def connect(self) -> list[str]:
        """Interactive login (if needed) and tool discovery."""
        login.interactive = True
        try:
            self.tools = {}
            async with self._session():
                pass
            return sorted(self.tools)
        finally:
            login.interactive = False

    async def account(self) -> Account:
        return parse_account(await self._call("account"))

    async def positions(self) -> list[Position]:
        return parse_positions(await self._call("positions"))

    def _order_args(self, capability, ticker, side, qty, limit_price) -> dict:
        qty = int(qty) if float(qty).is_integer() else qty
        values = {"symbol": ticker, "side": side, "quantity": qty, "type": "limit",
                  "limit_price": round(limit_price, 2), "time_in_force": "gfd"}
        schema = self.tools.get(self.tool(capability), {})
        tif = schema.get("properties", {}).get("time_in_force", {}).get("enum")
        if tif and "gfd" not in [str(e).lower() for e in tif]:
            values["time_in_force"] = "day"
        return map_order_args(schema, values, self.cfg.robinhood.order_args)

    async def review(self, ticker, side, qty, limit_price) -> str:
        async with self._session():
            args = self._order_args("review", ticker, side, qty, limit_price)
        payload = await self._call("review", args)
        issues = problems_in(payload)
        if issues:
            raise BrokerError("Robinhood review flagged: " + "; ".join(issues)[:500])
        return json.dumps(payload)[:1000] if not isinstance(payload, str) else payload[:1000]

    async def place(self, ticker, side, qty, limit_price) -> OrderResult:
        async with self._session():
            args = self._order_args("place", ticker, side, qty, limit_price)
        payload = await self._call("place", args)
        order_id = None
        for node in _walk(payload):
            if isinstance(node, dict):
                order_id = node.get("order_id") or node.get("id")
                if order_id:
                    break
        state = ""
        for node in _walk(payload):
            if isinstance(node, dict) and isinstance(node.get("state") or node.get("status"), str):
                state = (node.get("state") or node.get("status")).lower()
                break
        if any(s in state for s in ("reject", "cancel", "fail")):
            raise BrokerError(f"Robinhood order {state}: {str(payload)[:300]}")
        filled = "fill" in state and "partial" not in state
        return OrderResult("filled" if filled else "submitted", str(order_id) if order_id else None,
                           limit_price if filled else None, str(payload)[:500])

    async def cancel_all(self) -> str:
        if not any(n in self.tools for n in TOOL_CANDIDATES["cancel"]) and not self.cfg.robinhood.tools.get("cancel"):
            return "no cancel tool available; cancel open orders in the Robinhood app"
        orders = await self._call("orders")
        cancelled = 0
        for node in _walk(orders):
            if isinstance(node, dict) and str(node.get("state", node.get("status", ""))).lower() in (
                    "queued", "confirmed", "unconfirmed", "partially_filled", "open", "pending"):
                oid = node.get("order_id") or node.get("id")
                if oid:
                    async with self._session():
                        name = self.tool("cancel")
                        field = next((f for f in ("order_id", "id") if f in self.tools[name].get("properties", {})),
                                     "order_id")
                    await self._call("cancel", {field: oid})
                    cancelled += 1
        return f"cancelled {cancelled} open order(s)"

    def disconnect(self) -> None:
        self.storage.clear()
        self.tools = {}
