"""测试输出格式化器。"""

import json
import re

from search.formatters import format_rich_table, format_json, format_simple
from search.models import SearchResponse, SingleResult


def strip_ansi(text: str) -> str:
    """移除 ANSI 转义序列。"""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def make_response(query="测试", total=2, results=None, raw_text=None):
    """快速构造 SearchResponse。"""
    if results is None:
        results = [
            SingleResult(
                title="结果1",
                url="https://example.com/1",
                abstract="这是摘要1",
                site_name="站点A",
                time="2024-01-01",
            ),
            SingleResult(
                title="结果2",
                url="https://example.com/2",
                abstract="这是摘要2",
                site_name="站点B",
                time=None,
            ),
        ]
    return SearchResponse(
        query=query,
        total=total,
        results=results,
        raw_text=raw_text,
    )


class TestFormatJson:
    """JSON 格式输出。"""

    def test_valid_json(self):
        resp = make_response()
        data = json.loads(format_json(resp))
        assert data["query"] == "测试"
        assert len(data["results"]) == 2

    def test_json_contains_chinese(self):
        resp = make_response(query="中文搜索")
        output = format_json(resp)
        assert "中文搜索" in output

    def test_empty_results_json(self):
        resp = make_response(results=[])
        data = json.loads(format_json(resp))
        assert data["results"] == []

    def test_raw_text_included(self):
        resp = make_response(raw_text="这是AI生成的回答")
        data = json.loads(format_json(resp))
        assert data["raw_text"] == "这是AI生成的回答"


class TestFormatSimple:
    """纯文本格式输出。"""

    def test_contains_query(self):
        resp = make_response(query="Python")
        output = format_simple(resp)
        assert "Python" in output

    def test_contains_titles(self):
        resp = make_response()
        output = format_simple(resp)
        assert "结果1" in output
        assert "结果2" in output

    def test_contains_site_name(self):
        resp = make_response()
        output = format_simple(resp)
        assert "站点A" in output

    def test_empty_results(self):
        resp = make_response(results=[])
        output = format_simple(resp)
        assert "未找到" in output

    def test_raw_text_displayed(self):
        resp = make_response(raw_text="AI回答的内容")
        output = format_simple(resp)
        assert "AI回答的内容" in output


class TestFormatRichTable:
    """Rich 表格格式输出。"""

    def test_contains_query(self):
        resp = make_response(query="Python")
        output = strip_ansi(format_rich_table(resp))
        assert "Python" in output

    def test_contains_titles(self):
        resp = make_response()
        output = strip_ansi(format_rich_table(resp))
        assert "结果1" in output

    def test_empty_results_message(self):
        resp = make_response(results=[])
        output = strip_ansi(format_rich_table(resp))
        assert "未找到" in output

    def test_site_name_in_table(self):
        resp = make_response()
        output = strip_ansi(format_rich_table(resp))
        assert "站点A" in output

    def test_raw_text_panel(self):
        resp = make_response(raw_text="AI回答示例")
        output = strip_ansi(format_rich_table(resp))
        assert "AI回答示例" in output

    def test_total_count_displayed(self):
        resp = make_response(total=42)
        output = strip_ansi(format_rich_table(resp))
        assert "42" in output
