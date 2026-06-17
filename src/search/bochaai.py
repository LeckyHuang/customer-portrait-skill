import requests
from .base import SearchAdapter
from ..schemas import SearchResult


class BochaaiAdapter(SearchAdapter):
    def __init__(self, config: dict):
        self.api_key = config["api_key"]
        self.endpoint = config.get("endpoint", "https://api.bochaai.com/v1/web-search")
        self.timeout = config.get("timeout", 15)

    def search(self, query: str, num_results: int = 8) -> list[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "count": num_results,
            "freshness": "noLimit",
            "summary": True,
        }
        try:
            resp = requests.post(
                self.endpoint, json=payload, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            # 兼容 bochaai 响应结构
            raw_list = data.get("data", {}).get("webPages", {}).get("value", [])
            if not raw_list:
                raw_list = data.get("results", [])
            for item in raw_list[:num_results]:
                results.append(
                    SearchResult(
                        title=item.get("name", item.get("title", "")),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", item.get("summary", "")),
                        query=query,
                        source_provider="bochaai",
                        published_date=item.get("datePublished") or item.get("dateLastCrawled"),
                    )
                )
            return results
        except requests.RequestException as e:
            # fail-closed：搜索失败返回空列表，由 engine 处理
            print(f"[搜索失败] query='{query}' error={e}")
            return []


def create_search(config: dict) -> SearchAdapter:
    provider = config.get("provider", "bochaai")
    if provider == "bochaai":
        return BochaaiAdapter(config)
    raise ValueError(f"不支持的搜索 provider: {provider}")
