"""百度千帆 AI Search API 客户端。

封装 HTTP 调用、响应解析和错误处理。
使用 POST + Bearer Token 认证，JSON body 传参。

千帆 AI Search 接口：
    POST https://qianfan.baidubce.com/v2/ai_search/web_search
    Authorization: Bearer <access_token>
    Content-Type: application/json

响应格式适配集中在 _parse_response() 方法中。
"""

import requests

from search.config import Settings
from search.models import (
    SearchRequest,
    SearchResponse,
    SearchParams,
    SingleResult,
    Message,
)
from search.exceptions import NetworkError, APIError, AuthError


class BaiduSearchClient:
    """百度千帆 AI Search HTTP 客户端。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "baidu-search-cli/0.2.0",
                "Authorization": f"Bearer {settings.access_token}",
            }
        )

    def search(self, params: SearchParams) -> SearchResponse:
        """执行搜索请求。

        Args:
            params: 搜索参数（关键词、时效性过滤等）。

        Returns:
            SearchResponse: 规范化的搜索结果。

        Raises:
            NetworkError: 网络连接失败或超时。
            AuthError: Access Token 无效。
            APIError: API 返回错误。
        """
        # 构建请求体
        body = SearchRequest(
            messages=[Message(role="user", content=params.q)],
            edition=self.settings.edition,
            search_source=self.settings.search_source,
            search_recency_filter=params.recency,
        )

        try:
            resp = self.session.post(
                self.settings.api_url,
                json=body.model_dump(exclude_none=True),
                timeout=self.settings.timeout,
            )
        except requests.Timeout:
            raise NetworkError(
                f"请求超时（{self.settings.timeout}秒），请检查网络或稍后重试。"
            )
        except requests.ConnectionError:
            raise NetworkError(
                "无法连接到千帆 AI Search API，请检查网络连接。"
            )

        # 认证错误
        if resp.status_code in (401, 403):
            raise AuthError(
                "Access Token 无效或已过期，请检查后重试。",
                status_code=resp.status_code,
            )

        # 其他 HTTP 错误
        if resp.status_code != 200:
            raise APIError(
                f"API 返回错误状态码: {resp.status_code}",
                status_code=resp.status_code,
            )

        # 解析 JSON
        try:
            data = resp.json()
        except ValueError:
            raise APIError("API 返回了无法解析的数据。")

        return self._parse_response(data, params.q)

    def _parse_response(
        self,
        data: dict,
        query: str,
    ) -> SearchResponse:
        """将千帆 AI Search 原始 JSON 转换为 SearchResponse。

        实际返回格式：
        {
            "request_id": "...",
            "references": [
                {
                    "id": 1,
                    "url": "...",
                    "title": "...",
                    "date": "2026-06-21 00:00:00",
                    "content": "...",
                    "icon": "...",
                    "website": "中国青年网",
                    "type": "web",
                    "snippet": "..."
                }
            ]
        }
        """
        # 检查错误响应
        if "error" in data or "error_code" in data:
            msg = data.get("error_description", data.get("error_msg", "未知错误"))
            raise APIError(f"API 返回错误: {msg}")

        # references 是顶层字段
        raw_list = data.get("references", [])
        if not isinstance(raw_list, list):
            raw_list = []

        results = []
        for item in raw_list:
            if isinstance(item, dict):
                results.append(
                    SingleResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        abstract=item.get("content") or item.get("snippet", ""),
                        time=item.get("date"),
                        site_name=item.get("website"),
                    )
                )

        return SearchResponse(
            query=query,
            total=len(results),
            results=results,
            raw_text=None,
        )
