"""自定义异常体系，提供精确的中文错误信息。"""


class SearchError(Exception):
    """所有搜索工具异常的基础类。"""
    exit_code = 1


class ConfigError(SearchError):
    """配置缺失或无效时抛出（如未设置 API Key）。"""
    exit_code = 2


class NetworkError(SearchError):
    """网络连接失败、DNS 解析失败或请求超时时抛出。"""
    exit_code = 3


class APIError(SearchError):
    """百度 API 返回非成功状态码时抛出。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AuthError(APIError):
    """API Key 无效或过期时抛出（401/403）。"""
    exit_code = 4
