import logging

import httpx

logger = logging.getLogger(__name__)


class ZLMediaKitClient:
    def __init__(self, base_url: str = "http://localhost:8080", secret: str = "", client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def add_stream_proxy(self, app: str, stream: str, url: str) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/index/api/addStreamProxy",
            params={"secret": self.secret},
            json={"app": app, "stream": stream, "url": url},
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info("Stream proxy added: %s/%s -> %s", app, stream, url)
        return result

    async def close_stream_proxy(self, app: str, stream: str) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/index/api/close_stream",
            params={"secret": self.secret},
            json={"app": app, "stream": stream},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_media_list(self, app: str, stream: str) -> list:
        resp = await self._client.get(
            f"{self.base_url}/index/api/getMediaList",
            params={"secret": self.secret, "app": app, "stream": stream},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def close(self) -> None:
        await self._client.aclose()
