"""Pydantic 数据模型：千帆 AI Search 请求和响应结构。

请求格式（POST JSON）：
{
    "messages": [{"role": "user", "content": "..."}],
    "edition": "standard",
    "search_source": "baidu_search_v2",
    "search_recency_filter": "week"   // 可选: day, week, month, year
}
"""

from pydantic import BaseModel, Field


class Message(BaseModel):
    """对话消息。"""
    role: str = Field(default="user", description="角色: user / assistant")
    content: str = Field(..., min_length=1, description="消息内容")


class SearchRequest(BaseModel):
    """千帆 AI Search 请求体。"""

    messages: list[Message] = Field(..., min_length=1, description="对话消息列表")
    edition: str = Field(default="standard", description="版本")
    search_source: str = Field(default="baidu_search_v2", description="搜索源")
    search_recency_filter: str | None = Field(
        default=None, description="时效性过滤: day, week, month, year"
    )


class SearchParams(BaseModel):
    """CLI 搜索参数（内部使用）。"""

    q: str = Field(..., min_length=1, description="搜索关键词")
    recency: str | None = Field(default=None, description="时效性: day, week, month, year")


class SingleResult(BaseModel):
    """单条搜索结果。"""

    title: str = Field(default="", description="标题")
    url: str = Field(default="", description="链接")
    abstract: str = Field(default="", description="摘要/描述")
    time: str | None = Field(default=None, description="发布时间")
    site_name: str | None = Field(default=None, description="站点名称")


class SearchResponse(BaseModel):
    """搜索响应。"""

    query: str = Field(description="原始搜索词")
    total: int = Field(default=0, ge=0, description="总结果数")
    results: list[SingleResult] = Field(default_factory=list, description="搜索结果列表")
    raw_text: str | None = Field(default=None, description="AI 生成的综合回答（如有）")
