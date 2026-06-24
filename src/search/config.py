"""配置管理：环境变量 → 配置文件 → CLI 参数 三级优先级合并。

优先级（高→低）：
1. CLI --token 参数
2. 环境变量 BAIDU_ACCESS_TOKEN
3. .env 文件
4. config.yaml 配置文件（仅非敏感项）
"""

import os
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from search.exceptions import ConfigError


class Settings(BaseSettings):
    """全局设置，支持 env / .env / config.yaml 加载。"""

    model_config = SettingsConfigDict(
        env_prefix="BAIDU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    access_token: str = ""
    api_url: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    edition: str = "standard"
    search_source: str = "baidu_search_v2"
    timeout: int = 30

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        cli_token: str | None = None,
    ) -> "Settings":
        """综合加载配置：config.yaml → env/.env → CLI 覆盖。

        Args:
            config_path: YAML 配置文件路径，为 None 时自动搜索。
            cli_token: 命令行传入的 Access Token，优先级最高。

        Returns:
            合并后的 Settings 实例。
        """
        # 1. 从 YAML 中加载基础值
        yaml_values: dict = {}
        yaml_path = cls._find_config_file(config_path)
        if yaml_path:
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                    for key in ("api_url", "edition", "search_source", "timeout"):
                        if key in loaded:
                            yaml_values[key] = loaded[key]
            except yaml.YAMLError as e:
                raise ConfigError(f"配置文件 YAML 格式错误: {e}")

        # 2. 创建 Settings 实例：env/.env 自动加载
        settings = cls()

        # 3. YAML 值仅填充未被环境变量覆盖的字段
        _yaml_to_env = {
            "api_url": "BAIDU_API_URL",
            "edition": "BAIDU_EDITION",
            "search_source": "BAIDU_SEARCH_SOURCE",
            "timeout": "BAIDU_TIMEOUT",
        }
        for key, value in yaml_values.items():
            env_key = _yaml_to_env.get(key)
            if env_key and env_key not in os.environ:
                setattr(settings, key, value)

        # 4. CLI --token 覆盖一切
        if cli_token:
            settings.access_token = cli_token

        return settings

    @staticmethod
    def _find_config_file(explicit_path: Path | None = None) -> Path | None:
        """查找配置文件：显式指定 > 当前目录 config.yaml > ~/.search/config.yaml。"""
        if explicit_path:
            return explicit_path if explicit_path.exists() else None

        candidates = [Path.cwd() / "config.yaml"]
        try:
            candidates.append(Path.home() / ".search" / "config.yaml")
        except RuntimeError:
            pass

        for p in candidates:
            if p.exists():
                return p
        return None

    def ensure_access_token(self) -> str:
        """校验 Access Token 已配置，否则抛出 ConfigError。"""
        if not self.access_token:
            raise ConfigError(
                "未配置百度千帆 Access Token。请通过以下任一方式设置：\n"
                "  1. 命令行参数: --token <你的TOKEN>\n"
                "  2. 环境变量:   export BAIDU_ACCESS_TOKEN=<你的TOKEN>\n"
                "  3. .env 文件:   在项目根目录创建 .env 文件并写入 BAIDU_ACCESS_TOKEN=<你的TOKEN>"
            )
        return self.access_token

    def masked_token(self) -> str:
        """返回脱敏后的 Token，仅用于显示。"""
        t = self.access_token
        if len(t) <= 8:
            return "*" * len(t)
        return t[:4] + "****" + t[-4:]
