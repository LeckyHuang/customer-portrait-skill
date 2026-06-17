from abc import ABC, abstractmethod
from ..schemas import SearchResult


class SearchAdapter(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 8) -> list[SearchResult]:
        """执行搜索并返回结果列表"""
        pass
