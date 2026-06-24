"""CLI 入口 — typer 命令行应用。

用法：
    baidu-search search "搜索词"
    baidu-search search "搜索词" --recency week
    baidu-search search "搜索词" --format json
    baidu-search config show
    baidu-search config set-token
"""

from pathlib import Path
from typing import Optional

import typer

from search.api import BaiduSearchClient
from search.config import Settings
from search.exceptions import SearchError, ConfigError
from search.formatters import FORMATTERS
from search.models import SearchParams

app = typer.Typer(
    name="baidu-search",
    help="百度千帆 AI 搜索 CLI 工具",
    no_args_is_help=True,
)

# ── 配置子命令组 ──────────────────────────────────────────────
config_app = typer.Typer(help="管理配置")
app.add_typer(config_app, name="config")

RECENCY_CHOICES = ["day", "week", "month", "year"]


@config_app.command("show")
def config_show():
    """显示当前配置（Token 脱敏显示）。"""
    settings = Settings.load()
    print("当前配置:")
    print(f"  API 地址:       {settings.api_url}")
    print(f"  版本:           {settings.edition}")
    print(f"  搜索源:         {settings.search_source}")
    print(f"  请求超时:       {settings.timeout}秒")
    if settings.access_token:
        print(f"  Access Token:   {settings.masked_token()}")
    else:
        print(f"  Access Token:   [未设置]")
    print()
    print("配置文件搜索路径:")
    print(f"  1. 当前目录/config.yaml")
    print(f"  2. ~/.search/config.yaml")


@config_app.command("set-token")
def config_set_token(
    token: str = typer.Option(
        ...,
        "--token",
        "-t",
        prompt=True,
        hide_input=True,
        help="千帆 Access Token",
    ),
):
    """将 Access Token 写入当前目录的 .env 文件。"""
    env_path = Path.cwd() / ".env"
    existing_lines = []
    has_token = False
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    for line in existing_lines:
        if line.startswith("BAIDU_ACCESS_TOKEN="):
            new_lines.append(f"BAIDU_ACCESS_TOKEN={token}")
            has_token = True
        else:
            new_lines.append(line)

    if not has_token:
        new_lines.append(f"BAIDU_ACCESS_TOKEN={token}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[OK] Access Token 已写入 {env_path}")


# ── 搜索子命令 ──────────────────────────────────────────────

@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词"),
    token: Optional[str] = typer.Option(
        None, "--token", "-t", help="千帆 Access Token (Bearer)"
    ),
    recency: Optional[str] = typer.Option(
        None, "--recency", "-r",
        help=f"时效性过滤: {', '.join(RECENCY_CHOICES)}",
    ),
    format: str = typer.Option(
        "table", "--format", "-f",
        help="输出格式: table（彩色表格）, json, simple（纯文本）",
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="配置文件路径",
    ),
):
    """搜索关键词，返回 AI 增强的网页搜索结果。

    示例：
        baidu-search search "人工智能"
        baidu-search search "今天热点新闻" -r week
        baidu-search search "Python教程" -f json
    """
    # 1. 加载配置
    try:
        settings = Settings.load(
            config_path=config_file,
            cli_token=token,
        )
        settings.ensure_access_token()
    except ConfigError as e:
        typer.echo(f"❌ 配置错误: {e}", err=True)
        raise typer.Exit(code=2)

    # 2. 校验格式
    if format not in FORMATTERS:
        typer.echo(
            f"❌ 不支持的输出格式: {format}。可选: {', '.join(FORMATTERS)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # 3. 校验 recency
    if recency and recency not in RECENCY_CHOICES:
        typer.echo(
            f"❌ 无效的时效性参数: {recency}。可选: {', '.join(RECENCY_CHOICES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # 4. 执行搜索
    try:
        client = BaiduSearchClient(settings)
        params = SearchParams(q=query, recency=recency)
        response = client.search(params)
    except SearchError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(code=e.exit_code)

    # 5. 格式化输出
    formatter = FORMATTERS[format]
    output = formatter(response)
    print(output)


def cli_entry():
    """独立入口，供 console_scripts 使用。"""
    app()


if __name__ == "__main__":
    cli_entry()
