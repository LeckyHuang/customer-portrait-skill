from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CustomerInput:
    org_name: str
    guest_name: str
    # 以下字段可选：中控邀约系统不采集，留空时由引擎从 domain_specialty 等字段推断
    industry: str = ""               # 所属行业
    visit_needs: str = ""            # 参观目的说明
    # 以下字段来自中控邀约登记，Optional 保持向后兼容
    client_type: str = ""            # 客户属性：政府/部队/企业/媒体/外宾/合作伙伴/内部/其他
    guest_title: str = ""            # 主宾职务，如"副所长"
    visit_category: str = ""         # 参观类别：领导参观型/高层拜访型/营销发展型/客户签约型/…
    reception_goal: str = ""         # 本次接待营销目标和目的
    client_intro: str = ""           # 客户基本信息（填单人手工描述）
    domain_specialty: str = ""  # 参观需求/专场，单选


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
