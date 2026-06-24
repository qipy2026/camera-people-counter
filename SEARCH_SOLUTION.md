# 百度千帆 AI 搜索方案文档

> 基于百度千帆 AI Search API 的搜索工具方案，可供其他项目快速集成复用。

---

## 1. 方案概述

| 项目 | 说明 |
|------|------|
| **API 端点** | `POST https://qianfan.baidubce.com/v2/ai_search/web_search` |
| **认证方式** | `Authorization: Bearer <token>` |
| **请求格式** | JSON body（chat-style messages） |
| **响应特点** | 返回网页搜索结果 + 来源站点 + 发布时间 |
| **免费额度** | 新用户有每日免费调用量 |
| **Token 获取** | [百度千帆控制台](https://console.bce.baidu.com/iam/#/iam/apikey/list) 创建应用获取 |

---

## 2. 快速开始

### 2.1 安装

```bash
cd search
pip install -e .
```

### 2.2 配置 Token

```bash
# 方式一：环境变量（推荐）
export BAIDU_ACCESS_TOKEN=你的token

# 方式二：.env 文件
echo "BAIDU_ACCESS_TOKEN=你的token" > .env

# 方式三：命令行交互
baidu-search config set-token
```

### 2.3 使用

```bash
# 基本搜索
baidu-search search "关键词"

# 时效性过滤（day / week / month / year）
baidu-search search "热点新闻" -r week

# JSON 输出（适合程序调用）
baidu-search search "关键词" -f json

# 纯文本输出
baidu-search search "关键词" -f simple
```

---

## 3. API 详解

### 3.1 请求格式

```python
import requests
import json

url = "https://qianfan.baidubce.com/v2/ai_search/web_search"

payload = {
    "messages": [
        {"role": "user", "content": "搜索关键词"}
    ],
    "edition": "standard",
    "search_source": "baidu_search_v2",
    "search_recency_filter": "week"   # 可选: day / week / month / year
}

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer <ACCESS_TOKEN>"
}

resp = requests.post(url, json=payload, headers=headers, timeout=30)
data = resp.json()
```

### 3.2 响应格式

```json
{
    "request_id": "91288d8c-...",
    "references": [
        {
            "id": 1,
            "title": "结果标题",
            "url": "https://...",
            "content": "摘要内容...",
            "date": "2026-06-21 00:00:00",
            "website": "来源站点名",
            "type": "web",
            "snippet": "简短摘要"
        }
    ]
}
```

### 3.3 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | array | 是 | 对话消息，`[{"role":"user","content":"..."}]` |
| `edition` | string | 否 | 版本，默认 `standard` |
| `search_source` | string | 否 | 搜索源，默认 `baidu_search_v2` |
| `search_recency_filter` | string | 否 | 时效性: `day` / `week` / `month` / `year` |

---

## 4. 项目结构

```
search/
├── pyproject.toml              # 包配置，entry point: baidu-search
├── config.yaml                 # 默认配置（非敏感项）
├── .env                        # Token 配置（gitignore）
├── .env.example                # .env 模板
├── SEARCH_SOLUTION.md          # 本文档
├── README.md                   # 使用说明
├── src/search/
│   ├── cli.py                  # CLI 入口（Typer）
│   ├── api.py                  # HTTP 客户端 + 响应解析适配
│   ├── config.py               # 配置管理（env > .env > yaml > 默认）
│   ├── models.py               # Pydantic 数据模型
│   ├── formatters.py           # 输出格式化（table / json / simple）
│   └── exceptions.py           # 异常体系（中文错误信息）
└── tests/
    ├── test_api.py              # API 客户端测试（12项）
    ├── test_cli.py              # CLI 集成测试（10项）
    ├── test_config.py           # 配置测试（9项）
    └── test_formatters.py       # 格式化测试（11项）
```

---

## 5. 核心模块设计

### 5.1 配置管理 (`config.py`)

优先级链：**CLI 参数 > 环境变量 > .env 文件 > config.yaml > 默认值**

```python
from search.config import Settings

# 自动加载 .env + 环境变量 + config.yaml
settings = Settings.load()

# CLI token 覆盖
settings = Settings.load(cli_token="xxx")

# 校验
settings.ensure_access_token()  # 未配置时抛 ConfigError
```

### 5.2 API 客户端 (`api.py`)

```python
from search.api import BaiduSearchClient
from search.config import Settings
from search.models import SearchParams

settings = Settings.load()
client = BaiduSearchClient(settings)

# 搜索
params = SearchParams(q="关键词", recency="week")
response = client.search(params)

# response.results   -> list[SingleResult]
# response.total     -> int
# response.query     -> str
```

### 5.3 响应解析（适配层）

`api.py` 中的 `_parse_response()` 是**唯一的响应格式适配点**。如果千帆 API 升级或返回格式变化，只需修改这一个方法：

```python
def _parse_response(self, data: dict, query: str) -> SearchResponse:
    raw_list = data.get("references", [])
    results = [
        SingleResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            abstract=item.get("content") or item.get("snippet", ""),
            time=item.get("date"),
            site_name=item.get("website"),
        )
        for item in raw_list if isinstance(item, dict)
    ]
    return SearchResponse(query=query, total=len(results), results=results)
```

### 5.4 异常体系 (`exceptions.py`)

| 异常类 | 触发条件 | exit_code |
|--------|----------|-----------|
| `ConfigError` | Token 未配置 | 2 |
| `NetworkError` | 网络超时/连接失败 | 3 |
| `AuthError` | Token 无效（401/403） | 4 |
| `APIError` | API 返回错误 | 1 |

---

## 6. 集成到其他项目

### 6.1 作为 Python 库调用

```python
# pip install -e /path/to/search

from search.api import BaiduSearchClient
from search.config import Settings
from search.models import SearchParams

settings = Settings(access_token="xxx")
client = BaiduSearchClient(settings)
result = client.search(SearchParams(q="搜索词", recency="week"))

for r in result.results:
    print(f"[{r.site_name}] {r.title}")
    print(f"  {r.url}")
    print(f"  {r.abstract}\n")
```

### 6.2 作为 CLI 管道调用

```bash
# JSON 输出供 jq 处理
baidu-search search "关键词" -f json | jq '.results[] | {title, url, site_name}'

# 提取所有 URL
baidu-search search "关键词" -f json | jq -r '.results[].url'

# 保存到文件
baidu-search search "关键词" -f json > result.json
```

### 6.3 直接从 Python 调用千帆 API（无依赖）

如果不想引入整个 search 包，可以只用 `requests` 直接调用：

```python
import requests

def baidu_search(query: str, token: str, recency: str = None) -> dict:
    resp = requests.post(
        "https://qianfan.baidubce.com/v2/ai_search/web_search",
        json={
            "messages": [{"role": "user", "content": query}],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            **({"search_recency_filter": recency} if recency else {})
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

# 使用
data = baidu_search("关键词", token="xxx", recency="week")
for ref in data.get("references", []):
    print(ref["title"], ref["url"])
```

---

## 7. Token 格式说明

百度千帆支持两种 Token 格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| **直接 Bearer** | `bce-v3/ALTAK-xxx/xxx` | BCE v3 格式的 Key，直接作为 Bearer Token 使用，无需 OAuth 交换 |
| **OAuth Access Token** | `24.xxx.xxx` | 通过 OAuth 接口用 AK/SK 换取，有效期30天 |

当前方案同时兼容两种格式，配置时直接填入即可。

---

## 8. 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 47项测试
```

---

## 9. 依赖

| 包 | 用途 |
|----|------|
| `requests` | HTTP 请求 |
| `typer` | CLI 框架 |
| `rich` | 彩色表格输出 |
| `pydantic` >= 2.0 | 数据校验 |
| `pydantic-settings` | 配置管理 |
| `pyyaml` | YAML 配置文件解析 |

---

## 10. 已知限制

- 千帆 API 不返回精确的"总结果数"，`total` 为当前返回条数
- 不支持传统分页（无 `pn`/`rn` 参数），单次返回固定数量结果
- 搜索质量依赖千帆索引覆盖范围，特定企业信息可能不全
- 无官方 SLA 保障，适合信息搜集场景，不适合对实时性要求极高的生产环境
