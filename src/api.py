import asyncio
import json
import logging
import traceback
from functools import partial
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import load_config
from .schemas import CustomerInput
from .llm import create_llm
from .search import create_searchers
from .engine import PortraitEngine, CustomerInputValidationError
from .storage import generate_id, load_portrait, save_portrait, update_portrait
from .wiki_client import push_portrait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="客户画像生成引擎",
    description="展厅接待多维客户画像 API",
    version="1.0.0",
)

# 全局引擎实例（在 startup 时初始化）
_engine: PortraitEngine | None = None
_startup_error: str | None = None


@app.on_event("startup")
async def startup():
    import os
    global _engine, _startup_error
    config_path = os.environ.get("PORTRAIT_CONFIG", "config.yaml")
    logger.info(f"[启动] 加载配置：{config_path}（CWD={os.getcwd()}）")
    try:
        config = load_config(config_path)
        llm = create_llm(config["llm"])
        searchers = create_searchers(config["search"])
        _engine = PortraitEngine(config, llm, searchers)
        logger.info(f"[启动] 引擎初始化完成，搜索引擎：{list(searchers.keys())}")
    except Exception as e:
        _startup_error = str(e)
        logger.error(f"[启动失败] {traceback.format_exc()}")


class PortraitRequest(BaseModel):
    org_name: str
    guest_name: str
    # 以下字段中控邀约系统不采集，可选；留空时由本服务自动推断
    industry: str = Field(default="", description="所属行业（可选）。留空时从 domain_specialty 自动推断")
    visit_needs: str = Field(default="", description="参观目的说明（可选）。留空时从 domain_specialty + reception_goal 自动推断")
    # 来自中控邀约登记的扩展字段（均可选）
    client_type: str = Field(default="", description="客户属性：政府/部队/企业/媒体/外宾/合作伙伴/内部/其他")
    guest_title: str = Field(default="", description="主宾职务，如：副所长、总经理")
    visit_category: str = Field(default="", description="参观类别：领导参观型/营销发展型/客户签约型/…")
    reception_goal: str = Field(default="", description="本次接待营销目标和目的")
    client_intro: str = Field(default="", description="客户基本信息（填单人手工描述）")
    domain_specialty: str = Field(default="", description="参观需求/专场，单选，如：农业农村专场")
    display_needs: str = Field(default="", description="布展需求，透传至 wiki 接待活动记录")


def _derive_industry(domain_specialty: str) -> str:
    """domain_specialty → industry 兜底映射。"""
    mapping = {
        "农业农村专场": "农业科技",
        "金融专场": "金融服务",
        "工业专场": "智能制造",
        "互联网": "互联网科技",
        "政务公安专场": "政务信息化",
        "政府专场": "政务服务",
        "数厅专场": "数字政务",
        "卫健专场": "医疗健康",
        "住建专场": "城市建设",
        "交通物流专场": "交通物流",
        "文宣专场": "文化宣传",
        "应急专场": "应急管理",
        "资管专场": "资产管理",
        "商客专场": "商业客户",
        "通用场": "通用",
    }
    return mapping.get(domain_specialty, domain_specialty.replace("专场", ""))


def _derive_visit_needs(req: PortraitRequest) -> str:
    """中控不传 visit_needs 时，基于 domain_specialty + reception_goal 合成。"""
    parts = [p for p in [req.domain_specialty, req.reception_goal] if p]
    if parts:
        return "，".join(parts)
    return "参观交流"


class PortraitIdResponse(BaseModel):
    portrait_id: str


class PortraitPatchRequest(BaseModel):
    portrait: dict = Field(default_factory=dict)
    supplement: dict = Field(default_factory=dict)


@app.get("/ui", response_class=HTMLResponse)
async def ui_page(id: str = ""):
    if id:
        html_path = Path(__file__).parent.parent / "static" / "detail.html"
    else:
        html_path = Path(__file__).parent.parent / "static" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="页面不存在")
    return html_path.read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "engine_ready": _engine is not None,
        "startup_error": _startup_error,
    }


