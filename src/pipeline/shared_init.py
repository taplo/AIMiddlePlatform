import logging

from src.pipeline.aggregate_handler import aggregate_handler
from src.pipeline.condition_handler import condition_handler
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry

logger = logging.getLogger(__name__)


def register_default_pipelines(registry: PipelineRegistry) -> None:
    pipelines = {
        "plate_recognition": [DAGNode("detect_plate", NodeType.MODEL_INFERENCE, config={"model": "license_plate"})],
        "object_detection": [DAGNode("detect_objects", NodeType.MODEL_INFERENCE, config={"model": "object_detection"})],
        "face_recognition": [DAGNode("detect_faces", NodeType.MODEL_INFERENCE, config={"model": "face_recognition"})],
        "vehicle_detection": [DAGNode("detect_vehicles", NodeType.MODEL_INFERENCE, config={"model": "vehicle_detection"})],
        "ocr": [DAGNode("ocr_text", NodeType.MODEL_INFERENCE, config={"model": "ocr"})],
    }
    for name, nodes in pipelines.items():
        dag = DAGDefinition(name=name)
        for n in nodes:
            dag.add_node(n)
        registry.register(name, dag)


def register_dag_handlers(executor: DAGExecutor) -> None:
    executor.register_handler(NodeType.AGGREGATE, aggregate_handler)
    executor.register_handler(NodeType.CONDITION, condition_handler)
