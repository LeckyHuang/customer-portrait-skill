import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from .schemas import CustomerInput, SearchResult, PortraitOutput
from .llm.openai_compat import OpenAICompatAdapter
from .search.base import SearchAdapter

DEFAULT_DIMENSIONS = ["unit_background", "industry_status", "guest_profile", "visit_needs"]


class CustomerInputValidationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _build_search_tool(dimensions: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "在互联网上搜索信息，获取最新的企业、人物、行业相关资料",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索词，建议中文，贴近真实搜索习惯",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["bochaai", "ansipai"],
                        "description": "搜索引擎：bochaai（博查，综合中文）或 ansipai（安思派，AI增强）",
                    },
                    "dimension": {
                        "type": "string",
                        "enum": dimensions,
                        "description": "本次搜索针对的调研维度，便于系统跟踪进度",
                    },
                },
                "required": ["query"],
            },
        },
    }


def _build_mark_done_tool(dimensions: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "mark_dimension_done",
            "description": "当某个调研维度已采集到足够清晰的信息时，调用此工具标记完成",
            "parameters": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": dimensions,
                        "description": "要标记完成的维度",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "信息可信度",
                    },
                    "summary": {
                        "type": "string",
                        "description": "已获取的关键信息摘要（1-2句），信息不足时说明原因",
                    },
                },
                "required": ["dimension", "confidence", "summary"],
            },
        },
    }


@dataclass
class _DimState:
    status: str = "pending"   # pending | satisfied | exhausted
    confidence: str = ""
    summary: str = ""


def _load_prompt(path: str, **kwargs) -> str:
    text = Path(path).read_text(encoding="utf-8")
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _format_results(results: list[SearchResult], query: str) -> str:
    if not results:
        return f"搜索「{query}」无结果"
    lines = [f"搜索词：{query}，共 {len(results)} 条结果\n"]
    for i, r in enumerate(results, 1):
        date_str = f"（{r.published_date}）" if r.published_date else ""
        lines.append(f"{i}. 【{r.title}】{date_str}\n   URL: {r.url}\n   摘要: {r.snippet[:400]}\n")
    return "\n".join(lines)


def _format_all_results(results: list[SearchResult]) -> str:
    if not results:
        return "无搜索结果"
    by_query: dict[str, list[SearchResult]] = defaultdict(list)
    for r in results:
        by_query[r.query].append(r)
    lines = []
    for query, items in by_query.items():
        lines.append(f"\n【搜索词：{query}】")
        for i, r in enumerate(items, 1):
            date_str = f"（{r.published_date}）" if r.published_date else ""
            lines.append(f"{i}. [{r.source_provider}] {r.title}{date_str}")
            lines.append(f"   {r.url}")
            lines.append(f"   {r.snippet[:350]}")
    return "\n".join(lines)


def _format_dim_summary(dim_states: dict[str, _DimState]) -> str:
    status_labels = {"satisfied": "✅ 已满足", "exhausted": "⚠️ 已穷举", "pending": "⬜ 未完成"}
    lines = ["\n\n【维度采集状态】"]
    for dim, state in dim_states.items():
        label = status_labels.get(state.status, state.status)
        conf = f"（{state.confidence}）" if state.confidence else ""
        lines.append(f"- {dim}: {label}{conf}")
        if state.summary:
            lines.append(f"  {state.summary}")
    return "\n".join(lines)


def _format_plan(plan: dict) -> str:
    summary = plan.get("context_summary", "")
    queries = plan.get("queries", [])
    if not queries:
        return summary or "（规划阶段未返回有效数据，请自行制定搜索策略）"

    by_dim: dict[str, list[dict]] = defaultdict(list)
    for q in queries:
        by_dim[q.get("dimension", "other")].append(q)

    dim_labels = {
        "unit_background": "单位背景",
        "industry_status": "行业地位",
        "guest_profile": "主宾背景",
        "visit_needs": "来访动机",
    }
    lines = []
    if summary:
        lines.append(f"调研背景：{summary}\n")
    lines.append("建议初始搜索词（可根据结果灵活调整）：")
    # Iterate in insertion order; unknown dimensions fall to "other" bucket at end
    seen_dims = list(by_dim.keys())
    for dim in seen_dims:
        items = by_dim.get(dim, [])
        if not items:
            continue
        lines.append(f"\n[{dim_labels.get(dim, dim)}]")
        for q in sorted(items, key=lambda x: x.get("priority", 9)):
            rationale = q.get("rationale", "")
            lines.append(f'  • "{q["query"]}"' + (f"（{rationale}）" if rationale else ""))
    return "\n".join(lines)


