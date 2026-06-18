"""测试 Bochaai 搜索 adapter 的响应解析（mock HTTP，不发真实请求）。"""
import pytest

from src.search import bochaai as bochaai_mod
from src.search.bochaai import BochaaiAdapter


class _FakeResponse:
    def __init__(self, payload, *, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def adapter():
    return BochaaiAdapter({"api_key": "fake-key", "endpoint": "http://mock/search"})


def test_parse_nested_webpages_shape(monkeypatch, adapter):
    payload = {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "标题A", "url": "http://a",
                        "snippet": "摘要A", "datePublished": "2026-01-01",
                    },
                    {
                        "name": "标题B", "url": "http://b",
                        "summary": "摘要B(走summary字段)",
                    },
                ]
            }
        }
    }
    monkeypatch.setattr(bochaai_mod.requests, "post",
                        lambda *a, **k: _FakeResponse(payload))
    results = adapter.search("测试", num_results=5)
    assert len(results) == 2
    r0, r1 = results
    assert r0.title == "标题A" and r0.url == "http://a" and r0.source_provider == "bochaai"
    assert r0.published_date == "2026-01-01"
    # 缺 snippet 时应回退到 summary 字段
    assert r1.snippet == "摘要B(走summary字段)"
    # query 与 provider 透传
    assert all(r.query == "测试" for r in results)


def test_parse_flat_results_fallback(monkeypatch, adapter):
    payload = {"results": [
        {"title": "T", "url": "http://x", "snippet": "S"},
    ]}
    monkeypatch.setattr(bochaai_mod.requests, "post",
                        lambda *a, **k: _FakeResponse(payload))
    results = adapter.search("q")
    assert len(results) == 1
    assert results[0].title == "T"


def test_empty_payload_returns_empty(monkeypatch, adapter):
    monkeypatch.setattr(bochaai_mod.requests, "post",
                        lambda *a, **k: _FakeResponse({}))
    assert adapter.search("q") == []


def test_fail_closed_on_network_error(monkeypatch, adapter):
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(bochaai_mod.requests, "post", _raise)
    # fail-closed：网络异常必须返回空列表，不向上抛
    assert adapter.search("q") == []


def test_respects_num_results_cap(monkeypatch, adapter):
    payload = {"data": {"webPages": {"value": [
        {"name": f"n{i}", "url": f"http://{i}", "snippet": "s"} for i in range(20)
    ]}}}
    monkeypatch.setattr(bochaai_mod.requests, "post",
                        lambda *a, **k: _FakeResponse(payload))
    results = adapter.search("q", num_results=3)
    assert len(results) == 3
