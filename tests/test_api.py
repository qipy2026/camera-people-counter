"""测试千帆 AI Search API 客户端。"""

import pytest
import responses
import requests

from search.api import BaiduSearchClient
from search.config import Settings
from search.exceptions import NetworkError, APIError, AuthError
from search.models import SearchParams


@pytest.fixture
def settings():
    return Settings(
        access_token="test-token",
        api_url="https://qianfan.baidubce.com/v2/ai_search/web_search",
        timeout=5,
    )


@pytest.fixture
def client(settings):
    return BaiduSearchClient(settings)


class TestBaiduSearchClient:
    """千帆 API 客户端单元测试。"""

    def test_successful_search(self, client, mock_qianfan_success):
        """正常搜索返回 SearchResponse。"""
        params = SearchParams(q="Python")
        response = client.search(params)

        assert response.query == "Python"
        assert response.total == 2
        assert len(response.results) == 2
        assert response.results[0].title == "Python 官方文档"
        assert response.results[0].site_name == "Python.org"
        assert response.results[0].time == "2024-01-15"
        assert response.total == 2

    def test_search_with_recency(self, client, mock_qianfan_success):
        """带时效性过滤的搜索。"""
        params = SearchParams(q="新闻", recency="week")
        response = client.search(params)
        assert response.query == "新闻"

    def test_empty_results(self, client, mock_qianfan_empty):
        """空结果集。"""
        params = SearchParams(q="xyz不存在的词")
        response = client.search(params)
        assert response.total == 0
        assert len(response.results) == 0

    def test_api_error_code(self, client, mock_qianfan_error):
        """API 返回非0错误码。"""
        with pytest.raises(APIError, match="unknown"):
            client.search(SearchParams(q="test"))

    def test_timeout_error(self, client):
        """请求超时。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                body=requests.Timeout(),
            )
            with pytest.raises(NetworkError, match="超时"):
                client.search(SearchParams(q="test"))

    def test_connection_error(self, client):
        """连接失败。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                body=requests.ConnectionError(),
            )
            with pytest.raises(NetworkError, match="网络连接"):
                client.search(SearchParams(q="test"))

    def test_http_401(self, client):
        """401 返回 AuthError。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                status=401,
            )
            with pytest.raises(AuthError, match="Access Token"):
                client.search(SearchParams(q="test"))

    def test_http_403(self, client):
        """403 也返回 AuthError。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                status=403,
            )
            with pytest.raises(AuthError):
                client.search(SearchParams(q="test"))

    def test_http_500(self, client):
        """500 返回 APIError。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                status=500,
            )
            with pytest.raises(APIError, match="500"):
                client.search(SearchParams(q="test"))

    def test_malformed_json(self, client):
        """无效 JSON 返回 APIError。"""
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://qianfan.baidubce.com/v2/ai_search/web_search",
                body="not json",
                status=200,
            )
            with pytest.raises(APIError, match="无法解析"):
                client.search(SearchParams(q="test"))

    def test_bearer_token_in_header(self, client, mock_qianfan_success):
        """验证请求头包含 Bearer Token。"""
        client.search(SearchParams(q="test"))
        req = mock_qianfan_success.calls[0].request
        assert req.headers["Authorization"] == "Bearer test-token"
        assert req.headers["Content-Type"] == "application/json"

    def test_request_body_structure(self, client, mock_qianfan_success):
        """验证请求体结构正确。"""
        client.search(SearchParams(q="测试搜索", recency="week"))
        body = mock_qianfan_success.calls[0].request.body
        # 确认包含 messages
        assert b'"messages"' in body
        assert b'"user"' in body
        assert b'"content"' in body
        assert b'"search_recency_filter"' in body
        assert b'"week"' in body
