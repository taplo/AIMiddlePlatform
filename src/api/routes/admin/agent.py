import logging

from fastapi import APIRouter

from src.agent.agent_config import get_config_manager
from src.agent.client import get_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["admin-agent"])

_default_config = {
    "llm": {
        "provider": "openai",
        "url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_name": "Qwen/Qwen2.5-VL-7B-Instruct",
    },
    "system_prompt": "你是一个专业的计算机视觉分析助手。分析图像中的场景、物体、人脸等信息，输出结构化结果。",
    "thresholds": {
        "parking_lot": 0.7,
        "entrance": 0.8,
        "street": 0.6,
        "indoor": 0.7,
    },
    "routing_rules": [],
}

_config = dict(_default_config)
_cfg_mgr = get_config_manager()


@router.get("/config")
async def get_agent_config() -> dict:
    return dict(_config)


@router.get("/providers")
async def list_providers() -> list[dict[str, str]]:
    return get_providers()


@router.post("/config")
async def save_agent_config(body: dict) -> dict:
    _config.clear()
    _config.update(body)
    _cfg_mgr.apply_config(_config)
    logger.info("Agent config updated, LLM client recreated")
    return {"ok": True}
