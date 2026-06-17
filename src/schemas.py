from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CustomerInput:
    org_name: str
    industry: str
    guest_name: str
    visit_needs: str


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str
    source_provider: str
    published_date: Optional[str] = None


@dataclass
class PortraitOutput:
    portrait_id: str = ""
    portrait: dict = field(default_factory=dict)
    confidence_assessment: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    queries_executed: list[str] = field(default_factory=list)
    raw_search_results: list[SearchResult] = field(default_factory=list)
    error: Optional[str] = None