class PortraitEngine:
    def __init__(self, config: dict, llm: OpenAICompatAdapter, searchers: dict[str, SearchAdapter]):
        self.config = config
        self.llm = llm
        self.searchers = searchers
        engine_cfg = config.get("engine", {})
        self.max_queries = engine_cfg.get("max_queries_total", 15)
        self.novelty_stale_rounds = engine_cfg.get("novelty_stale_rounds", 2)
        self.results_per_query = config.get("search", {}).get("results_per_query", 8)
        prompts_cfg = config.get("prompts", {})
        self.validate_prompt_path = prompts_cfg.get("validate", "prompts/validate.txt")
        self.planning_prompt_path = prompts_cfg.get("planning", "prompts/keyword_extraction.txt")
        self.research_prompt_path = prompts_cfg.get("research_loop", "prompts/portrait.txt")
        self.synthesis_prompt_path = prompts_cfg.get("synthesis", "prompts/portrait_synthesis.txt")
        self.default_provider = list(searchers.keys())[0]
        self.dimensions: list[str] = engine_cfg.get("dimensions", DEFAULT_DIMENSIONS)
        if not self.dimensions:
            raise ValueError("engine.dimensions 不能为空，请在 config.yaml 中配置至少一个维度")
        self._tools = [_build_search_tool(self.dimensions), _build_mark_done_tool(self.dimensions)]
        self.fallback_sparse_threshold: int = engine_cfg.get("fallback_sparse_threshold", 3)
        self.research_loop_max_tokens: int = engine_cfg.get("research_loop_max_tokens", 1024)
        self.synthesis_enable_search: bool = engine_cfg.get("synthesis_enable_search", False)
        self.synthesis_model: str | None = config.get("llm", {}).get("synthesis_model")
        self._tlocal = threading.local()

    def _log(self, msg: str) -> None:
        fn = getattr(self._tlocal, "log_fn", None) or print
        fn(msg)

    def run(self, customer: CustomerInput, log_fn=None) -> PortraitOutput:
        self._tlocal.log_fn = log_fn or print
        # Stage 0: Validate input
        self._log("[阶段0] 验证输入信息...")
        self._validate(customer)

        # Stage 1: Planning — generate structured research plan with initial queries
        self._log("[阶段1] 生成调研规划...")
        plan = self._plan(customer)
        query_count = len(plan.get("queries", []))
        self._log(f"  规划完成：{query_count} 个初始搜索词")
        if plan.get("context_summary"):
            self._log(f"  背景判断：{plan['context_summary'][:80]}")

        # Stage 2: Research — parallel search
        self._log("[阶段2] 开始多维并行搜索...")
        dim_states, all_results, queries_executed = self._research(customer, plan)

        satisfied = sum(1 for s in dim_states.values() if s.status == "satisfied")
        exhausted = sum(1 for s in dim_states.values() if s.status == "exhausted")
        self._log(f"  调研结束：{len(queries_executed)} 次搜索，{satisfied} 个维度满足，{exhausted} 个维度穷举")

        # Stage 3: Synthesis — generate portrait from accumulated results
        self._log("[阶段3] 合成客户画像...")
        return self._synthesize(customer, dim_states, all_results, queries_executed)

    # ------------------------------------------------------------------ #
    # Stage 0: Input validation                                            #
    # ------------------------------------------------------------------ #

    def _validate(self, customer: CustomerInput) -> None:
        prompt = _load_prompt(
            self.validate_prompt_path,
            org_name=customer.org_name,
            industry=customer.industry,
            guest_name=customer.guest_name,
            visit_needs=customer.visit_needs,
        )
        try:
            response = self.llm.chat([{"role": "user", "content": prompt}])
            data = _parse_json(response)
            if not data.get("valid", True):
                reason = data.get("reason", "输入信息不符合要求，请检查后重试")
                self._log(f"  [验证失败] {reason}")
                raise CustomerInputValidationError(reason)
            self._log("  验证通过")
        except CustomerInputValidationError:
            raise
        except Exception as e:
            self._log(f"  [验证] 解析异常（{e}），跳过验证继续")

    # ------------------------------------------------------------------ #
    # Stage 1: Planning                                                    #
    # ------------------------------------------------------------------ #

    def _plan(self, customer: CustomerInput) -> dict:
        prompt = _load_prompt(
            self.planning_prompt_path,
            org_name=customer.org_name,
            industry=customer.industry,
            guest_name=customer.guest_name,
            visit_needs=customer.visit_needs,
            client_type=customer.client_type or "未知",
            guest_title=customer.guest_title or "未知",
            visit_category=customer.visit_category or "未知",
            reception_goal=customer.reception_goal or "未填写",
            client_intro=customer.client_intro or "未填写",
            domain_specialty_str=customer.domain_specialty or "未指定",
        )
        try:
            response = self.llm.chat([{"role": "user", "content": prompt}])
            return _parse_json(response)
        except Exception as e:
            self._log(f"  [规划阶段] 解析失败（{e}），使用空规划继续")
            return {"queries": [], "context_summary": ""}

    # ------------------------------------------------------------------ #
    # Stage 2: Research loop                                               #
    # ------------------------------------------------------------------ #

    def _search_with_fallback(
        self, query: str, provider: str, dimension: str
    ) -> tuple[list[SearchResult], str]:
        """执行搜索；若主引擎结果稀少（< fallback_sparse_threshold），
        自动用备用引擎补充并合并去重，不额外消耗搜索次数。
        返回 (results, actual_providers_used)。
        """
        actual = provider if provider in self.searchers else self.default_provider
        primary_results = self.searchers[actual].search(query, self.results_per_query)
        providers_used = actual

        if len(primary_results) < self.fallback_sparse_threshold and len(self.searchers) > 1:
            alt = next((p for p in self.searchers if p != actual), None)
            if alt:
                alt_results = self.searchers[alt].search(query, self.results_per_query)
                seen = {r.url for r in primary_results}
                new = [r for r in alt_results if r.url not in seen]
                if new:
                    primary_results = primary_results + new
                    dim_tag = f"[{dimension}] " if dimension else ""
                    self._log(
                        f"  {dim_tag}[稀疏补充] {actual}({len(primary_results)-len(new)}条)"
                        f" + {alt}({len(new)}条新URL)"
                    )
                    providers_used = f"{actual}+{alt}"

        return primary_results, providers_used

    # 维度-搜索引擎亲和映射：bochaai 擅长企业/行业资讯，ansipai 擅长人物/需求分析
    _DIM_PROVIDER: dict[str, str] = {
        "unit_background": "bochaai",
        "industry_status": "bochaai",
        "guest_profile":   "ansipai",
        "visit_needs":     "ansipai",
    }

    def _research(
        self, customer: CustomerInput, plan: dict
    ) -> tuple[dict[str, _DimState], list[SearchResult], list[str]]:
        from concurrent.futures import ThreadPoolExecutor, as_completed as futures_as_completed

        # 捕获当前线程的 log_fn，供工作线程闭包使用
        log = getattr(self._tlocal, "log_fn", None) or print

        queries = plan.get("queries", [])

        # 若规划阶段未返回查询词，生成兜底查询
        if not queries:
            queries = [
                {"query": f"{customer.org_name} 机构介绍 背景", "dimension": "unit_background"},
                {"query": f"{customer.org_name} {customer.industry} 行业地位", "dimension": "industry_status"},
                {"query": f"{customer.guest_name} {customer.org_name} 职务", "dimension": "guest_profile"},
                {"query": f"{customer.org_name} {customer.visit_needs[:30]}", "dimension": "visit_needs"},
            ]

        # 按维度亲和映射分配搜索引擎（规划阶段 prompt 不输出 provider，这里补充）
        for q in queries:
            if not q.get("provider"):
                dim = q.get("dimension", "")
                preferred = self._DIM_PROVIDER.get(dim, self.default_provider)
                q["provider"] = preferred if preferred in self.searchers else self.default_provider

        queries = queries[:self.max_queries]
        log(f"  并行执行 {len(queries)} 个搜索（双源亲和分配）...")

        all_results: list[SearchResult] = []
        queries_executed: list[str] = []

        def do_search(q: dict) -> tuple[list[SearchResult], str]:
            query_text = q.get("query", "").strip()
            provider = q.get("provider", self.default_provider)
            dimension = q.get("dimension", "")
            if not query_text:
                return [], ""
            results, providers_used = self._search_with_fallback(query_text, provider, dimension)
            log(f"  [{dimension}] [{providers_used}] {query_text} -> {len(results)} 条")
            return results, query_text

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {executor.submit(do_search, q): q for q in queries}
            for future in futures_as_completed(future_map, timeout=60):
                try:
                    results, query_text = future.result()
                    if query_text:
                        all_results.extend(results)
                        queries_executed.append(query_text)
                except Exception as e:
                    q = future_map[future]
                    log(f"  [搜索失败] {q.get('query', '')} - {e}")

        # 按维度汇总状态
        dim_counts: dict[str, int] = defaultdict(int)
        searched_dims = {q.get("dimension", "") for q in queries if q.get("dimension")}
        for q in queries:
            dim = q.get("dimension", "")
            if dim:
                count = sum(1 for r in all_results if r.query == q.get("query", ""))
                dim_counts[dim] += count

        dim_states: dict[str, _DimState] = {}
        for dim in self.dimensions:
            if dim in searched_dims:
                count = dim_counts.get(dim, 0)
                dim_states[dim] = _DimState(
                    status="satisfied" if count > 0 else "exhausted",
                    confidence="medium" if count >= 3 else "low",
                    summary=f"搜索到 {count} 条结果",
                )
            else:
                dim_states[dim] = _DimState(status="exhausted", confidence="low", summary="未覆盖此维度")

        return dim_states, all_results, queries_executed

    # ------------------------------------------------------------------ #
    # Stage 3: Synthesis                                                   #
    # ------------------------------------------------------------------ #

    def _synthesize(
        self,
        customer: CustomerInput,
        dim_states: dict[str, _DimState],
        all_results: list[SearchResult],
        queries_executed: list[str],
    ) -> PortraitOutput:
        search_results_text = _format_all_results(all_results) + _format_dim_summary(dim_states)

        prompt = _load_prompt(
            self.synthesis_prompt_path,
            org_name=customer.org_name,
            industry=customer.industry,
            guest_name=customer.guest_name,
            visit_needs=customer.visit_needs,
            search_results=search_results_text,
            client_type=customer.client_type or "未知",
            guest_title=customer.guest_title or "未知",
            visit_category=customer.visit_category or "未知",
            reception_goal=customer.reception_goal or "未填写",
            client_intro=customer.client_intro or "未填写",
            domain_specialty_str=customer.domain_specialty or "未指定",
        )

        chat_kwargs: dict = {"enable_search": self.synthesis_enable_search}
        if self.synthesis_model:
            chat_kwargs["model"] = self.synthesis_model
            self._log(f"  使用快速模型 {self.synthesis_model} 合成...")
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                **chat_kwargs,
            )
        except Exception as e:
            return PortraitOutput(
                portrait={},
                confidence_assessment={"overall": "low"},
                sources=[],
                queries_executed=queries_executed,
                raw_search_results=all_results,
                error=f"合成阶段 LLM 调用失败: {e}",
            )
        return self._parse_output(response, queries_executed, all_results)

    # ------------------------------------------------------------------ #
    # Output parsing                                                       #
    # ------------------------------------------------------------------ #

    def _parse_output(
        self, text: str, queries_executed: list[str], all_results: list[SearchResult]
    ) -> PortraitOutput:
        try:
            data = _parse_json(text)
            data["queries_executed"] = queries_executed
            return PortraitOutput(
                portrait=data.get("portrait", {}),
                confidence_assessment=data.get("confidence_assessment", {}),
                sources=data.get("sources", []),
                queries_executed=queries_executed,
                raw_search_results=all_results,
            )
        except (json.JSONDecodeError, ValueError) as e:
            return PortraitOutput(
                portrait={},
                confidence_assessment={"overall": "low"},
                sources=[],
                queries_executed=queries_executed,
                raw_search_results=all_results,
                error=f"输出解析失败: {e}\n原始内容（前800字）:\n{text[:800]}",
            )
