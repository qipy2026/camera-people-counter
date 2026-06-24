"""CLI 集成测试（使用 CliRunner）。"""

import os
from unittest import mock

import pytest
import responses
from typer.testing import CliRunner

from search.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前清除 BAIDU_ 环境变量（覆盖 .env 文件中的值）。"""
    removed = {k: v for k, v in os.environ.items() if k.startswith("BAIDU_")}
    try:
        for k in removed:
            del os.environ[k]
        # 显式置空以覆盖 .env 文件
        os.environ["BAIDU_ACCESS_TOKEN"] = ""
        yield
    finally:
        for k, v in removed.items():
            os.environ[k] = v
        if "BAIDU_ACCESS_TOKEN" in os.environ and os.environ["BAIDU_ACCESS_TOKEN"] == "":
            del os.environ["BAIDU_ACCESS_TOKEN"]


class TestCliHelp:
    """帮助信息测试。"""

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "千帆" in result.stdout

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 2
        assert "千帆" in result.stdout or "千帆" in result.stderr


class TestCliSearch:
    """搜索命令测试。"""

    def test_missing_token(self):
        """未配置 Token 时报错。"""
        result = runner.invoke(app, ["search", "测试"])
        assert result.exit_code == 2
        output = result.stdout + result.stderr
        assert "Access Token" in output

    def test_search_with_token(self):
        """通过 --token 执行搜索。"""
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                json={
                    "request_id": "test-001",
                    "references": [
                        {"id": 1, "title": "结果1", "url": "https://a.com", "content": "摘要1"},
                        {"id": 2, "title": "结果2", "url": "https://b.com", "content": "摘要2"},
                    ],
                },
                status=200,
            )
            result = runner.invoke(app, ["search", "测试", "--token", "test-token"])
            assert result.exit_code == 0
            assert "结果1" in result.stdout

    def test_json_format(self):
        """--format json 输出 JSON。"""
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                json={
                    "request_id": "test-002",
                    "references": [
                        {"id": 1, "title": "JSON结果", "url": "https://x.com", "content": "摘要"}
                    ],
                },
                status=200,
            )
            result = runner.invoke(app, ["search", "测试", "--token", "k", "-f", "json"])
            assert result.exit_code == 0
            assert '"query"' in result.stdout

    def test_invalid_format(self):
        """无效格式报错。"""
        result = runner.invoke(app, ["search", "测试", "--token", "k", "-f", "xml"])
        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "不支持的输出格式" in output

    def test_invalid_recency(self):
        """无效时效性参数报错。"""
        result = runner.invoke(app, ["search", "测试", "--token", "k", "-r", "invalid"])
        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "时效性" in output or "recency" in output

    def test_search_with_recency(self):
        """时效性过滤参数正常。"""
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                json={"request_id": "test-003", "references": []},
                status=200,
            )
            result = runner.invoke(app, ["search", "新闻", "--token", "k", "-r", "week"])
            assert result.exit_code == 0

    def test_search_required_query(self):
        """缺少 query 时报错。"""
        result = runner.invoke(app, ["search"])
        assert result.exit_code == 2


class TestConfigCommands:
    """配置子命令测试。"""

    def test_config_show(self):
        """config show 显示配置。"""
        with mock.patch.dict(os.environ, {"BAIDU_ACCESS_TOKEN": "my-secret-token-1234"}):
            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            assert "千帆" in result.stdout or "API 地址" in result.stdout
            assert "my-s****1234" in result.stdout
