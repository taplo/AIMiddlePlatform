import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Rule, RuleBinding, Alert
from src.pipeline.rule_engine import RuleEngine, CameraRuleState, Detection

logger = logging.getLogger(__name__)

_session_factory = None


def init_session_factory(factory):
    global _session_factory
    _session_factory = factory


async def condition_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    rule_refs: list[int] = node_config.get("rule_refs", [])
    camera_id = context.get("camera_id", "")
    task_id = context.get("task_id", "")

    if not rule_refs:
        return {"condition_results": [], "triggered": False}

    rule_engine = RuleEngine()
    camera_state = CameraRuleState()
    all_detections = input_data.get("all_detections", [])
    condition_results: list[dict] = []
    triggered = False

    async with AsyncSession(_session_factory) as session:
        for rule_id in rule_refs:
            stmt = select(RuleBinding).where(
                RuleBinding.rule_id == rule_id,
                RuleBinding.enabled == True,
            )
            result = await session.execute(stmt)
            bindings = result.scalars().all()

            for binding in bindings:
                if binding.camera_id and binding.camera_id != camera_id:
                    continue

                rule = await session.get(Rule, rule_id)
                if rule is None or not rule.enabled:
                    continue

                detections = [
                    Detection(
                        bbox=tuple(d["bbox"]),
                        confidence=d.get("confidence", 0.0),
                        label=d.get("label", ""),
                        track_id=d.get("track_id"),
                    )
                    for d in all_detections
                    if "bbox" in d
                ]

                eval_result = rule_engine.evaluate(rule, binding, camera_id, detections, camera_state)
                if eval_result and eval_result.triggered:
                    triggered = True
                    condition_results.append({
                        "rule_id": rule_id,
                        "binding_id": binding.id,
                        "rule_type": rule.rule_type,
                        "severity": rule.severity,
                        "matches": eval_result.matches,
                        "details": eval_result.details,
                    })
                    alert = Alert(
                        task_id=task_id,
                        alert_type=rule.rule_type,
                        label=rule.name,
                        bbox=json.dumps(eval_result.matches) if eval_result.matches else None,
                        confidence=max((d.confidence for d in detections), default=0.0),
                        verified_by="rule",
                        status="pending",
                        rule_id=rule.id,
                        binding_id=binding.id,
                        metadata_=json.dumps(eval_result.details),
                    )
                    session.add(alert)

        await session.commit()

    return {"condition_results": condition_results, "triggered": triggered}
