"""配置加载与通用工具测试"""
import os
from unittest.mock import patch

import pytest

from src.utils.common import safe_execute, validate_config, with_retry
from src.utils.config_loader import ConfigLoader
from src.utils.exceptions import ConfigurationError, RetryableError


class TestConfigLoader:
    @pytest.fixture
    def config_dir(self, tmp_path):
        d = tmp_path / "config"
        d.mkdir()
        (d / "config.yaml").write_text(
            "api:\n"
            "  stooq:\n"
            "    timeout: 20\n"
            "llm:\n"
            "  api_key: \"${TEST_API_KEY}\"\n"
            "  model: \"gpt-4o\"\n",
            encoding="utf-8",
        )
        (d / "keywords.txt").write_text("黄金\n白银\n\n# 注释行\n", encoding="utf-8")
        return d

    def test_loads_yaml(self, config_dir):
        config = ConfigLoader(str(config_dir)).load_main_config()
        assert config["api"]["stooq"]["timeout"] == 20
        assert config["llm"]["model"] == "gpt-4o"

    def test_substitutes_env_vars(self, config_dir):
        with patch.dict(os.environ, {"TEST_API_KEY": "secret-123"}):
            config = ConfigLoader(str(config_dir)).load_main_config()
        assert config["llm"]["api_key"] == "secret-123"

    def test_missing_env_resolves_to_empty_string(self, config_dir):
        """环境变量缺失时应解析为空串，而非保留 ${VAR} 字面量。

        回归测试：保留占位符会让下游把"未配置"误判为"已配置"，
        进而用 '${SLACK_WEBHOOK_URL}' 这类非法值初始化通知渠道并抛错。
        """
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigLoader(str(config_dir)).load_main_config()
        assert config["llm"]["api_key"] == ""
        # 空串为假值，下游的 `if webhook_url:` 判断得以正确跳过
        assert not config["llm"]["api_key"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ConfigLoader(str(tmp_path)).load_main_config()

    def test_dotted_get(self, config_dir):
        loader = ConfigLoader(str(config_dir))
        loader.load_main_config()

        assert loader.get("api.stooq.timeout") == 20
        assert loader.get("api.missing.key", "fallback") == "fallback"

    def test_load_text_skips_blank_lines(self, config_dir):
        lines = ConfigLoader(str(config_dir)).load_text("keywords.txt")
        assert "黄金" in lines
        assert "" not in lines


class TestValidateConfig:
    def test_passes_when_keys_present(self):
        validate_config({"a": 1, "b": 2}, ["a", "b"])

    def test_raises_on_missing_keys(self):
        with pytest.raises(ConfigurationError) as exc:
            validate_config({"a": 1}, ["a", "b"], "测试配置")
        assert "b" in str(exc.value)

    def test_empty_requirements_always_pass(self):
        validate_config({}, [])


class TestWithRetry:
    def test_returns_on_first_success(self):
        calls = []

        @with_retry(max_attempts=3, delay=0)
        def fn():
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_retries_then_succeeds(self):
        calls = []

        @with_retry(max_attempts=3, delay=0, exceptions=(RetryableError,))
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RetryableError("暂时失败")
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 3

    def test_raises_after_exhausting_attempts(self):
        calls = []

        @with_retry(max_attempts=2, delay=0, exceptions=(RetryableError,))
        def fn():
            calls.append(1)
            raise RetryableError("持续失败")

        with pytest.raises(RetryableError):
            fn()
        assert len(calls) == 2

    def test_non_retryable_error_fails_fast(self):
        calls = []

        @with_retry(max_attempts=3, delay=0, exceptions=(RetryableError,))
        def fn():
            calls.append(1)
            raise ValueError("不可重试")

        with pytest.raises(ValueError):
            fn()
        assert len(calls) == 1, "不可重试异常不应触发重试"


class TestSafeExecute:
    def test_returns_result_on_success(self):
        assert safe_execute(lambda: 42) == 42

    def test_returns_default_on_failure(self):
        def boom():
            raise RuntimeError("失败")

        assert safe_execute(boom, default_value="fallback") == "fallback"
