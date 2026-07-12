import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import init_db, Rule, RuleBinding, Alert


@pytest.mark.asyncio
async def test_extract_detections_all_detections() -> None:
    from src.worker import _extract_detections
    result = {"all_detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]}
    dets = _extract_detections(result)
    assert len(dets) == 1
    assert dets[0]["label"] == "person"


@pytest.mark.asyncio
async def test_extract_detections_node_results() -> None:
    from src.worker import _extract_detections
    result = {"node1": {"detections": [{"label": "car", "bbox": [0, 0, 1, 1]}]}}
    dets = _extract_detections(result)
    assert len(dets) == 1
    assert dets[0]["label"] == "car"


@pytest.mark.asyncio
async def test_extract_detections_empty() -> None:
    from src.worker import _extract_detections
    assert _extract_detections({}) == []
    assert _extract_detections(None) == []


@pytest.mark.asyncio
async def test_evaluate_rules_triggers_alert() -> None:
    from src.worker import _evaluate_rules_for_task

    db = await init_db("sqlite+aiosqlite:///:memory:")

    async with AsyncSession(db) as session:
        rule = Rule(
            name="test_rule",
            rule_type="count_threshold",
            config='{"min":0,"max":2,"direction":"above"}',
            enabled=True,
        )
        session.add(rule)
        await session.flush()
        saved_rule_id = rule.id

        binding = RuleBinding(rule_id=saved_rule_id, camera_id="cam-test", enabled=True)
        session.add(binding)
        await session.commit()

    await _evaluate_rules_for_task(db, "task-1", "cam-test", {
        "all_detections": [
            {"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9},
            {"label": "person", "bbox": [2, 2, 3, 3], "confidence": 0.8},
            {"label": "person", "bbox": [4, 4, 5, 5], "confidence": 0.7},
        ]
    })

    async with AsyncSession(db) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].task_id == "task-1"
        assert alerts[0].rule_id == saved_rule_id
        assert alerts[0].alert_type == "count_threshold"


@pytest.mark.asyncio
async def test_evaluate_rules_skips_camera_mismatch() -> None:
    from src.worker import _evaluate_rules_for_task

    db = await init_db("sqlite+aiosqlite:///:memory:")

    async with AsyncSession(db) as session:
        rule = Rule(
            name="test_rule",
            rule_type="count_threshold",
            config='{"min":0,"max":2,"direction":"above"}',
            enabled=True,
        )
        session.add(rule)
        await session.flush()
        saved_rule_id = rule.id

        binding = RuleBinding(rule_id=saved_rule_id, camera_id="cam-other", enabled=True)
        session.add(binding)
        await session.commit()

    await _evaluate_rules_for_task(db, "task-1", "cam-test", {
        "all_detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]
    })

    async with AsyncSession(db) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 0


@pytest.mark.asyncio
async def test_evaluate_rules_dedup() -> None:
    from src.worker import _evaluate_rules_for_task

    db = await init_db("sqlite+aiosqlite:///:memory:")

    async with AsyncSession(db) as session:
        rule = Rule(
            name="test_rule",
            rule_type="count_threshold",
            config='{"min":0,"max":2,"direction":"above"}',
            enabled=True,
        )
        session.add(rule)
        await session.flush()
        saved_rule_id = rule.id

        binding = RuleBinding(rule_id=saved_rule_id, camera_id="cam-test", enabled=True)
        session.add(binding)
        await session.flush()
        saved_binding_id = binding.id

        # Insert a pre-existing alert to simulate dedup
        existing = Alert(
            task_id="task-1",
            alert_type="count_threshold",
            label="test_rule",
            confidence=0.9,
            rule_id=saved_rule_id,
            binding_id=saved_binding_id,
        )
        session.add(existing)
        await session.commit()

    await _evaluate_rules_for_task(db, "task-1", "cam-test", {
        "all_detections": [
            {"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9},
            {"label": "person", "bbox": [2, 2, 3, 3], "confidence": 0.8},
            {"label": "person", "bbox": [4, 4, 5, 5], "confidence": 0.7},
        ]
    })

    async with AsyncSession(db) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1


@pytest.mark.asyncio
async def test_evaluate_rules_disabled_rule() -> None:
    from src.worker import _evaluate_rules_for_task

    db = await init_db("sqlite+aiosqlite:///:memory:")

    async with AsyncSession(db) as session:
        rule = Rule(
            name="disabled_rule",
            rule_type="count_threshold",
            config='{"min":0,"max":2,"direction":"above"}',
            enabled=False,
        )
        session.add(rule)
        await session.flush()
        saved_rule_id = rule.id

        binding = RuleBinding(rule_id=saved_rule_id, camera_id="cam-test", enabled=True)
        session.add(binding)
        await session.commit()

    await _evaluate_rules_for_task(db, "task-1", "cam-test", {
        "all_detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]
    })

    async with AsyncSession(db) as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(alerts) == 0
