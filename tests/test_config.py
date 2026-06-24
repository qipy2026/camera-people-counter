"""测试配置加载和优先级。"""

import os
from pathlib import Path
from unittest import mock

import pytest
import yaml

from search.config import Settings, ConfigError


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前清除 BAIDU_ 环境变量（覆盖 .env 文件中的值）。"""
    removed = {k: v for k, v in os.environ.items() if k.startswith("BAIDU_")}
    try:
        for k in removed:
            del os.environ[k]
        os.environ["BAIDU_ACCESS_TOKEN"] = ""
        yield
    finally:
        for k, v in removed.items():
            os.environ[k] = v
        if "BAIDU_ACCESS_TOKEN" in os.environ and os.environ["BAIDU_ACCESS_TOKEN"] == "":
            del os.environ["BAIDU_ACCESS_TOKEN"]


class TestSettingsLoad:
    """配置加载测试。"""

    def test_defaults_when_no_config(self):
        """无配置文件时使用默认值。"""
        settings = Settings.load()
        assert settings.api_url == "https://qianfan.baidubce.com/v2/ai_search/web_search"
        assert settings.edition == "standard"
        assert settings.search_source == "baidu_search_v2"
        assert settings.timeout == 30
        assert settings.access_token == ""

    def test_load_from_yaml_file(self, temp_config_dir):
        """从 YAML 文件加载非敏感配置。"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(
            yaml.dump({
                "api_url": "https://custom.api.com/search",
                "edition": "advanced",
                "timeout": 60,
            }),
            encoding="utf-8",
        )
        settings = Settings.load(config_path=config_path)
        assert settings.api_url == "https://custom.api.com/search"
        assert settings.edition == "advanced"
        assert settings.timeout == 60

    def test_env_var_overrides_yaml(self, temp_config_dir):
        """环境变量覆盖 YAML 配置。"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(
            yaml.dump({"timeout": 10}),
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"BAIDU_TIMEOUT": "45"}):
            settings = Settings.load(config_path=config_path)
            assert settings.timeout == 45

    def test_cli_token_overrides_all(self):
        """CLI --token 覆盖环境变量。"""
        with mock.patch.dict(os.environ, {"BAIDU_ACCESS_TOKEN": "env-token"}):
            settings = Settings.load(cli_token="cli-token")
            assert settings.access_token == "cli-token"

    def test_env_token_used_when_no_cli(self):
        """无 CLI 参数时使用环境变量中的 Token。"""
        with mock.patch.dict(os.environ, {"BAIDU_ACCESS_TOKEN": "env-token"}):
            settings = Settings.load()
            assert settings.access_token == "env-token"

    def test_bad_yaml_raises_config_error(self, temp_config_dir):
        """格式错误的 YAML 抛出 ConfigError。"""
        config_path = temp_config_dir / "bad.yaml"
        config_path.write_text("{{{bad: yaml: [", encoding="utf-8")
        with pytest.raises(ConfigError, match="YAML 格式错误"):
            Settings.load(config_path=config_path)


class TestEnsureAccessToken:
    """Token 校验测试。"""

    def test_raises_when_missing(self):
        """未配置 Token 时抛出 ConfigError。"""
        settings = Settings(access_token="")
        with pytest.raises(ConfigError, match="未配置"):
            settings.ensure_access_token()

    def test_returns_token_when_present(self):
        """已配置 Token 时正常返回。"""
        settings = Settings(access_token="my-token")
        assert settings.ensure_access_token() == "my-token"


class TestMaskedToken:
    """Token 脱敏测试。"""

    def test_normal_token(self):
        """正常长度 Token 脱敏显示。"""
        s = Settings(access_token="abcdefgh12345678")
        assert s.masked_token() == "abcd****5678"

    def test_short_token(self):
        """短 Token 全脱敏。"""
        s = Settings(access_token="abc")
        assert s.masked_token() == "***"
