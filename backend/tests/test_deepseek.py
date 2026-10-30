import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.deepseek import DeepSeekClient, DeepSeekError


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("test-key"),
        deepseek_base_url="https://api.deepseek.com",
        deepseek_utility_model="deepseek-flash",
    )


def test_create_plan_sends_current_model_and_validates_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-flash"
        assert payload["reasoning_effort"] == "none"
        assert payload["response_format"] == {"type": "json_object"}
        assert "JSON Schema" in payload["messages"][0]["content"]
        content = json.dumps({"focus": ["业务护城河", "财务质量", "估值与风险"], "selected_groups": []}, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = DeepSeekClient(_settings(), client=http_client)
        plan = client.create_plan("600519", None)

    assert plan.focus == ["业务护城河", "财务质量", "估值与风险"]


def test_create_plan_rejects_empty_focus() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        content = json.dumps({"focus": [], "selected_groups": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = DeepSeekClient(_settings(), client=http_client)
        with pytest.raises(DeepSeekError, match="结构化输出失败"):
            client.create_plan("600519", None)


def test_authentication_error_is_safe_and_actionable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret provider detail"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = DeepSeekClient(_settings(), client=http_client)
        with pytest.raises(DeepSeekError, match="密钥无效") as exc_info:
            client.create_plan("600519", None)

    assert "secret provider detail" not in str(exc_info.value)
