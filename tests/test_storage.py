"""测试画像存储的存/取/改（用 monkeypatch 隔离 DATA_DIR，不污染真实数据目录）。"""
import json
from datetime import datetime, timezone

import pytest

from src import storage


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    # storage._path 直接引用模块级 DATA_DIR 全局，patch 后隔离到 tmp
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    return tmp_path


def test_generate_id_is_hex_uuid():
    pid = storage.generate_id()
    assert isinstance(pid, str) and len(pid) == 32
    assert all(c in "0123456789abcdef" for c in pid)


def test_save_then_load_roundtrip():
    pid = storage.generate_id()
    payload = {"portrait": {"org_profile": "X"}, "sources": [{"url": "http://a"}]}
    storage.save_portrait(pid, payload)

    loaded = storage.load_portrait(pid)
    assert loaded is not None
    assert loaded["portrait_id"] == pid
    assert loaded["portrait"]["org_profile"] == "X"
    assert loaded["sources"] == [{"url": "http://a"}]
    assert "created_at" in loaded and "updated_at" in loaded


def test_load_missing_returns_none():
    assert storage.load_portrait("does-not-exist") is None


def test_update_merges_portrait_subfields_and_updates_ts():
    pid = storage.generate_id()
    storage.save_portrait(pid, {"portrait": {"a": 1, "b": 2}})
    before = storage.load_portrait(pid)

    updated = storage.update_portrait(pid, {"portrait": {"b": 99, "c": 3}})
    assert updated["portrait"] == {"a": 1, "b": 99, "c": 3}
    # portrait 子字段不应泄漏到记录顶层
    assert "b" not in updated or updated.get("b") is None
    # updated_at 推进
    assert datetime.fromisoformat(updated["updated_at"]) >= datetime.fromisoformat(before["updated_at"])


def test_update_supplement_merges():
    pid = storage.generate_id()
    storage.save_portrait(pid, {"portrait": {}})
    storage.update_portrait(pid, {"supplement": {"k1": "v1"}})
    r1 = storage.load_portrait(pid)
    assert r1["supplement"] == {"k1": "v1"}

    r2 = storage.update_portrait(pid, {"supplement": {"k2": "v2"}})
    # supplement 应合并而非覆盖
    assert r2["supplement"] == {"k1": "v1", "k2": "v2"}


def test_update_missing_record_raises():
    with pytest.raises(FileNotFoundError):
        storage.update_portrait("nope", {"portrait": {"x": 1}})
