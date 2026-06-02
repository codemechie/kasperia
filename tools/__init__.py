import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional

from contracts.models import ToolName, ToolResponse, TelemetryPayload
from tools.base import MockTool, ToolScenario, FailureMode

logger = logging.getLogger("MockTools")

_FIXTURES = {
    "sports": {
        "matches": [
            {"match_id": "101", "home": {"name": "Brazil"}, "away": {"name": "France"}, "goals": {"home": 2, "away": 1}, "status": "LIVE", "league": "World Cup", "venue": "Stadium X"},
            {"match_id": "102", "home": {"name": "Argentina"}, "away": {"name": "Germany"}, "goals": {"home": 0, "away": 0}, "status": "SCHEDULED", "league": "World Cup", "venue": "Stadium Y"},
            {"match_id": "103", "home": {"name": "England"}, "away": {"name": "Portugal"}, "goals": {"home": 3, "away": 2}, "status": "FINISHED", "league": "Euro 2026", "venue": "Wembley"},
        ]
    },
    "ecommerce": {
        "products": [
            {"title": "Nike Air Max 270", "price": 149.99, "currency": "USD", "rating": 4.5, "in_stock": True},
            {"title": "Sony WH-1000XM5", "price": 349.99, "currency": "USD", "rating": 4.8, "in_stock": True},
            {"title": "MacBook Pro 16", "price": 2499.99, "currency": "USD", "rating": 4.7, "in_stock": False},
        ]
    },
    "news": {
        "articles": [
            {"title": "Brazil Advances to Semi-Finals After Stunning Victory", "content": "In an exciting match at Stadium X, Brazil defeated France 2-1 to advance to the semi-finals of the World Cup. Neymar scored twice in the second half.", "url": "https://sports-news.example.com/brazil-france", "published_date": "2026-06-01"},
            {"title": "Markets Rally as Tech Stocks Surge", "content": "Technology stocks led a broad market rally today, with the NASDAQ gaining 2.3%. Apple and Microsoft both hit new all-time highs.", "url": "https://finance.example.com/markets-rally", "published_date": "2026-06-01"},
        ]
    },
}


class ApiFootballMock(MockTool):
    tool_name = ToolName.API_FOOTBALL

    async def execute(self, query: str, market: str, scenario: Optional[ToolScenario] = None) -> ToolResponse:
        scenario = scenario or ToolScenario()
        started = datetime.utcnow()
        await self._simulate_behavior(scenario)
        match = self._pick_match(query)
        latency = (datetime.utcnow() - started).total_seconds() * 1000
        return ToolResponse(
            tool_name=self.tool_name,
            status="success",
            data=[TelemetryPayload(
                source_system=self.tool_name,
                timestamp=datetime.utcnow(),
                entity_id=f"match_{match['home']['name'].lower()}_{match['away']['name'].lower()}_{match['match_id']}",
                metrics={"home_score": match["goals"]["home"], "away_score": match["goals"]["away"]},
                contextual_signals={
                    "status": match["status"],
                    "league": match["league"],
                    "venue": match["venue"],
                    "home_team": match["home"]["name"],
                    "away_team": match["away"]["name"],
                },
                status="OK" if match["status"] == "LIVE" else "OK",
                confidence=0.95,
                latency_ms=latency,
                raw_data=match,
            )],
            latency_ms=latency,
            confidence=0.95,
            fetched_at=datetime.utcnow(),
        )

    def _pick_match(self, query: str) -> dict:
        q = query.lower()
        for m in _FIXTURES["sports"]["matches"]:
            if q in m["home"]["name"].lower() or q in m["away"]["name"].lower():
                return m
        return random.choice(_FIXTURES["sports"]["matches"])

    async def _simulate_behavior(self, scenario: ToolScenario) -> None:
        await self._apply_latency(scenario.latency_range)
        self._apply_failure(scenario)

    @staticmethod
    async def _apply_latency(latency_range: tuple[float, float]) -> None:
        delay = random.uniform(*latency_range)
        await asyncio.sleep(delay)

    @staticmethod
    def _apply_failure(scenario: ToolScenario) -> None:
        if scenario.force_status:
            raise _status_to_exception(scenario.force_status)
        if scenario.failure_probability > 0 and random.random() < scenario.failure_probability:
            raise _status_to_exception(scenario.failure_mode)


