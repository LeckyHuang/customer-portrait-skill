import requests
from .base import SearchAdapter
from ..schemas import SearchResult


class AnsipaiAdapter(SearchAdapter):
    def __init__(self, config: dict):
        self.api_key = config["api_key"]
        self.endpoint = config.get("endpoint", "https://plugin.anspire.cn/api/ntsearch/search")
        self.timeout = config.get("timeout", 15)

    def search(self, query: str, num_results: int = 8) -> list[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        params = {
            "query": query,
            "top_k": str(min(num_results, 50)),
            "search_type": "web",
        }
        try:
            resp = requests.get(
                self.endpoint, params=params, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("results", [])[:num_results]:
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        query=query,
                        source_provider="ansipai",
                        published_date=item.get("publish_time") or item.get("date") or item.get("publishedDate"),
                    )
                )
            return results
        except requests.RequestException as e:
            print(f"[安思派搜索失败] query='{query}' error={e}")
            return []
