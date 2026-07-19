import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from src.pipeline.dag import DAGDefinition, NodeType
from src.resilience.circuit_breaker import get_circuit_breaker
from src.resilience.retry import retry_with_backoff

_NODE_TIMEOUT = 30.0

logger = logging.getLogger(__name__)

NodeHandler = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Any]


class DAGExecutor:
    def __init__(self) -> None:
        self._handlers: dict[NodeType, NodeHandler] = {}

    def register_handler(self, node_type: NodeType, handler: NodeHandler) -> None:
        self._handlers[node_type] = handler

    async def execute(self, dag: DAGDefinition, context: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()
        results: dict[str, Any] = {}
        completed: set[str] = set()
        pending = set(dag.nodes.keys())

        while pending:
            ready = [
                nid for nid in pending
                if all(dep in completed for dep in dag.nodes[nid].depends_on)
            ]
            if not ready:
                logger.error("Cycle detected in DAG %s", dag.name)
                break

            tasks = []
            for nid in ready:
                node = dag.nodes[nid]
                handler = self._handlers.get(node.node_type)
                if handler is None:
                    logger.warning("No handler for %s (%s)", nid, node.node_type)
                    results[nid] = None
                    completed.add(nid)
                    pending.discard(nid)
                    continue

                async def run(nid: str, handler: NodeHandler) -> None:
                    input_data = {dep: results[dep] for dep in dag.nodes[nid].depends_on}
                    cb = get_circuit_breaker(f"node:{nid}", failure_threshold=3, recovery_timeout=30.0)
                    try:
                        async def _invoke():
                            if inspect.iscoroutinefunction(handler):
                                return await asyncio.wait_for(
                                    handler(context, input_data, dag.nodes[nid].config),
                                    timeout=_NODE_TIMEOUT,
                                )
                            return await asyncio.wait_for(
                                asyncio.to_thread(handler, context, input_data, dag.nodes[nid].config),
                                timeout=_NODE_TIMEOUT,
                            )
                        result = await cb.call(_invoke)
                        results[nid] = result
                        completed.add(nid)
                    except (asyncio.TimeoutError, Exception):
                        results[nid] = None
                        completed.add(nid)

                tasks.append(run(nid, handler))

            await asyncio.gather(*tasks)
            for nid in ready:
                pending.discard(nid)

        elapsed = time.monotonic() - start
        logger.info("DAG %s executed in %.0fms", dag.name, elapsed * 1000)
        try:
            from src.monitoring.metrics import dag_execution_latency, dag_execution_total
            dag_execution_total.labels(dag_name=dag.name, status="success").inc()
            dag_execution_latency.labels(dag_name=dag.name).observe(elapsed)
        except Exception:
            pass
        return results
