"""共享测试夹具。"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import responses

from search.models import SearchResponse, SingleResult


@pytest.fixture
def mock_token():
    """临时设置 BAIDU_ACCESS_TOKEN 环境变量。"""
    with mock.patch.dict(os.environ, {"BAIDU_ACCESS_TOKEN": "test-token-12345678"}):
        yield


@pytest.fixture
def sample_results():
    """构造示例搜索结果。"""
    return [
        SingleResult(
            title="Python 官方文档",
            url="https://docs.python.org/zh-cn/3/",
            abstract="Python 编程语言的官方文档，包含教程、库参考和语言参考。",
            site_name="Python.org",
            time="2024-01-15",
        ),
        SingleResult(
            title="Python 教程 | 菜鸟教程",
            url="https://www.runoob.com/python/",
            abstract="Python 基础教程，适合初学者入门。",
            site_name="菜鸟教程",
            time="2024-06-20",
        ),
    ]


@pytest.fixture
def sample_response(sample_results):
    """构造完整的 SearchResponse。"""
    return SearchResponse(
        query="Python",
        total=2,
        results=sample_results,
    )


@pytest.fixture
def mock_qianfan_success(sample_results):
    """mock 千帆 AI Search 成功响应（匹配真实 API 格式）。"""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            json={
                "request_id": "test-req-001",
                "references": [
                    {
                        "id": i + 1,
                        "title": r.title,
                        "url": r.url,
                        "content": r.abstract,
                        "date": r.time,
                        "website": r.site_name,
                        "type": "web",
                        "snippet": r.abstract,
                    }
                    for i, r in enumerate(sample_results)
                ],
            },
            status=200,
        )
        yield rsps


@pytest.fixture
def mock_qianfan_error():
    """mock 千帆 API 错误响应。"""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            json={"error": "invalid_client", "error_description": "unknown client id"},
            status=200,
        )
        yield rsps


@pytest.fixture
def mock_qianfan_empty():
    """mock 千帆 API 空结果响应。"""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            json={
                "request_id": "test-empty",
                "references": [],
            },
            status=200,
        )
        yield rsps


@pytest.fixture
def temp_config_dir():
    """创建临时目录用于测试配置文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
