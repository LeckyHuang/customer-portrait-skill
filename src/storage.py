import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data" / "portraits"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _path(portrait_id: str) -> Path:
    return DATA_DIR / f"{portrait_id}.json"


def generate_id() -> str:
    return uuid.uuid4().hex


def save_portrait(portrait_id: str, payload: dict) -> None:
    """首次生成时保存完整画像。"""
    record = {
        "portrait_id": portrait_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    _path(portrait_id).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_portrait(portrait_id: str) -> Optional[dict]:
    p = _path(portrait_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def update_portrait(portrait_id: str, patch: dict) -> dict:
    """合并用户补充信息，更新 updated_at，返回完整记录。"""
    record = load_portrait(portrait_id)
    if record is None:
        raise FileNotFoundError(f"Portrait {portrait_id} not found")

    # 允许更新 portrait 下的子字段
    if "portrait" in patch:
        record.setdefault("portrait", {})
        for k, v in patch["portrait"].items():
            record["portrait"][k] = v

    # 允许更新顶层补充字段
    if "supplement" in patch:
        record["supplement"] = {
            **(record.get("supplement") or {}),
            **patch["supplement"],
        }

    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    _path(portrait_id).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
