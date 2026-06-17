from .bochaai import BochaaiAdapter
from .ansipai import AnsipaiAdapter
from .base import SearchAdapter


def create_searchers(search_config: dict) -> dict[str, SearchAdapter]:
    """根据配置创建所有可用的搜索适配器，返回 {provider_name: adapter}"""
    searchers = {}
    providers = search_config.get("providers", {})

    if "bochaai" in providers and providers["bochaai"].get("api_key"):
        searchers["bochaai"] = BochaaiAdapter(providers["bochaai"])

    if "ansipai" in providers and providers["ansipai"].get("api_key"):
        searchers["ansipai"] = AnsipaiAdapter(providers["ansipai"])

    if not searchers:
        raise ValueError("配置中没有可用的搜索引擎，请检查 search.providers 配置")

    return searchers


__all__ = ["create_searchers", "BochaaiAdapter", "AnsipaiAdapter", "SearchAdapter"]
