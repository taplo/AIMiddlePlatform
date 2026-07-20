import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def retry_with_backoff(
    fn,
    max_retries: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except retryable_exceptions as e:
            last_exc = e
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if jitter:
                    delay *= 1 + random.random() * 0.5
                logger.warning(
                    "Retry %d/%d failed: %s, backing off %.2fs",
                    attempt + 1, max_retries, e, delay,
                )
                await asyncio.sleep(delay)
    raise last_exc
