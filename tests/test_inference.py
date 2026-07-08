import pytest

from src.models.registry import ModelRegistry, ModelSpec
from src.models.inference import InferenceOrchestrator, ModelAdapter


class StubAdapter(ModelAdapter):
    async def predict(self, spec, input_data):
        return {"stub_result": "ok"}


@pytest.mark.asyncio
async def test_infer_online_model() -> None:
    registry = ModelRegistry()
    spec = ModelSpec(model_id="stub", name="Stub", version="1.0.0")
    registry.register(spec)

    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())

    result = await orchestrator.infer("stub", {"image": "data"})
    assert result["model_id"] == "stub"
    assert result["output"]["stub_result"] == "ok"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_infer_offline_model_raises() -> None:
    registry = ModelRegistry()
    from src.models.registry import ModelStatus
    spec = ModelSpec(model_id="offline", name="Off", version="1.0.0",
                     status=ModelStatus.OFFLINE)
    registry.register(spec)

    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())

    with pytest.raises(ValueError, match="not online"):
        await orchestrator.infer("offline", {})


@pytest.mark.asyncio
async def test_infer_unknown_model_raises() -> None:
    orchestrator = InferenceOrchestrator(ModelRegistry())
    with pytest.raises(ValueError, match="not found"):
        await orchestrator.infer("unknown", {})


@pytest.mark.asyncio
async def test_infer_no_adapter_raises() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="m", name="M", version="1.0.0",
                                backend="custom"))
    orchestrator = InferenceOrchestrator(registry)
    with pytest.raises(ValueError, match="No adapter"):
        await orchestrator.infer("m", {})


@pytest.mark.asyncio
async def test_parallel_inference() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="a", name="A", version="1.0.0"))
    registry.register(ModelSpec(model_id="b", name="B", version="1.0.0"))

    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())

    results = await orchestrator.infer_parallel([("a", {}), ("b", {})])
    assert len(results) == 2
    assert all(r["model_id"] in ("a", "b") for r in results)
