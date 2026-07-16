"""Integration tests for the rule-based alerting engine (end-to-end)."""
import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.database import Base, Rule, RuleBinding, Alert
from src.pipeline.condition_handler import condition_handler
from src.pipeline.aggregate_handler import aggregate_handler


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _count_rule_config(min_v=0, max_v=1, direction="above"):
    return json.dumps({"min": min_v, "max": max_v, "direction": direction})


@pytest.mark.asyncio
async def test_full_flow_rule_alert_created(db_engine):
    """Scenario 1: Create Rule -> Create Binding -> Submit frame -> Alert created."""
    from src.worker import _evaluate_rules_for_task

    async with AsyncSession(db_engine) as session:
        rule = Rule(name="count_rule", rule_type="count_threshold",
                    config=_count_rule_config(), enabled=True)
        session.add(rule)
        await session.flush()
        binding = RuleBinding(rule_id=rule.id, camera_id="cam-1", enabled=True)
        session.add(binding)
        await session.flush()
        rule_id, binding_id = rule.id, binding.id
        await session.commit()

    await _evaluate_rules_for_task(db_engine, "task-1", "cam-1", {
        "all_detections": [
            {"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9},
            {"label": "person", "bbox": [2, 2, 3, 3], "confidence": 0.8},
        ]
    })

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
        a = alerts[0]
        assert a.task_id == "task-1"
        assert a.rule_id == rule_id
        assert a.binding_id == binding_id
        assert a.alert_type == "count_threshold"
        assert a.verified_by == "model"
        assert a.status == "pending"


@pytest.mark.asyncio
async def test_aggregate_condition_flow(db_engine):
    """Scenario 2: AGGREGATE handler followed by CONDITION handler evaluates rules."""
    async with AsyncSession(db_engine) as session:
        rule = Rule(name="agg_rule", rule_type="count_threshold",
                    config=_count_rule_config(0, 1, "above"), enabled=True)
        session.add(rule)
        await session.flush()
        rule_id = rule.id
        binding = RuleBinding(rule_id=rule_id, camera_id="cam-agg", enabled=True)
        session.add(binding)
        await session.flush()
        await session.commit()

    async with AsyncSession(db_engine) as cond_session:
        agg_result = await aggregate_handler(
            {"camera_id": "cam-agg"},
            {
                "detect_objects": {
                    "detections": [{"label": "car", "bbox": [0, 0, 2, 2], "confidence": 0.9}]
                },
                "detect_faces": {
                    "detections": [{"label": "person", "bbox": [5, 5, 6, 6], "confidence": 0.95}]
                },
            },
            {},
        )
        assert len(agg_result["all_detections"]) == 2

        cond_result = await condition_handler(
            {"camera_id": "cam-agg", "scene_type": "", "task_id": "task-agg", "db_session": cond_session},
            {"all_detections": agg_result["all_detections"]},
            {"rule_refs": [rule_id]},
        )

        assert cond_result["triggered"] is True
        assert len(cond_result["condition_results"]) == 1
        cr = cond_result["condition_results"][0]
        assert cr["rule_id"] == rule_id
        assert cr["rule_type"] == "count_threshold"

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].task_id == "task-agg"
        assert alerts[0].verified_by == "rule"


@pytest.mark.asyncio
async def test_worker_fallback_rule_evaluation(db_engine):
    """Scenario 3: Worker fallback path evaluates rules and creates Alert."""
    from src.worker import _evaluate_rules_for_task

    async with AsyncSession(db_engine) as session:
        rule = Rule(name="fallback_rule", rule_type="count_threshold",
                    config=_count_rule_config(), enabled=True)
        session.add(rule)
        await session.flush()
        binding = RuleBinding(rule_id=rule.id, camera_id="cam-fb", enabled=True)
        session.add(binding)
        await session.flush()
        await session.commit()

    await _evaluate_rules_for_task(db_engine, "task-fb", "cam-fb", {
        "all_detections": [
            {"label": "dog", "bbox": [0, 0, 1, 1], "confidence": 0.85},
            {"label": "cat", "bbox": [2, 2, 3, 3], "confidence": 0.75},
        ]
    })

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1


@pytest.mark.asyncio
async def test_disabled_rule_no_alert(db_engine):
    """Scenario 4: Disabled rule produces no alert."""
    from src.worker import _evaluate_rules_for_task

    async with AsyncSession(db_engine) as session:
        rule = Rule(name="disabled_rule", rule_type="count_threshold",
                    config=_count_rule_config(), enabled=False)
        session.add(rule)
        await session.flush()
        binding = RuleBinding(rule_id=rule.id, camera_id="cam-1", enabled=True)
        session.add(binding)
        await session.flush()
        await session.commit()

    await _evaluate_rules_for_task(db_engine, "task-4", "cam-1", {
        "all_detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]
    })

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 0


@pytest.mark.asyncio
async def test_camera_mismatch_no_alert(db_engine):
    """Scenario 5: Camera mismatch suppresses alert."""
    from src.worker import _evaluate_rules_for_task

    async with AsyncSession(db_engine) as session:
        rule = Rule(name="mismatch_rule", rule_type="count_threshold",
                    config=_count_rule_config(), enabled=True)
        session.add(rule)
        await session.flush()
        binding = RuleBinding(rule_id=rule.id, camera_id="cam-other", enabled=True)
        session.add(binding)
        await session.flush()
        await session.commit()

    await _evaluate_rules_for_task(db_engine, "task-5", "cam-1", {
        "all_detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]
    })

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 0


@pytest.mark.asyncio
async def test_dedup_same_task_id(db_engine):
    """Scenario 6: Same task_id submitted twice produces only one Alert."""
    from src.worker import _evaluate_rules_for_task

    async with AsyncSession(db_engine) as session:
        rule = Rule(name="dedup_rule", rule_type="count_threshold",
                    config=_count_rule_config(), enabled=True)
        session.add(rule)
        await session.flush()
        binding = RuleBinding(rule_id=rule.id, camera_id="cam-1", enabled=True)
        session.add(binding)
        await session.flush()
        await session.commit()

    detections = {
        "all_detections": [
            {"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9},
            {"label": "person", "bbox": [2, 2, 3, 3], "confidence": 0.8},
        ]
    }

    await _evaluate_rules_for_task(db_engine, "task-6", "cam-1", detections)
    await _evaluate_rules_for_task(db_engine, "task-6", "cam-1", detections)

    async with AsyncSession(db_engine) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
