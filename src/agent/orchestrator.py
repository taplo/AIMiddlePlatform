import logging
from typing import Any

from src.agent.agent import CVAgent
from src.models.inference import InferenceOrchestrator
from src.routing.fast_path import FastPathHandler

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

    async def process(
        self,
        frame_context: dict[str, Any],
        image_data: bytes | None = None,
    ) -> dict[str, Any]:
        if image_data:
            return await self.agent.analyze_with_image(frame_context, image_data)
        return await self.agent.analyze(frame_context)
