import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from src.ingestion.frame_extractor import AdaptiveFrameExtractor
from src.ingestion.gb28181 import GB28181StreamReader
from src.ingestion.rtsp import RTSPStreamReader
from src.ingestion.stream import StreamReader
from src.queue.interface import FrameQueue
from src.queue.redis_streams import RedisStreamQueue

_alert_callbacks: list = []

logger = logging.getLogger(__name__)


@dataclass
class CameraStats:
    camera_id: str = ""
    connected: bool = False
    reconnects: int = 0
    frames_read: int = 0
    frames_kept: int = 0
    fps_output: float = 0.0
    current_fps_target: float = 0.0
    uptime: float = 0.0
    last_error: str = ""
    started_at: float = field(default_factory=time.monotonic)


_ENCODE_QUALITY = 85
_MAX_RECONNECT_DELAY = 60.0
_INITIAL_RECONNECT_DELAY = 1.0
_MAX_RECONNECT_ATTEMPTS = 50


def register_alert_callback(cb) -> None:
    _alert_callbacks.append(cb)


def _publish_alert(event_type: str, camera_id: str, message: str, **extra) -> None:
    payload = json.dumps({
        "type": event_type,
        "camera_id": camera_id,
        "message": message,
        "timestamp": time.time(),
        **extra,
    })
    for cb in _alert_callbacks:
        try:
            cb(payload)
        except Exception:
            logger.debug("Alert callback failed", exc_info=True)


def _encode_jpeg(frame: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _ENCODE_QUALITY])
    return buf.tobytes()