class TavilyMock(MockTool):
    tool_name = ToolName.TAVILY_SEARCH

    async def execute(self, query: str, market: str, scenario: Optional[ToolScenario] = None) -> ToolResponse:
        scenario = scenario or ToolScenario()
        started = datetime.utcnow()
        await self._simulate_behavior(scenario)
        article = self._pick_article(query)
        latency = (datetime.utcnow() - started).total_seconds() * 1000
        return ToolResponse(
            tool_name=self.tool_name,
            status="success",
            data=[TelemetryPayload(
                source_system=self.tool_name,
                timestamp=datetime.utcnow(),
                entity_id=f"search_{article['title'][:30].replace(' ', '_').lower()}",
                metrics={"num_results": len(_FIXTURES["news"]["articles"])},
                contextual_signals={
                    "title": article["title"],
                    "content": article["content"][:500],
                    "source_url": article["url"],
                    "published_date": article["published_date"],
                },
                status="OK",
                confidence=0.75,
                latency_ms=latency,
                raw_data={"results": _FIXTURES["news"]["articles"]},
            )],
            latency_ms=latency,
            confidence=0.75,
            fetched_at=datetime.utcnow(),
        )

    def _pick_article(self, query: str) -> dict:
        q = query.lower()
        for a in _FIXTURES["news"]["articles"]:
            if q in a["title"].lower() or q in a["content"].lower():
                return a
        return random.choice(_FIXTURES["news"]["articles"])

    async def _simulate_behavior(self, scenario: ToolScenario) -> None:
        delay = random.uniform(*scenario.latency_range)
        await asyncio.sleep(delay)
        if scenario.force_status:
            raise _status_to_exception(scenario.force_status)
        if scenario.failure_probability > 0 and random.random() < scenario.failure_probability:
            raise _status_to_exception(scenario.failure_mode)


class SerpApiMock(MockTool):
    tool_name = ToolName.SERPAPI_SEARCH

    async def execute(self, query: str, market: str, scenario: Optional[ToolScenario] = None) -> ToolResponse:
        scenario = scenario or ToolScenario()
        started = datetime.utcnow()
        delay = random.uniform(*scenario.latency_range)
        await asyncio.sleep(delay)
        if scenario.force_status:
            raise _status_to_exception(scenario.force_status)
        if scenario.failure_probability > 0 and random.random() < scenario.failure_probability:
            raise _status_to_exception(scenario.failure_mode)
        product = random.choice(_FIXTURES["ecommerce"]["products"])
        latency = (datetime.utcnow() - started).total_seconds() * 1000
        results = [
            {
                "title": product["title"],
                "snippet": f"Buy {product['title']} at the best price",
                "link": f"https://shop.example.com/{product['title'].lower().replace(' ', '-')}",
                "position": i + 1,
            }
            for i, product in enumerate(_FIXTURES["ecommerce"]["products"][:3])
        ]
        return ToolResponse(
            tool_name=self.tool_name,
            status="success",
            data=[TelemetryPayload(
                source_system=self.tool_name,
                timestamp=datetime.utcnow(),
                entity_id=f"serpapi_{results[0]['title'][:30].replace(' ', '_').lower()}",
                metrics={"num_results": len(results)},
                contextual_signals={
                    "title": results[0]["title"],
                    "snippet": results[0]["snippet"],
                    "source_url": results[0]["link"],
                    "position": results[0]["position"],
                },
                status="OK",
                confidence=0.60,
                latency_ms=latency,
                raw_data={"organic_results": results},
            )],
            latency_ms=latency,
            confidence=0.60,
            fetched_at=datetime.utcnow(),
        )


class CacheMock(MockTool):
    tool_name = ToolName.LOCAL_CACHE

    def __init__(self) -> None:
        self._store: Dict[str, TelemetryPayload] = {}

    def seed(self, key: str, payload: TelemetryPayload) -> None:
        self._store[key] = payload

    async def execute(self, query: str, market: str, scenario: Optional[ToolScenario] = None) -> ToolResponse:
        scenario = scenario or ToolScenario()
        key = f"{market}:{query.lower().strip()}"
        cached = self._store.get(key)
        if cached:
            return ToolResponse(
                tool_name=self.tool_name,
                status="success",
                data=[cached],
                latency_ms=0.0,
                confidence=0.50,
                fetched_at=datetime.utcnow(),
            )
        if scenario.force_status == "error":
            raise _status_to_exception("error")
        return ToolResponse(
            tool_name=self.tool_name,
            status="success",
            data=[],
            latency_ms=0.0,
            confidence=0.50,
            fetched_at=datetime.utcnow(),
        )


class MockToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[ToolName, MockTool] = {
            ToolName.API_FOOTBALL: ApiFootballMock(),
            ToolName.TAVILY_SEARCH: TavilyMock(),
            ToolName.SERPAPI_SEARCH: SerpApiMock(),
            ToolName.LOCAL_CACHE: CacheMock(),
        }

    def register(self, tool: MockTool) -> None:
        self._tools[tool.tool_name] = tool

    def get(self, name: ToolName) -> MockTool:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool not registered: {name}")
        return tool

    def all(self) -> Dict[ToolName, MockTool]:
        return dict(self._tools)

    @property
    def cache(self) -> CacheMock:
        c = self._tools.get(ToolName.LOCAL_CACHE)
        assert isinstance(c, CacheMock)
        return c


def _status_to_exception(mode: FailureMode) -> Exception:
    if mode == "error":
        return RuntimeError("Simulated tool error")
    elif mode == "timeout":
        return TimeoutError("Simulated tool timeout")
    elif mode == "rate_limited":
        return RuntimeError("Simulated rate limit exceeded")
    raise ValueError(f"Unknown failure mode: {mode}")
