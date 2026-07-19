from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FrameInfo(BaseModel):
    width: int
    height: int
    fps_actual: float


class ModelResult(BaseModel):
    model_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    request_id: str
    timestamp: datetime
    camera_id: str
    frame_info: FrameInfo | None = None
    results: list[ModelResult] = Field(default_factory=list)
    latency_ms: float = 0.0


class StreamConfig(BaseModel):
    camera_id: str
    stream_url: str
    protocol: str = "rtsp"
    target_fps: float = 2.0
    roi: dict[str, Any] | None = None


class StreamTask(BaseModel):
    task_id: str
    camera_id: str
    stream_url: str
    protocol: str
    status: str = "active"
    config: StreamConfig | None = None
