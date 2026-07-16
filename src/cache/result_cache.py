import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class CacheResult:
    result: dict
    created_at: float
    context_hash: str


class ResultCache:
    def __init__(
        self,
        redis_client,
        ttl: int = 60,
        threshold: int = 8,
        max_candidates: int = 20,
    ):
        self.redis = redis_client
        self.ttl = ttl
        self.threshold = threshold
        self.max_candidates = max_candidates

    async def get(
        self,
        camera_id: str,
        frame_hash: str,
        context_hash: str = "",
    ) -> CacheResult | None:
        if self.redis is None:
            return None
        exact_key = f"cache:result:{camera_id}:{frame_hash}"
        raw = await self.redis.get(exact_key)
        if raw:
            try:
                data = json.loads(raw)
                if data.get("context_hash", "") == context_hash:
                    await self.redis.incr("cache:stats:hits")
                    return CacheResult(**data)
            except (json.JSONDecodeError, TypeError):
                pass

        from src.cache.frame_hasher import FrameHasher
        hasher = FrameHasher()

        candidates = await self.redis.zrangebyscore(
            f"cache:camera:{camera_id}:hashes",
            time.time() - self.ttl,
            time.time(),
            start=0,
            num=self.max_candidates,
        )
        for member in candidates:
            if isinstance(member, bytes):
                member = member.decode()
            parts = member.split(":", 1)
            if len(parts) < 2:
                continue
            cand_hash, cand_ctx = parts
            if cand_ctx != context_hash:
                continue
            dist = hasher.hamming_distance(frame_hash, cand_hash)
            if dist <= self.threshold:
                hit_raw = await self.redis.get(
                    f"cache:result:{camera_id}:{cand_hash}"
                )
                if hit_raw:
                    try:
                        data = json.loads(hit_raw)
                        await self.redis.incr("cache:stats:hits")
                        return CacheResult(**data)
                    except (json.JSONDecodeError, TypeError):
                        pass

        await self.redis.incr("cache:stats:misses")
        return None

    async def set(
        self,
        camera_id: str,
        frame_hash: str,
        result: dict,
        context_hash: str = "",
    ) -> None:
        if self.redis is None:
            return
        entry = CacheResult(
            result=result,
            created_at=time.time(),
            context_hash=context_hash,
        )
        exact_key = f"cache:result:{camera_id}:{frame_hash}"
        await self.redis.set(exact_key, json.dumps(asdict(entry)), ex=self.ttl)
        camera_set_key = f"cache:camera:{camera_id}:hashes"
        await self.redis.zadd(
            camera_set_key, {f"{frame_hash}:{context_hash}": time.time()}
        )
        await self.redis.expire(camera_set_key, self.ttl)

    async def get_stats(self) -> dict:
        if self.redis is None:
            return {"hits": 0, "misses": 0, "total": 0, "hit_rate": 0.0}
        hits = int(await self.redis.get("cache:stats:hits") or 0)
        misses = int(await self.redis.get("cache:stats:misses") or 0)
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": round(hits / total, 4) if total > 0 else 0.0,
        }
