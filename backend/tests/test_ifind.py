import json

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.services.ifind import ALLOWED_TOOLS, IFindClient, default_collection_specs, payload_excerpt, safe_payload
from app.services.analytics import calculate_financial_indicators


def test_collection_plan_stays_inside_allow_list() -> None:
    specs = default_collection_specs("600519", "2026-10-09")
    assert len(specs) == 10
    assert all(tool in ALLOWED_TOOLS[server] for server, tool, _ in specs)
    assert all("600519" in params["query"] for _, _, params in specs)
    notice = next(params for _, tool, params in specs if tool == "search_notice")
    assert notice["time_end"] == "2026-10-09"


def test_safe_payload_redacts_secret_shaped_keys_and_bounds_content() -> None:
    payload = safe_payload({"Authorization": "secret", "visible": "ok", "rows": [{"token": "x", "value": 1}]})
    assert "Authorization" not in payload
    assert payload["visible"] == "ok"
    assert "token" not in payload["rows"][0]
    assert "visible" in payload_excerpt(payload)


def test_numeric_structured_data_can_produce_traceable_calculations() -> None:
    metrics = calculate_financial_indicators(
        [
            ("old", {"data": [{"year": "2024", "revenue": 100, "net_profit": 10}]}),
            ("new", {"data": [{"year": "2025", "revenue": 120, "net_profit": 18, "operating_cash_flow": 20, "total_assets": 200, "total_liabilities": 80}]}),
        ]
    )
    revenue_yoy = next(metric for metric in metrics if metric["metric"] == "营业收入同比")
    assert revenue_yoy["value_percent"] == 20.0
    assert revenue_yoy["source_evidence_ids"] == ["old", "new"]


def test_mcp_handshake_tool_call_and_embedded_json_normalization() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.headers["Authorization"] == "test-key"
        if payload["method"] == "initialize":
            return httpx.Response(200, headers={"Mcp-Session-Id": "session-1"}, json={"result": {}})
        assert request.headers["Mcp-Session-Id"] == "session-1"
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        if payload["method"] == "tools/list":
            return httpx.Response(200, json={"result": {"tools": [{"name": "get_stock_info"}]}})
        if payload["method"] == "tools/call":
            embedded = json.dumps({"code": 1, "msg": "success", "data": {"answer": "600519.SH"}})
            return httpx.Response(
                200,
                json={"result": {"content": [{"type": "text", "text": embedded}]}},
            )
        raise AssertionError(f"未预期的 MCP 请求：{payload}")

    settings = Settings(
        _env_file=None,
        ifind_mcp_api_key=SecretStr("test-key"),
        ifind_max_requests_per_second=20,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = IFindClient(settings, client=http_client)
        result = client.call("stock", "get_stock_info", {"query": "贵州茅台股票代码"})

    assert [call["method"] for call in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    content = result.payload["result"]["content"][0]
    assert "text" not in content
    assert content["data"]["data"]["answer"] == "600519.SH"
