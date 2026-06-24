# 百度千帆 AI 搜索 CLI 工具

基于 [百度千帆 AI Search API](https://qianfan.baidubce.com/v2/ai_search/web_search) 的命令行搜索工具。

支持 AI 增强搜索、时效性过滤、结构化结果展示。

## 安装

```bash
pip install -e .
```

## 获取 Access Token

1. 访问 [百度千帆控制台](https://console.bce.baidu.com/iam/#/iam/apikey/list)
2. 注册/登录 → 实名认证 → 创建应用
3. 获取 **Access Token**（用于 Bearer 认证）

> 接口文档参考：[千帆 AI Search](https://cloud.baidu.com/doc/AppSearch/s/blw8b0ujn)

## 配置 Token

三种方式任选其一：

**方式一：命令行参数（单次使用）**

```bash
baidu-search search "搜索词" --token YOUR_ACCESS_TOKEN
```

**方式二：环境变量（推荐）**

```bash
export BAIDU_ACCESS_TOKEN=YOUR_ACCESS_TOKEN
baidu-search search "搜索词"
```

**方式三：.env 文件**

```bash
cp .env.example .env
# 编辑 .env，填入真实的 Token
baidu-search config set-token   # 交互式输入
```

## 使用

### 基本搜索

```bash
baidu-search search "人工智能技术"
```

### 时效性过滤

```bash
baidu-search search "今天热点新闻" --recency week
baidu-search search "最新论文" -r month
baidu-search search "年度回顾" -r year
```

可选值：`day` | `week` | `month` | `year`

### 输出格式

```bash
# 彩色表格（默认）
baidu-search search "Python教程"

# JSON 格式（适合管道处理）
baidu-search search "Python教程" --format json | jq '.results[].url'

# 纯文本格式
baidu-search search "Python教程" --format simple
```

### 管理配置

```bash
# 查看当前配置
baidu-search config show

# 设置 Access Token
baidu-search config set-token
```

### 查看帮助

```bash
baidu-search --help
baidu-search search --help
```

## 命令行参数

### search 命令

| 参数 | 短选项 | 说明 | 默认值 |
|------|--------|------|--------|
| `QUERY` | - | 搜索关键词 | 必填 |
| `--token` | `-t` | 千帆 Access Token | - |
| `--recency` | `-r` | 时效性: day / week / month / year | 不限 |
| `--format` | `-f` | 输出格式: table / json / simple | table |
| `--config` | `-c` | 自定义配置文件路径 | - |

## 配置文件

非敏感配置可写入 `config.yaml`：

```yaml
api_url: "https://qianfan.baidubce.com/v2/ai_search/web_search"
edition: "standard"
search_source: "baidu_search_v2"
timeout: 30
```

配置文件搜索路径：当前目录 `./config.yaml` → `~/.search/config.yaml`

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