class CameraSession:
    def __init__(
        self,
        camera_id: str,
        stream_url: str,
        protocol: str = "rtsp",
        target_fps: float = 2.0,
        frame_queue: FrameQueue | None = None,
    ) -> None:
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.protocol = protocol
        self.target_fps = target_fps
        self._queue = frame_queue or RedisStreamQueue()
        self._task: asyncio.Task | None = None
        self._running = False
        self._reader: StreamReader | None = None
        self._extractor: AdaptiveFrameExtractor | None = None
        self._reconnect_delay = _INITIAL_RECONNECT_DELAY
        self._backlog: int = 0
        self._backlog_update_interval = 30
        self._frames_since_backlog_check = 0
        self.stats = CameraStats(camera_id=camera_id)

    async def _run(self) -> None:
        self._running = True
        self.stats.started_at = time.monotonic()
        while self._running:
            try:
                self._reader = self._create_reader()
                self._extractor = AdaptiveFrameExtractor(
                    target_fps=self.target_fps,
                    backlog_size_fn=lambda: self._backlog,
                )

                await self._reader.connect()
                self._reconnect_delay = _INITIAL_RECONNECT_DELAY
                self.stats.connected = True
                logger.info("Camera %s connected", self.camera_id)

                async for frame in self._reader.read_frames():
                    if not self._running:
                        break
                    self.stats.frames_read += 1
                    self._frames_since_backlog_check += 1
                    if self._frames_since_backlog_check >= self._backlog_update_interval:
                        self._frames_since_backlog_check = 0
                        self._backlog = await self._queue.backlog_size(self.camera_id)
                        if self._backlog > 100:
                            _publish_alert("frame_backpressure", self.camera_id, f"Backlog {self._backlog} frames, reducing FPS")

                    if self._extractor.should_keep(frame.data, time.monotonic()):
                        encoded = _encode_jpeg(frame.data)
                        await self._queue.push(self.camera_id, encoded)
                        self.stats.frames_kept += 1
                        now = time.monotonic()
                        elapsed = now - self.stats.started_at
                        self.stats.fps_output = (
                            self.stats.frames_kept / elapsed if elapsed > 0 else 0
                        )
                        self.stats.current_fps_target = self._extractor.current_fps

            except asyncio.CancelledError:
                logger.info("Camera %s task cancelled", self.camera_id)
                break
            except Exception as exc:
                self.stats.last_error = str(exc)[:200]
                self.stats.connected = False
                self.stats.reconnects += 1
                logger.warning(
                    "Camera %s error (reconnect #%d): %s, delay %.1fs",
                    self.camera_id,
                    self.stats.reconnects,
                    exc,
                    self._reconnect_delay,
                )
                if self.stats.reconnects == 1:
                    _publish_alert("stream_disconnected", self.camera_id, f"Stream disconnected: {exc}")
                elif self.stats.reconnects >= _MAX_RECONNECT_ATTEMPTS:
                    _publish_alert("stream_max_reconnect", self.camera_id, f"Max reconnects ({_MAX_RECONNECT_ATTEMPTS}) reached")
                    logger.error("Camera %s max reconnects reached, stopping", self.camera_id)
                    break
                elif self.stats.reconnects % 10 == 0:
                    _publish_alert("stream_reconnect_persistent", self.camera_id, f"Persistent reconnect (#{self.stats.reconnects})")
                await self._disconnect_reader()
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, _MAX_RECONNECT_DELAY
                )

        await self._disconnect_reader()
        self.stats.connected = False

    def _create_reader(self) -> StreamReader:
        if self.protocol == "rtsp":
            return RTSPStreamReader(self.camera_id, self.stream_url, self.target_fps)
        if self.protocol == "gb28181":
            return GB28181StreamReader(self.camera_id, self.stream_url, self.target_fps)
        raise ValueError(f"Unsupported protocol: {self.protocol}")

    async def _disconnect_reader(self) -> None:
        if self._reader is not None:
            try:
                await self._reader.disconnect()
            except Exception:
                pass
            self._reader = None
        if self._extractor is not None:
            self._extractor.reset()
            self._extractor = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name=f"cam-{self.camera_id}")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def get_info(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.stats.started_at
        return {
            "camera_id": self.camera_id,
            "url": self.stream_url,
            "protocol": self.protocol,
            "connected": self.stats.connected,
            "running": self.is_running,
            "frames_read": self.stats.frames_read,
            "frames_kept": self.stats.frames_kept,
            "fps_output": round(self.stats.fps_output, 2),
            "fps_target": round(self.stats.current_fps_target, 2),
            "reconnects": self.stats.reconnects,
            "uptime_seconds": round(elapsed, 1),
            "last_error": self.stats.last_error,
        }


class StreamManager:
    def __init__(self) -> None:
        self._sessions: dict[str, CameraSession] = {}

    async def add_stream(
        self,
        camera_id: str,
        stream_url: str,
        protocol: str = "rtsp",
        target_fps: float = 2.0,
    ) -> CameraSession:
        if camera_id in self._sessions:
            existing = self._sessions[camera_id]
            if existing.is_running:
                logger.warning("Stream %s already exists, skipping", camera_id)
                return existing
            del self._sessions[camera_id]

        session = CameraSession(camera_id, stream_url, protocol, target_fps)
        self._sessions[camera_id] = session
        session.start()
        logger.info(
            "Stream added: %s (%s, %s, %.1f fps)", camera_id, stream_url, protocol, target_fps
        )
        return session

    async def remove_stream(self, camera_id: str) -> bool:
        session = self._sessions.pop(camera_id, None)
        if session is None:
            return False
        await session.stop()
        logger.info("Stream removed: %s", camera_id)
        return True

    def get_session(self, camera_id: str) -> CameraSession | None:
        return self._sessions.get(camera_id)

    def list_streams(self) -> list[dict[str, Any]]:
        return [s.get_info() for s in self._sessions.values()]

    def stats(self) -> dict[str, Any]:
        active = sum(1 for s in self._sessions.values() if s.is_running)
        connected = sum(1 for s in self._sessions.values() if s.stats.connected)
        total_kept = sum(s.stats.frames_kept for s in self._sessions.values())
        return {
            "total_streams": len(self._sessions),
            "active_tasks": active,
            "connected": connected,
            "total_frames_kept": total_kept,
            "streams": self.list_streams(),
        }

    async def shutdown(self) -> None:
        ids = list(self._sessions.keys())
        for cid in ids:
            await self.remove_stream(cid)
        logger.info("StreamManager shut down, %d streams removed", len(ids))


_manager: StreamManager | None = None


def get_manager() -> StreamManager:
    global _manager
    if _manager is None:
        _manager = StreamManager()
    return _manager
