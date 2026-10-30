"""Small, allow-listed client for the iFinD MCP HTTP endpoint.

The data provider accepts natural-language requests. This module deliberately owns
the endpoint protocol and the permitted request shapes so an LLM can never issue
arbitrary external requests or access the MCP credential.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx
from redis import Redis

from app.core.config import Settings

MCP_BASE = "https://api-mcp.51ifind.com:8643/ds-mcp-servers"
SERVERS = {
    "stock": f"{MCP_BASE}/hexin-ifind-ds-stock-mcp",
    "news": f"{MCP_BASE}/hexin-ifind-ds-news-mcp",
}
ALLOWED_TOOLS = {
    "stock": {
        "get_stock_info",
        "get_stock_financials",
        "get_stock_performance",
        "get_stock_shareholders",
        "get_risk_indicators",
        "get_stock_events",
        "get_esg_data",
        "search_stocks",
    },
    "news": {"search_news", "search_notice"},
}
BLOCKED_KEYS = {"__proto__", "prototype", "constructor", "authorization", "api_key", "token"}


class IFindError(RuntimeError):
    """A safe-to-display iFinD failure; it never includes credentials or payloads."""


@dataclass(frozen=True)
class CollectedPayload:
    server: str
    tool: str
    params: dict[str, Any]
    payload: dict[str, Any]
    from_cache: bool


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_key(payload).encode("utf-8")).hexdigest()


def safe_payload(value: Any, *, depth: int = 0) -> Any:
    """Limit database and prompt size while removing accidental secret-shaped fields."""
    if depth > 8:
        return "[已截断：嵌套过深]"
    if isinstance(value, dict):
        return {
            str(key): safe_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:100]
            if str(key).lower() not in BLOCKED_KEYS
        }
    if isinstance(value, list):
        return [safe_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:20_000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2_000]


def payload_excerpt(payload: dict[str, Any], limit: int = 3_000) -> str:
    rendered = json.dumps(safe_payload(payload), ensure_ascii=False, separators=(",", ":"))
    return rendered[:limit] + ("…" if len(rendered) > limit else "")


def _validate_params(params: dict[str, Any]) -> None:
    if not isinstance(params, dict):
        raise IFindError("iFinD 请求参数必须为对象")

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if str(key).lower() in BLOCKED_KEYS:
                    raise IFindError("iFinD 请求包含禁止字段")
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)
        elif not isinstance(item, (str, int, float, bool, type(None))):
            raise IFindError("iFinD 请求参数类型无效")

    walk(params)


class IFindClient:
    def __init__(
        self,
        settings: Settings,
        redis_client: Redis | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        api_key = settings.secret_value(settings.ifind_mcp_api_key)
        if not api_key:
            raise IFindError("未配置 IFIND_MCP_API_KEY")
        self._api_key = api_key
        self._settings = settings
        self._redis = redis_client
        self._sessions: dict[str, str] = {}
        self._tool_sets: dict[str, set[str]] = {}
        self._request_ids: dict[str, int] = {}
        self._last_request_at = 0.0
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            trust_env=settings.ifind_use_env_proxy,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _next_id(self, server: str) -> int:
        self._request_ids[server] = self._request_ids.get(server, 0) + 1
        return self._request_ids[server]

    def _headers(self, server: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self._api_key,
        }
        if session_id := self._sessions.get(server):
            headers["Mcp-Session-Id"] = session_id
        return headers

    def _rate_limit(self) -> None:
        minimum_interval = 1.0 / self._settings.ifind_max_requests_per_second
        remaining = minimum_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _post(self, server: str, body: dict[str, Any], timeout: float = 60.0) -> tuple[httpx.Response, Any]:
        self._rate_limit()
        try:
            response = self._client.post(SERVERS[server], json=body, headers=self._headers(server), timeout=timeout)
        except httpx.HTTPError as exc:
            raise IFindError("iFinD 网络请求失败") from exc
        try:
            data: Any = response.json() if response.content else {}
        except ValueError:
            data = {"text": response.text[:20_000]}
        return response, data

    def _initialize(self, server: str) -> None:
        if server in self._sessions:
            return
        response, data = self._post(
            server,
            {
                "jsonrpc": "2.0",
                "id": self._next_id(server),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "a-share-research", "version": "0.1.0"},
                },
            },
            timeout=30.0,
        )
        session_id = response.headers.get("Mcp-Session-Id")
        if response.status_code >= 400 or not session_id:
            raise IFindError("iFinD 初始化失败，请检查密钥和服务权限")
        self._sessions[server] = session_id
        # MCP protocol requires this notification after a successful initialize.
        self._post(server, {"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=10.0)

    def list_tools(self, server: str) -> set[str]:
        if server not in SERVERS:
            raise IFindError("不支持的 iFinD 服务")
        if server in self._tool_sets:
            return self._tool_sets[server]
        self._initialize(server)
        response, data = self._post(
            server,
            {"jsonrpc": "2.0", "id": self._next_id(server), "method": "tools/list", "params": {}},
        )
        tools = data.get("result", {}).get("tools", []) if isinstance(data, dict) else []
        if (
            response.status_code >= 400
            or not isinstance(tools, list)
            or (isinstance(data, dict) and data.get("error"))
        ):
            raise IFindError("无法读取 iFinD 工具权限")
        available = {entry.get("name") for entry in tools if isinstance(entry, dict) and entry.get("name")}
        self._tool_sets[server] = available
        return available

    def _cache_key(self, server: str, tool: str, params: dict[str, Any]) -> str:
        digest = payload_hash({"server": server, "tool": tool, "params": params})
        return f"stock-research:ifind:{digest}"

    @staticmethod
    def _normalize_mcp_payload(data: Any) -> dict[str, Any]:
        """Decode JSON embedded in MCP text content while retaining protocol metadata."""
        clean = safe_payload(data)
        if not isinstance(clean, dict):
            return {"data": clean}

        raw_content = data.get("result", {}).get("content", []) if isinstance(data, dict) else []
        clean_content = clean.get("result", {}).get("content", [])
        if isinstance(raw_content, list) and isinstance(clean_content, list):
            for raw_item, clean_item in zip(raw_content, clean_content):
                if not isinstance(raw_item, dict) or not isinstance(clean_item, dict):
                    continue
                text = raw_item.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    parsed = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    continue
                clean_item.pop("text", None)
                clean_item["data"] = safe_payload(parsed)
        return clean

    def call(self, server: str, tool: str, params: dict[str, Any]) -> CollectedPayload:
        if server not in ALLOWED_TOOLS or tool not in ALLOWED_TOOLS[server]:
            raise IFindError("该 iFinD 工具不在研究系统白名单中")
        _validate_params(params)
        if tool not in self.list_tools(server):
            raise IFindError("当前 iFinD 账户没有该工具权限")

        cache_key = self._cache_key(server, tool, params)
        if self._redis:
            try:
                cached = self._redis.get(cache_key)
                if cached:
                    return CollectedPayload(server, tool, params, json.loads(cached), True)
            except Exception:
                # Caching must never prevent source collection.
                pass

        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(server),
            "method": "tools/call",
            "params": {"name": tool, "arguments": params},
        }
        for attempt in range(3):
            response, data = self._post(server, body)
            if response.status_code in {429, 502, 503, 504} and attempt < 2:
                time.sleep(2**attempt)
                continue
            tool_result = data.get("result", {}) if isinstance(data, dict) else {}
            if (
                response.status_code >= 400
                or (isinstance(data, dict) and data.get("error"))
                or (isinstance(tool_result, dict) and tool_result.get("isError") is True)
            ):
                raise IFindError("iFinD 查询失败或被限流")
            clean = self._normalize_mcp_payload(data)
            if self._redis:
                try:
                    self._redis.setex(cache_key, self._settings.ifind_cache_ttl_seconds, _json_key(clean))
                except Exception:
                    pass
            return CollectedPayload(server, tool, params, clean, False)
        raise IFindError("iFinD 查询在重试后仍失败")


def default_collection_specs(symbol: str, as_of: str | None) -> list[tuple[str, str, dict[str, Any]]]:
    date_hint = f"截至{as_of}" if as_of else "截至最新可得日期"
    notice_params: dict[str, Any] = {"query": f"{symbol} 年报、业绩预告、重大合同、投资者关系、风险提示", "size": 10}
    news_params: dict[str, Any] = {"query": f"{symbol} 经营、行业、产品、竞争格局", "size": 10}
    if as_of:
        cutoff = date.fromisoformat(as_of)
        # A historical report must not retrieve notices published after its stated cut-off.
        time_window = {"time_start": (cutoff - timedelta(days=365)).isoformat(), "time_end": cutoff.isoformat()}
        notice_params.update(time_window)
        news_params.update(time_window)
    return [
        ("stock", "get_stock_info", {"query": f"{symbol} 股票代码、股票简称、所属行业、主营业务、上市日期、总市值，{date_hint}"}),
        ("stock", "get_stock_financials", {"query": f"{symbol} 最近5年营业收入、归母净利润、扣非净利润、毛利率、净利率、ROE、经营活动现金流净额、资产负债率，{date_hint}"}),
        ("stock", "get_stock_performance", {"query": f"{symbol} {date_hint}的收盘价、总市值、PE(TTM)、PB、PS(TTM)、近一年涨跌幅"}),
        ("stock", "get_stock_shareholders", {"query": f"{symbol} 最新前十大股东、机构持股比例、流通股占比，{date_hint}"}),
        ("stock", "get_risk_indicators", {"query": f"{symbol} 风险指标、波动率、最大回撤、夏普比率，{date_hint}"}),
        ("stock", "get_stock_events", {"query": f"{symbol} 最近一年重大事件、并购重组、股权融资、股权激励，{date_hint}"}),
        ("stock", "get_esg_data", {"query": f"{symbol} 最新 ESG 评级及关键 ESG 指标，{date_hint}"}),
        (
            "stock",
            "search_stocks",
            {
                "query": f"与{symbol}同一 iFinD 行业且主营业务相近的 A 股上市公司，筛选总市值和盈利规模相近的3至5家可比公司，返回股票代码、简称、所属行业、总市值、PE(TTM)、PB、PS(TTM)，{date_hint}"
            },
        ),
        ("news", "search_notice", notice_params),
        ("news", "search_news", news_params),
    ]
