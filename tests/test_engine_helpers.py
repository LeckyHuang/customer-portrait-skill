"""测试 engine 层的纯辅助函数（不依赖 LLM / 网络）。"""
import json
from pathlib import Path

from src.engine import (
    DEFAULT_DIMENSIONS,
    _build_mark_done_tool,
    _build_search_tool,
    _format_all_results,
    _format_dim_summary,
    _format_plan,
    _format_results,
    _load_prompt,
    _parse_json,
    _DimState,
)
from src.schemas import SearchResult


def _mk_result(title="t", url="u", snippet="s", query="q", provider="bochaai", date=None):
    return SearchResult(
        title=title, url=url, snippet=snippet, query=query,
        source_provider=provider, published_date=date,
    )


class TestParseJson:
    def test_plain_json(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_strips_code_fence(self):
        text = "```json\n{\"a\": 2}\n```"
        assert _parse_json(text) == {"a": 2}

    def test_strips_bare_code_fence(self):
        text = "```\n{\"a\": 3}\n```"
        assert _parse_json(text) == {"a": 3}

    def test_invalid_raises(self):
        import pytest
        with pytest.raises(json.JSONDecodeError):
            _parse_json("not json at all")


class TestFormatResults:
    def test_empty(self):
        out = _format_results([], "关键词")
        assert "无结果" in out and "关键词" in out

    def test_with_items(self):
        rs = [_mk_result(title="标题A", url="http://a", snippet="摘要A", date="2026-01-01")]
        out = _format_results(rs, "关键词")
        assert "关键词" in out and "标题A" in out and "http://a" in out and "2026-01-01" in out

    def test_snippet_truncated_to_400(self):
        long = "字" * 1000
        rs = [_mk_result(snippet=long)]
        out = _format_results(rs, "q")
        assert "字" * 400 in out
        assert "字" * 401 not in out

    def test_missing_date_omits_parens(self):
        rs = [_mk_result(date=None)]
        out = _format_results(rs, "q")
        assert "（）" not in out


class TestFormatAllResults:
    def test_empty(self):
        assert _format_all_results([]) == "无搜索结果"

    def test_grouped_by_query(self):
        rs = [
            _mk_result(title="A", query="q1"),
            _mk_result(title="B", query="q2"),
            _mk_result(title="C", query="q1"),
        ]
        out = _format_all_results(rs)
        # q1 有两条，q2 一条，且都按 query 分组
        assert out.count("【搜索词：q1】") == 1
        assert out.count("【搜索词：q2】") == 1
        assert "A" in out and "B" in out and "C" in out


class TestFormatDimSummary:
    def test_labels_and_summary(self):
        states = {
            "unit_background": _DimState(status="satisfied", confidence="high", summary="ok"),
            "industry_status": _DimState(status="exhausted", confidence="low"),
            "guest_profile": _DimState(status="pending"),
        }
        out = _format_dim_summary(states)
        assert "✅ 已满足" in out and "⚠️ 已穷举" in out and "⬜ 未完成" in out
        assert "（high）" in out
        assert "ok" in out


class TestBuildTools:
    def test_search_tool_enum_matches_dimensions(self):
        dims = ["unit_background", "industry_status", "guest_profile", "visit_needs"]
        tool = _build_search_tool(dims)
        assert tool["function"]["name"] == "web_search"
        # 维度 enum 必须与传入维度一致，否则 LLM 调用会被拒
        assert tool["function"]["parameters"]["properties"]["dimension"]["enum"] == dims
        assert "query" in tool["function"]["parameters"]["required"]

    def test_mark_done_tool_required_fields(self):
        tool = _build_mark_done_tool(DEFAULT_DIMENSIONS)
        assert tool["function"]["name"] == "mark_dimension_done"
        required = tool["function"]["parameters"]["required"]
        assert set(required) == {"dimension", "confidence", "summary"}
        assert tool["function"]["parameters"]["properties"]["confidence"]["enum"] == [
            "high", "medium", "low"
        ]


class TestFormatPlan:
    def test_empty_queries_returns_summary(self):
        out = _format_plan({"context_summary": "背景X", "queries": []})
        assert out == "背景X"

    def test_no_summary_no_queries_returns_placeholder(self):
        out = _format_plan({"context_summary": "", "queries": []})
        assert "规划阶段未返回" in out

    def test_groups_by_dimension_and_sorts_by_priority(self):
        plan = {
            "context_summary": "调研背景",
            "queries": [
                {"query": "低优先", "dimension": "unit_background", "priority": 5},
                {"query": "高优先", "dimension": "unit_background", "priority": 1},
                {"query": "行业词", "dimension": "industry_status", "priority": 1},
            ],
        }
        out = _format_plan(plan)
        assert "调研背景" in out
        # 同维度内按 priority 升序：高优先 在 低优先 之前
        assert out.index("高优先") < out.index("低优先")


class TestLoadPrompt:
    def test_replaces_placeholders(self, tmp_path):
        p = tmp_path / "tpl.txt"
        p.write_text("Hello {name}, you are {role}", encoding="utf-8")
        out = _load_prompt(str(p), name="Alice", role="admin")
        assert out == "Hello Alice, you are admin"

    def test_missing_placeholder_kept_as_is(self, tmp_path):
        p = tmp_path / "tpl.txt"
        p.write_text("Hi {name}, {missing}", encoding="utf-8")
        out = _load_prompt(str(p), name="Bob")
        assert "Bob" in out and "{missing}" in out
