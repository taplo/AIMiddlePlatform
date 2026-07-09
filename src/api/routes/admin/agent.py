from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/agent", tags=["admin-agent"])

_default_config = {
    "llm": {
        "provider": "Qwen",
        "url": "",
        "api_key": "",
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


@router.get("/config")
async def get_agent_config() -> dict:
    return dict(_config)


@router.post("/config")
async def save_agent_config(body: dict) -> dict:
    _config.clear()
    _config.update(body)
    return {"ok": True}
