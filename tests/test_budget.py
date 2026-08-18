import pytest

from radar.ai import APIBudgetError, AIClient


def test_api_request_budget_blocks_before_network(monkeypatch):
    client = AIClient({"base_url": "https://example.test/v1", "api_key": "test", "model": "test", "mode": "chat", "max_requests": 1, "requests_per_minute": 10})
    client.request_count = 1
    with pytest.raises(APIBudgetError):
        client._post("chat/completions", {})


def test_rpm_is_hard_capped():
    client = AIClient({"base_url": "https://example.test/v1", "api_key": "test", "model": "test", "requests_per_minute": 65})
    assert client.requests_per_minute == 10
