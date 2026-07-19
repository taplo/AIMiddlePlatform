import logging
from typing import Any

from src.agent.agent import CVAgent
from src.agent.client import LLMError
from src.agent.health import get_health_checker
from src.models.inference import InferenceOrchestrator
from src.routing.fast_path import FastPathHandler
from src.resilience.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        fast_path: FastPathHandler,
        agent: CVAgent,
        inference: InferenceOrchestrator,
    ):
        self.fast_path = fast_path
        self.agent = agent
        self.inference = inference
        self._cb = get_circuit_breaker("llm-agent", failure_threshold=3, recovery_timeout=30.0)

    async def process(
        self,
        frame_context: dict[str, Any],
        image_data: bytes | None = None,
    ) -> dict[str, Any]:
        if not self._cb.is_available:
            logger.warning("LLM circuit breaker OPEN, degrading to fast path")
            return await self._fallback(frame_context, "llm_circuit_open")

        try:
            if image_data:
                result = await self._cb.call(self.agent.analyze_with_image, frame_context, image_data)
            else:
                result = await self._cb.call(self.agent.analyze, frame_context)
            try:
                await get_health_checker().check(self.agent.llm)
            except Exception:
                pass
            return result
        except LLMError as e:
            logger.error("LLM unavailable: %s, degrading to fast path", e)
            return await self._fallback(frame_context, "llm_unavailable")
        except Exception as e:
            logger.error("Agent orchestrator error: %s, degrading to fast path", e)
            return await self._fallback(frame_context, "agent_error")

    async def _fallback(self, frame_context: dict[str, Any], reason: str) -> dict[str, Any]:
        try:
            result = await self.fast_path.process(frame_context)
            if result is None:
                result = {}
            result["_degraded"] = True
            result["_degraded_reason"] = reason
            return result
        except Exception as e:
            logger.error("Fallback fast path also failed: %s", e)
            return {"error": str(e), "_degraded": True, "_degraded_reason": reason}
