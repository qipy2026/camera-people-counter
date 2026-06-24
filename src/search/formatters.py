"""输出格式化器：table（Rich 表格）、json、simple（纯文本）三种模式。"""

import json

from search.models import SearchResponse


def format_rich_table(response: SearchResponse) -> str:
    """将搜索结果渲染为 Rich 表格字符串（带 ANSI 颜色）。"""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    import io

    buf = io.StringIO()
    str_console = Console(file=buf, force_terminal=True, color_system="standard", width=160)

    # 表头摘要
    str_console.print(
        f"[bold]搜索:[/bold] {response.query}  "
        f"[dim]|  共 {response.total} 条结果[/dim]"
    )
    str_console.print()

    # AI 综合回答（如有）
    if response.raw_text:
        str_console.print(
            Panel(response.raw_text, title="AI 回答", border_style="green")
        )
        str_console.print()

    if not response.results:
        str_console.print("[yellow]未找到相关结果。[/yellow]")
        return buf.getvalue()

    # 构建表格
    table = Table(show_header=True, header_style="bold cyan", show_lines=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("标题", style="bold", width=30)
    table.add_column("URL", style="dim blue", width=36)
    table.add_column("来源", style="magenta", width=10)
    table.add_column("摘要", width=36)

    for i, r in enumerate(response.results, start=1):
        abstract = r.abstract or ""
        if len(abstract) > 200:
            abstract = abstract[:200] + "…"
        site = r.site_name or "-"
        table.add_row(str(i), r.title, r.url, site, abstract)

    str_console.print(table)
    return buf.getvalue()


def format_json(response: SearchResponse) -> str:
    """将搜索结果输出为格式化的 JSON 字符串。"""
    return json.dumps(
        response.model_dump(),
        indent=2,
        ensure_ascii=False,
    )


def format_simple(response: SearchResponse) -> str:
    """将搜索结果输出为纯文本，每条结果一组。"""
    lines = [f"搜索: {response.query}  共{response.total}条\n"]

    if response.raw_text:
        lines.append(f"[AI 回答] {response.raw_text}\n")

    if not response.results:
        lines.append("未找到相关结果。\n")
        return "".join(lines)

    for i, r in enumerate(response.results, start=1):
        abstract = r.abstract or ""
        if len(abstract) > 150:
            abstract = abstract[:150] + "…"
        lines.append(f"{i}. {r.title}")
        lines.append(f"   {r.url}")
        if r.site_name or r.time:
            meta = " | ".join(filter(None, [r.site_name, r.time]))
            lines.append(f"   [{meta}]")
        if abstract:
            lines.append(f"   {abstract}")
        lines.append("")

    return "\n".join(lines)


# 格式器注册表
FORMATTERS = {
    "table": format_rich_table,
    "json": format_json,
    "simple": format_simple,
}
