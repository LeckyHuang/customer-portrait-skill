"""测试配置加载的 ${ENV_VAR} / ${ENV_VAR:default} 展开。"""
import pytest

from src.config import _expand_env, _expand_config, load_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # 测试间隔离环境变量
    for k in ("LLM_API_KEY", "BOCHAAI_API_KEY", "ANSIPAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)


class TestExpandEnv:
    def test_plain_string_untouched(self):
        assert _expand_env("hello world") == "hello world"

    def test_env_var_present(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-real")
        assert _expand_env("${LLM_API_KEY}") == "sk-real"

    def test_env_var_missing_no_default_keeps_placeholder(self):
        # 不存在且无默认值 → 原样保留（fail-closed，便于发现配置缺失）
        assert _expand_env("${MISSING_VAR}") == "${MISSING_VAR}"

    def test_env_var_missing_with_default(self):
        assert _expand_env("${MISSING_VAR:fallback}") == "fallback"

    def test_empty_env_uses_default_when_provided(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "")
        assert _expand_env("${LLM_API_KEY:default-key}") == "default-key"

    def test_empty_env_no_default_returns_empty(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "")
        assert _expand_env("${LLM_API_KEY}") == ""

    def test_non_string_passthrough(self):
        assert _expand_env(123) == 123  # type: ignore[arg-type]
        assert _expand_env(None) is None  # type: ignore[arg-type]

    def test_embedded_in_text(self, monkeypatch):
        monkeypatch.setenv("REGION", "cn")
        assert _expand_env("https://${REGION}.example.com") == "https://cn.example.com"


class TestExpandConfig:
    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-1")
        cfg = {"llm": {"api_key": "${LLM_API_KEY}", "model": "qwen"}}
        out = _expand_config(cfg)
        assert out["llm"]["api_key"] == "sk-1"
        assert out["llm"]["model"] == "qwen"

    def test_list_values(self, monkeypatch):
        monkeypatch.setenv("X", "v1")
        assert _expand_config(["${X}", "plain"]) == ["v1", "plain"]

    def test_does_not_mutate_input(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-1")
        cfg = {"api_key": "${LLM_API_KEY}"}
        _expand_config(cfg)
        assert cfg["api_key"] == "${LLM_API_KEY}"


class TestLoadConfig:
    def test_loads_and_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-loaded")
        p = tmp_path / "cfg.yaml"
        p.write_text("llm:\n  api_key: ${LLM_API_KEY}\n  model: test-model\n", encoding="utf-8")
        cfg = load_config(str(p))
        assert cfg["llm"]["api_key"] == "sk-loaded"
        assert cfg["llm"]["model"] == "test-model"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/cfg.yaml")
