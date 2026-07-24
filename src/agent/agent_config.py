import logging

from src.agent.client import LLMClient, create_llm_client

logger = logging.getLogger(__name__)


class AgentConfigManager:
    """Manages the active LLM client instance, recreated on config change."""

    def __init__(self):
        self._client: LLMClient | None = None
        self._current_cfg: dict | None = None

    @property
    def client(self) -> LLMClient | None:
        return self._client

    def get_client(self) -> LLMClient:
        if self._client is None:
            self._client = create_llm_client()
        return self._client

    def apply_config(self, cfg: dict) -> LLMClient:
        llm_cfg = cfg.get("llm", {})
        provider = llm_cfg.get("provider", "openai")
        api_url = llm_cfg.get("url") or None
        api_key = llm_cfg.get("api_key") or None
        model_name = llm_cfg.get("model_name") or None

        old = self._client
        self._client = create_llm_client(
            provider=provider,
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
        )
        self._current_cfg = dict(cfg)

        if old is not None:
            try:
                import asyncio
                asyncio.ensure_future(old.aclose())
            except Exception:
                pass

        logger.info(
            "LLM client recreated: provider=%s url=%s model=%s",
            provider, api_url or "?", getattr(self._client, "model_name", "?"),
        )
        return self._client

_config_manager = AgentConfigManager()


def get_config_manager() -> AgentConfigManager:
    return _config_manager
