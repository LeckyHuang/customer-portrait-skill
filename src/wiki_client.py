import json
import logging
from typing import Optional

import httpx

from .config import load_config
from .storage import load_portrait

logger = logging.getLogger(__name__)

# 延迟加载配置：模块被导入时配置可能尚未准备好
_config: Optional[dict] = None


def _get_config() -> dict:
    global _config
    if _config is None:
        import os

        config_path = os.environ.get("PORTRAIT_CONFIG", "config.yaml")
        try:
            _config = load_config(config_path)
        except FileNotFoundError:
            _config = {}
    return _config


def _wiki_push_url() -> str:
    return _get_config().get("wiki", {}).get("push_url", "")


async def push_portrait(portrait_id: str) -> dict:
    """将画像数据推送到 wiki-app-hub 进行 ingest。

    失败仅记录日志，不向上抛异常，避免影响主流程。
    """
    url = _wiki_push_url()
    if not url:
        logger.warning("[wiki] wiki.push_url 未配置，跳过推送")
        return {"pushed": False, "reason": "wiki.push_url not configured"}

    data = load_portrait(portrait_id)
    if not data:
        return {"pushed": False, "reason": "portrait not found"}

    payload = {
        "portrait_id": portrait_id,
        "customer_input": data.get("customer_input", {}),
        "portrait": data.get("portrait", {}),
        "confidence_assessment": data.get("confidence_assessment", {}),
        "sources": data.get("sources", []),
        "queries_executed": data.get("queries_executed", []),
        "supplement": data.get("supplement", {}),
        "updated_at": data.get("updated_at"),
    }

    headers = {"Content-Type": "application/json"}
    # 新架构下 wiki-app-hub 的 /ingest/portrait 已开放，不携带 X-Sync-Key
    # 如后续需要恢复鉴权，可在此读取 WIKI_PUSH_API_KEY 并加入 headers

    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.exception(
            "[wiki] 推送画像 %s 失败，HTTP %s: %s",
            portrait_id,
            e.response.status_code,
            e.response.text[:300],
        )
        return {"pushed": False, "reason": f"HTTP {e.response.status_code}"}
    except httpx.TimeoutException:
        logger.exception("[wiki] 推送画像 %s 超时", portrait_id)
        return {"pushed": False, "reason": "timeout"}
    except Exception as e:
        logger.exception("[wiki] 推送画像 %s 失败", portrait_id)
        return {"pushed": False, "reason": str(e)}
