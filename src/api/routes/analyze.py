import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.agent.orchestrator import AgentOrchestrator
from src.pipeline.dag import DAGDefinition
from src.pipeline.registry import PipelineRegistry

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])

_orchestrator: AgentOrchestrator | None = None


def init_orchestrator(orchestrator: AgentOrchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


@router.post("/frame")
async def analyze_frame(body: dict) -> dict:
    if _orchestrator is None:
        raise HTTPException(500, "Orchestrator not initialized")
    result = await _orchestrator.process(body)
    return result


@router.get("/ping")
async def ping() -> dict:
    return {"ok": True, "timestamp": str(datetime.now())}
