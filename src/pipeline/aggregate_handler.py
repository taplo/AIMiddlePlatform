import logging

logger = logging.getLogger(__name__)


async def aggregate_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    max_detections = node_config.get("max_detections")
    all_detections: list = []
    by_source: dict[str, list] = {}

    for source_id, source_data in input_data.items():
        dets = source_data.get("detections", [])
        if max_detections is not None:
            remaining = max_detections - len(all_detections)
            if remaining <= 0:
                break
            dets = dets[:remaining]
        all_detections.extend(dets)
        by_source[source_id] = source_data.get("detections", [])

    return {"all_detections": all_detections, "by_source": by_source}
