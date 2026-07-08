from src.pipeline.dag import DAGDefinition


class PipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: dict[str, DAGDefinition] = {}

    def register(self, name: str, dag: DAGDefinition) -> None:
        self._pipelines[name] = dag

    def get(self, name: str) -> DAGDefinition | None:
        return self._pipelines.get(name)

    def list(self) -> list[str]:
        return list(self._pipelines.keys())

    def unregister(self, name: str) -> None:
        self._pipelines.pop(name, None)
