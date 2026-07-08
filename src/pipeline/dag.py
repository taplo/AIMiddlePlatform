from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(Enum):
    MODEL_INFERENCE = "model_inference"
    CONDITION = "condition"
    AGGREGATE = "aggregate"
    OUTPUT = "output"


@dataclass
class DAGNode:
    node_id: str
    node_type: NodeType
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class DAGDefinition:
    name: str
    nodes: dict[str, DAGNode] = field(default_factory=dict)
    entry_nodes: list[str] = field(default_factory=list)
    output_node: str = ""

    def add_node(self, node: DAGNode) -> None:
        self.nodes[node.node_id] = node

    def validate(self) -> bool:
        for node_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    return False
        return True
