"""测试 api 层的字段推断逻辑（纯函数，无外部依赖）。"""
import pytest

from src.api import _derive_industry, _derive_visit_needs, PortraitRequest


class TestDeriveIndustry:
    def test_known_mapping(self):
        assert _derive_industry("农业农村专场") == "农业科技"
        assert _derive_industry("金融专场") == "金融服务"
        assert _derive_industry("政务公安专场") == "政务信息化"
        assert _derive_industry("通用场") == "通用"

    def test_unknown_falls_back_to_strip_suffix(self):
        # 未登记的「XX专场」→ 去掉「专场」二字
        assert _derive_industry("未登记专场") == "未登记"

    def test_unknown_no_suffix_kept_as_is(self):
        assert _derive_industry("某新型行业") == "某新型行业"

    def test_empty_string(self):
        assert _derive_industry("") == ""


class TestDeriveVisitNeeds:
    def test_empty_all_returns_default(self):
        req = PortraitRequest(org_name="X", guest_name="Y")
        assert _derive_visit_needs(req) == "参观交流"

    def test_only_domain_specialty(self):
        req = PortraitRequest(org_name="X", guest_name="Y", domain_specialty="农业农村专场")
        assert _derive_visit_needs(req) == "农业农村专场"

    def test_only_reception_goal(self):
        req = PortraitRequest(org_name="X", guest_name="Y", reception_goal="了解产品方案")
        assert _derive_visit_needs(req) == "了解产品方案"

    def test_both_joined_by_chinese_comma(self):
        req = PortraitRequest(
            org_name="X", guest_name="Y",
            domain_specialty="工业专场", reception_goal="考察产线",
        )
        assert _derive_visit_needs(req) == "工业专场，考察产线"

    def test_empty_strings_filtered(self):
        # 空串视为 falsy，被过滤
        req = PortraitRequest(org_name="X", guest_name="Y", domain_specialty="", reception_goal="")
        assert _derive_visit_needs(req) == "参观交流"

    def test_whitespace_strings_kept(self):
        # 当前实现用 `if p` 判真，仅过滤空串；纯空白串仍是 truthy（记录现有行为）
        req = PortraitRequest(org_name="X", guest_name="Y", domain_specialty="  ")
        assert _derive_visit_needs(req) == "  "
