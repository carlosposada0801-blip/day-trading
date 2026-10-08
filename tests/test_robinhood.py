"""Exercise the Robinhood adapter against a fake, in-process MCP server shaped like Robinhood's."""
import asyncio

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from app.trading import strategy
from app.trading.brokers import BrokerError
from app.trading.robinhood import RobinhoodBroker, map_order_args, problems_in

placed = []


def fake_server(review_warnings=None):
    s = MCPServer("fake-robinhood")

    @s.tool()
    def get_account() -> dict:
        return {"account": {"portfolio_value": "1500.00", "buying_power": "900.50"}}

    @s.tool()
    def get_equity_positions() -> dict:
        return {"results": [{"symbol": "AAPL", "quantity": "2", "average_buy_price": "200.00"}]}

    @s.tool()
    def review_equity_order(symbol: str, side: str, quantity: float, type: str, limit_price: float,
                            time_in_force: str, account_number: str) -> dict:
        return {"estimated_cost": quantity * limit_price, "warnings": review_warnings or []}

    @s.tool()
    def place_equity_order(symbol: str, side: str, quantity: float, type: str, limit_price: float,
                           time_in_force: str, account_number: str) -> dict:
        placed.append(locals())
        return {"order": {"id": "ord-123", "state": "confirmed"}}

    return s


def broker(**kw):
    cfg = strategy.Strategy()
    cfg.robinhood.order_args = {"account_number": "AGENT1"}
    srv = fake_server(**kw)
    b = RobinhoodBroker(cfg, client_factory=lambda: Client(srv))
    return b


def test_account_and_positions():
    b = broker()
    acct = asyncio.run(b.account())
    assert (acct.equity, acct.cash) == (1500.0, 900.5)
    pos = asyncio.run(b.positions())
    assert pos[0].ticker == "AAPL" and pos[0].qty == 2 and pos[0].avg_cost == 200


def test_review_then_place_maps_args():
    placed.clear()
    b = broker()
    assert "estimated_cost" in asyncio.run(b.review("NVDA", "buy", 3, 130.123))
    r = asyncio.run(b.place("NVDA", "buy", 3, 130.123))
    assert r.status == "submitted" and r.order_id == "ord-123"
    args = placed[0]
    assert args["symbol"] == "NVDA" and args["limit_price"] == 130.12 and args["type"] == "limit"
    assert args["account_number"] == "AGENT1"


def test_review_warnings_block_order():
    b = broker(review_warnings=["Order exceeds buying power"])
    with pytest.raises(BrokerError, match="buying power"):
        asyncio.run(b.review("NVDA", "buy", 300, 130))


def test_unmappable_required_field_refuses():
    schema = {"properties": {"symbol": {}, "mystery_field": {}}, "required": ["symbol", "mystery_field"]}
    with pytest.raises(BrokerError, match="mystery_field"):
        map_order_args(schema, {"symbol": "A"}, {})


def test_enum_values_matched_case_insensitively():
    schema = {"properties": {"side": {"enum": ["BUY", "SELL"]}}, "required": ["side"]}
    assert map_order_args(schema, {"side": "buy"}, {}) == {"side": "BUY"}
    with pytest.raises(BrokerError, match="doesn't accept"):
        map_order_args({"properties": {"side": {"enum": ["long"]}}, "required": []}, {"side": "buy"}, {})


def test_missing_tool_explains():
    cfg = strategy.Strategy()
    b = RobinhoodBroker(cfg, client_factory=lambda: Client(MCPServer("empty")))
    with pytest.raises(BrokerError, match="no Robinhood tool"):
        asyncio.run(b.account())


def test_problems_in():
    assert problems_in({"a": {"warnings": []}, "errors": None}) == []
    assert problems_in({"x": [{"rejection_reason": "market closed"}]})