@app.post("/portrait", response_model=PortraitIdResponse)
async def generate_portrait(req: PortraitRequest, background_tasks: BackgroundTasks):
    if _engine is None:
        detail = f"引擎未就绪" + (f"：{_startup_error}" if _startup_error else "")
        raise HTTPException(status_code=503, detail=detail)

    customer = CustomerInput(
        org_name=req.org_name,
        guest_name=req.guest_name,
        industry=req.industry or _derive_industry(req.domain_specialty),
        visit_needs=req.visit_needs or _derive_visit_needs(req),
        client_type=req.client_type,
        guest_title=req.guest_title,
        visit_category=req.visit_category,
        reception_goal=req.reception_goal,
        client_intro=req.client_intro,
        domain_specialty=req.domain_specialty,
    )
    logger.info(f"[请求] org={req.org_name!r} guest={req.guest_name!r} client_type={req.client_type!r}")

    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, partial(_engine.run, customer)),
            timeout=360,
        )
    except asyncio.TimeoutError:
        logger.error("[超时] 画像生成超过 360s")
        raise HTTPException(status_code=504, detail="画像生成超时（超过6分钟），请稍后重试")
    except CustomerInputValidationError as e:
        raise HTTPException(status_code=422, detail=e.reason)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[未捕获异常]\n{tb}")
        raise HTTPException(status_code=500, detail=f"引擎内部错误：{e}\n\n{tb}")

    if result.error:
        logger.error(f"[引擎错误] {result.error}")
        raise HTTPException(status_code=500, detail=result.error)

    portrait_id = generate_id()
    save_portrait(
        portrait_id,
        {
            "customer_input": req.model_dump(),
            "portrait": result.portrait,
            "confidence_assessment": result.confidence_assessment,
            "sources": result.sources,
            "queries_executed": result.queries_executed,
        },
    )
    # 后台触发 wiki 推送，不阻塞响应
    background_tasks.add_task(push_portrait, portrait_id)
    logger.info(f"[完成] portrait_id={portrait_id} {len(result.queries_executed)} 次搜索")
    return PortraitIdResponse(portrait_id=portrait_id)


@app.get("/portrait/{portrait_id}")
async def get_portrait(portrait_id: str):
    data = load_portrait(portrait_id)
    if not data:
        raise HTTPException(status_code=404, detail="画像不存在")
    return data


@app.patch("/portrait/{portrait_id}")
async def patch_portrait(portrait_id: str, req: PortraitPatchRequest, background_tasks: BackgroundTasks):
    try:
        record = update_portrait(portrait_id, req.model_dump(exclude_unset=True))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="画像不存在")
    # 后台触发 wiki 补录
    background_tasks.add_task(push_portrait, portrait_id)
    return record


@app.post("/portrait/stream")
async def stream_portrait(req: PortraitRequest):
    """SSE 流式端点：供 WebUI 使用，实时推送进度日志和最终结果。"""
    if _engine is None:
        detail = "引擎未就绪" + (f"：{_startup_error}" if _startup_error else "")
        async def _err():
            yield f'data: {json.dumps({"type":"error","msg":detail}, ensure_ascii=False)}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    customer = CustomerInput(
        org_name=req.org_name,
        guest_name=req.guest_name,
        industry=req.industry or _derive_industry(req.domain_specialty),
        visit_needs=req.visit_needs or _derive_visit_needs(req),
        client_type=req.client_type, guest_title=req.guest_title,
        visit_category=req.visit_category, reception_goal=req.reception_goal,
        client_intro=req.client_intro, domain_specialty=req.domain_specialty,
    )
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def log_fn(msg: str):
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "log", "msg": msg})

    async def run_engine():
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, partial(_engine.run, customer, log_fn)),
                timeout=360,
            )
            if result.error:
                await queue.put({"type": "error", "msg": result.error})
            else:
                await queue.put({"type": "result", "data": {
                    "portrait": result.portrait,
                    "confidence_assessment": result.confidence_assessment,
                    "sources": result.sources,
                    "queries_executed": result.queries_executed,
                }})
        except asyncio.TimeoutError:
            await queue.put({"type": "error", "msg": "画像生成超时（超过6分钟），请稍后重试"})
        except CustomerInputValidationError as e:
            await queue.put({"type": "validation_error", "msg": e.reason})
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[流式接口异常]\n{tb}")
            await queue.put({"type": "error", "msg": f"引擎内部错误：{e}"})

    task = asyncio.create_task(run_engine())

    async def generate():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
                yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
                if event["type"] in ("result", "error", "validation_error"):
                    break
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield 'data: {"type":"heartbeat"}\n\n'
        if not task.done():
            await task

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"[全局异常] {request.url}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误：{exc}\n\n{tb}"},
    )
