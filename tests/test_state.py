"""测试 state.py 中的数据结构。"""

import pytest
from state import AnalyzerOutput


class TestAnalyzerOutput:
    """AnalyzerOutput Pydantic 模型测试。"""

    def test_valid_output_all_fields(self):
        output = AnalyzerOutput(
            core_claim="贫富差距过大是不公平的",
            underlying_assumption="公平意味着结果平等",
            matched_philosophy="分配正义",
        )
        assert output.core_claim == "贫富差距过大是不公平的"
        assert output.underlying_assumption == "公平意味着结果平等"
        assert output.matched_philosophy == "分配正义"

    def test_philosophy_category_must_be_valid(self):
        with pytest.raises(ValueError):
            AnalyzerOutput(
                core_claim="x",
                underlying_assumption="y",
                matched_philosophy="不存在主义",
            )

    def test_model_serializes_to_dict(self):
        output = AnalyzerOutput(
            core_claim="c",
            underlying_assumption="a",
            matched_philosophy="未知",
        )
        d = output.model_dump()
        assert d == {
            "core_claim": "c",
            "underlying_assumption": "a",
            "matched_philosophy": "未知",
        }
