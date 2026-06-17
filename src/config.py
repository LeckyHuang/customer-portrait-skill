import os
import re
import yaml
from pathlib import Path


def _expand_env(value: str) -> str:
    """替换 ${ENV_VAR} 或 ${ENV_VAR:default} 占位符"""
    if not isinstance(value, str):
        return value
    def _repl(m):
        var_name = m.group(1)
        default = m.group(2)
        if var_name in os.environ:
            val = os.environ[var_name]
            # 环境变量存在但为空字符串时，如果有显式默认值则使用默认值
            if val == "" and default is not None:
                return default
            return val
        if default is not None:
            return default
        return m.group(0)
    return re.sub(r"\$\{(\w+)(?::([^}]*))?\}", _repl, value)


def _expand_config(obj):
    if isinstance(obj, dict):
        return {k: _expand_config(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_config(i) for i in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_config(raw)
