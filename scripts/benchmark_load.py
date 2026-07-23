#!/usr/bin/env python3
"""
全链路压力测试脚本 — 模拟多路摄像头并发提交帧，验证系统延迟约束。

用法:
  # 针对本地开发服务器（快速路径 + 128 路摄像头, 10s）
  python scripts/benchmark_load.py --cameras 128 --duration 10

  # 针对 Docker Compose 部署服务
  python scripts/benchmark_load.py --target http://localhost:8000 --cameras 500 --duration 60

  # 全量测试（快路径 + 健康检查混合）
  python scripts/benchmark_load.py --cameras 1000 --duration 120 --health-interval 5

约束验证:
  - 快速路径 p95 < 300ms
  - 健康检查 p95 < 300ms
  - 错误率 < 1%
"""

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from statistics import median

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("benchmark")


@dataclass
class CameraStats:
    camera_id: str
    sent: int = 0
    errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    status_codes: dict[int, int] = field(default_factory=dict)


@dataclass
class HealthStats:
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0


class LoadTest:
    def __init__(
        self,
        target: str,
        api_key: str,
        num_cameras: int,
        fps: float,
        duration: float,
        image_size: tuple[int, int],
        scene_type: str,
        health_interval: float,
        sync_ratio: float,
    ):
        self.target = target.rstrip("/")
        self.api_key = api_key
        self.num_cameras = num_cameras
        self.fps = fps
        self.duration = duration
        self.image_size = image_size
        self.scene_type = scene_type
        self.health_interval = health_interval
        self.sync_ratio = sync_ratio

        self._frame_b64: str | None = None
        self._camera_stats: dict[str, CameraStats] = {}
        self._health_stats = HealthStats()
        self._start_time: float = 0.0

    def _generate_frame(self) -> str:
        import base64

        import cv2
        import numpy as np
        w, h = self.image_size
        img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        cv2.rectangle(img, (w // 4, h // 4), (w * 3 // 4, h * 3 // 4), (0, 255, 0), 2)
        _, buf = cv2.imencode(".jpg", img)
        return base64.b64encode(buf).decode()

    async def _camera_loop(self, camera_id: str, client: httpx.AsyncClient):
        stat = CameraStats(camera_id=camera_id)
        self._camera_stats[camera_id] = stat
        interval = 1.0 / self.fps
        url = f"{self.target}/api/v1/analyze/frame"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        use_sync = camera_id.startswith("sync-")

        while time.monotonic() - self._start_time < self.duration:
            payload = {
                "frame": self._frame_b64,
                "camera_id": camera_id,
                "scene_type": self.scene_type,
                "model_id": "object_detection",
            }
            params = {"sync": "true"} if use_sync else {}
            start = time.monotonic()
            try:
                resp = await client.post(url, json=payload, headers=headers, params=params, timeout=30)
                elapsed = (time.monotonic() - start) * 1000
                stat.sent += 1
                stat.latencies_ms.append(elapsed)
                stat.status_codes[resp.status_code] = stat.status_codes.get(resp.status_code, 0) + 1
                if resp.status_code >= 400:
                    stat.errors += 1
            except Exception as e:
                stat.errors += 1
                logger.debug("Camera %s error: %s", camera_id, e)
            await asyncio.sleep(max(0, interval - (time.monotonic() - start)))

    async def _health_loop(self, client: httpx.AsyncClient):
        url = f"{self.target}/api/v1/health"
        headers = {"X-API-Key": self.api_key}
        while time.monotonic() - self._start_time < self.duration:
            start = time.monotonic()
            try:
                resp = await client.get(url, headers=headers, timeout=10)
                elapsed = (time.monotonic() - start) * 1000
                self._health_stats.latencies_ms.append(elapsed)
                if resp.status_code >= 400:
                    self._health_stats.errors += 1
            except Exception:
                self._health_stats.errors += 1
            await asyncio.sleep(self.health_interval)

    async def _progress_reporter(self):
        last_sent = 0
        while time.monotonic() - self._start_time < self.duration:
            await asyncio.sleep(2)
            elapsed = time.monotonic() - self._start_time
            total_sent = sum(s.sent for s in self._camera_stats.values())
            total_errors = sum(s.errors for s in self._camera_stats.values())
            throughput = (total_sent - last_sent) / 2
            last_sent = total_sent
            all_lats = [lat for s in self._camera_stats.values() for lat in s.latencies_ms[-50:]]
            p95 = sorted(all_lats)[int(len(all_lats) * 0.95)] if len(all_lats) > 20 else 0
            logger.info(
                "  %4.0fs | sent=%d err=%d | thr=%.0f req/s | p95=%.0fms",
                elapsed, total_sent, total_errors, throughput, p95,
            )

    async def run(self):
        self._frame_b64 = self._generate_frame()
        num_sync = max(1, int(self.num_cameras * self.sync_ratio))
        num_async = self.num_cameras - num_sync
        camera_ids = [f"sync-cam-{i:04d}" for i in range(num_sync)]
        camera_ids += [f"cam-{i:04d}" for i in range(num_async)]

        logger.info("=" * 60)
        logger.info("全链路压力测试")
        logger.info("=" * 60)
        logger.info("Target:       %s", self.target)
        logger.info("Cameras:      %d (async=%d, sync=%d)", self.num_cameras, num_async, num_sync)
        logger.info("Duration:     %.0fs", self.duration)
        logger.info("FPS:          %.1f/camera (total ~%.0f req/s)", self.fps, self.fps * self.num_cameras)
        logger.info("Image size:   %dx%d", self.image_size[0], self.image_size[1])
        logger.info("Health check: every %.0fs", self.health_interval)
        logger.info("-" * 60)

        limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
        async with httpx.AsyncClient(limits=limits, timeout=30) as client:
            self._start_time = time.monotonic()
            tasks = [asyncio.create_task(self._camera_loop(cid, client)) for cid in camera_ids]
            if self.health_interval > 0:
                tasks.append(asyncio.create_task(self._health_loop(client)))
            tasks.append(asyncio.create_task(self._progress_reporter()))
            await asyncio.sleep(self.duration)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return self._report()

    def _report(self) -> dict:
        all_lats = sorted([lat for s in self._camera_stats.values() for lat in s.latencies_ms])
        total_sent = sum(s.sent for s in self._camera_stats.values())
        total_errors = sum(s.errors for s in self._camera_stats.values())
        elapsed = time.monotonic() - self._start_time

        result = {
            "target": self.target,
            "num_cameras": self.num_cameras,
            "duration_seconds": round(elapsed, 1),
            "total_requests": total_sent,
            "total_errors": total_errors,
            "error_rate_pct": round(total_errors / max(total_sent, 1) * 100, 2),
            "throughput_req_per_sec": round(total_sent / max(elapsed, 0.1), 1),
            "latency_ms": {
                "min": round(all_lats[0], 1) if all_lats else 0,
                "p50": round(median(all_lats), 1) if all_lats else 0,
                "p95": round(sorted(all_lats)[int(len(all_lats) * 0.95)], 1) if len(all_lats) > 20 else 0,
                "p99": round(sorted(all_lats)[int(len(all_lats) * 0.99)], 1) if len(all_lats) > 100 else 0,
                "max": round(all_lats[-1], 1) if all_lats else 0,
                "avg": round(sum(all_lats) / len(all_lats), 1) if all_lats else 0,
            },
            "constraints": {
                "fast_path_p95_lt_300ms": None,
                "health_p95_lt_300ms": None,
                "error_rate_lt_1pct": None,
            },
            "health_check": {
                "total": len(self._health_stats.latencies_ms),
                "errors": self._health_stats.errors,
            },
            "status_codes": {},
        }

        for s in self._camera_stats.values():
            for code, count in s.status_codes.items():
                key = str(code)
                result["status_codes"][key] = result["status_codes"].get(key, 0) + count

        if all_lats:
            p95 = sorted(all_lats)[int(len(all_lats) * 0.95)]
            result["constraints"]["fast_path_p95_lt_300ms"] = p95 < 300
        if self._health_stats.latencies_ms:
            h_lats = sorted(self._health_stats.latencies_ms)
            h_p95 = h_lats[int(len(h_lats) * 0.95)]
            result["constraints"]["health_p95_lt_300ms"] = h_p95 < 300
            result["health_check"]["p95_ms"] = round(h_p95, 1)
        result["constraints"]["error_rate_lt_1pct"] = result["error_rate_pct"] < 1.0

        logger.info("-" * 60)
        logger.info("结果报告")
        logger.info("-" * 60)
        logger.info("Total requests: %d  Errors: %d (%.2f%%)", total_sent, total_errors, result["error_rate_pct"])
        logger.info("Throughput:     %.0f req/s", result["throughput_req_per_sec"])
        logger.info("Latency:        p50=%.1fms  p95=%.1fms  p99=%.1fms", result["latency_ms"]["p50"], result["latency_ms"]["p95"], result["latency_ms"]["p99"])
        logger.info("Constraints:")
        for k, v in result["constraints"].items():
            status = "PASS" if v is True else ("FAIL" if v is False else "N/A")
            logger.info("  %-40s %s", k, status)
        if self._health_stats.latencies_ms:
            h_p95 = sorted(self._health_stats.latencies_ms)[int(len(self._health_stats.latencies_ms) * 0.95)]
            logger.info("Health check:   %d calls, p95=%.1fms, %d errors", len(self._health_stats.latencies_ms), h_p95, self._health_stats.errors)
        logger.info("=" * 60)

        return result


def main():
    parser = argparse.ArgumentParser(description="AIMiddlePlatform 全链路压力测试")
    parser.add_argument("--target", default=os.getenv("BENCHMARK_TARGET", "http://localhost:8000"), help="目标服务 URL")
    parser.add_argument("--api-key", default=os.getenv("BENCHMARK_API_KEY", ""), help="API Key（默认从环境变量读取）")
    parser.add_argument("--cameras", type=int, default=int(os.getenv("BENCHMARK_CAMERAS", "100")), help="模拟摄像头数量")
    parser.add_argument("--duration", type=int, default=int(os.getenv("BENCHMARK_DURATION", "30")), help="测试持续时间（秒）")
    parser.add_argument("--fps", type=float, default=float(os.getenv("BENCHMARK_FPS", "1")), help="每路摄像头 FPS")
    parser.add_argument("--image-width", type=int, default=640, help="测试图像宽度")
    parser.add_argument("--image-height", type=int, default=480, help="测试图像高度")
    parser.add_argument("--scene", default="parking_lot", help="场景类型")
    parser.add_argument("--health-interval", type=float, default=5, help="健康检查间隔（秒），0 禁用")
    parser.add_argument("--sync-ratio", type=float, default=0.0, help="同步模式摄像头占比（0~1）")
    parser.add_argument("--output", default="", help="结果输出 JSON 路径")
    args = parser.parse_args()

    test = LoadTest(
        target=args.target,
        api_key=args.api_key,
        num_cameras=args.cameras,
        fps=args.fps,
        duration=args.duration,
        image_size=(args.image_width, args.image_height),
        scene_type=args.scene,
        health_interval=args.health_interval,
        sync_ratio=args.sync_ratio,
    )
    result = asyncio.run(test.run())

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("结果已保存至 %s", args.output)

    all_pass = all(v is True for v in result["constraints"].values() if v is not None)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
