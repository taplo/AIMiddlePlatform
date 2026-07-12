# 规则告警引擎实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 CONDITION 节点 + 独立 Rule 注册表 + AGGREGATE 节点，支持区域入侵、逗留检测、数量阈值三种告警规则，以及 Worker 兜底评估。

**Architecture:** Rule/Binding 数据模型存储在 SQLite/MySQL，RuleEngine 为核心评估引擎，CONDITION handler 和 Worker._save_result() 两条路径触发评估并写入 Alert 表。AGGREGATE handler 合并多模型检测结果为统一输入。CameraRuleState 内存跟踪跨帧状态。

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0 async, FastAPI, pytest, shapely (可选，用于多边形计算)

## Global Constraints

- 所有告警规则通过独立的 Rule 注册表管理，支持 CRUD API
- 规则绑定支持 camera_id、scene_type 维度，解析优先级: camera+scene > camera > scene
- 跨帧状态使用内存级 CameraRuleState 单例，TTL 60s 清理
- Alert 表兼容现有 quality_rejected 告警（rule_id 为 null）
- 实现顺序：模型 → 引擎 → 处理器 → Worker → API

---

## 文件结构

### 创建的文件

| 文件 | 职责 |
|---|---|
| `src/pipeline/rule_engine.py` | RuleEngine 核心评估逻辑、CameraRuleState 跨帧状态管理、Detection/RuleEvaluationResult 数据类 |
| `src/pipeline/aggregate_handler.py` | AGGREGATE 节点处理器 |
| `src/pipeline/condition_handler.py` | CONDITION 节点处理器 |
| `src/api/routes/rules.py` | Rule + RuleBinding CRUD API |
| `tests/test_rule_engine.py` | RuleEngine 单元测试 |
| `tests/test_aggregate_handler.py` | AGGREGATE handler 测试 |
| `tests/test_condition_handler.py` | CONDITION handler 测试 |
| `tests/test_rules_api.py` | Rule + RuleBinding API 测试 |

### 修改的文件

| 文件 | 修改内容 |
|---|---|
| `src/core/database.py` | 新增 Rule、RuleBinding 模型；Alert 增加 rule_id/binding_id/metadata 字段 |
| `alembic/versions/` | 新增迁移：创建 rules、rule_bindings 表 + Alert 加列 |
| `src/api/app.py` | 注册 AGGREGATE/CONDITION handler；include rules router |
| `src/worker.py` | `_save_result()` 增加规则评估 + Alert 创建逻辑 |

---

### Task 1: 数据模型 + 数据库迁移

**Files:**
- Modify: `src/core/database.py`
- Create: `alembic/versions/xxxx_add_rule_engine_tables.py`

**Interfaces:**
- Produces: `Rule(Base)`、`RuleBinding(Base)` ORM 模型；Alert 表增加 `rule_id`、`binding_id`、`metadata` 列

- [ ] **Step 1: 在 database.py 添加 Rule 模型**

在 `src/core/database.py` 中现有 Alert 模型之后添加：

```python
class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    rule_type: Mapped[str] = mapped_column(String(32))
    config: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 添加 RuleBinding 模型**

```python
class RuleBinding(Base):
    __tablename__ = "rule_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("rules.id", ondelete="CASCADE"))
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scene_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 3: Alert 模型增加字段**

在现有 Alert 模型中增加：

```python
rule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rules.id"), nullable=True)
binding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: 生成并编辑迁移文件**

```bash
cd src
alembic revision --autogenerate -m "add_rule_engine_tables"
```

编辑生成的迁移文件，确认创建了 rules、rule_bindings 表，并在 alerts 表增加了 rule_id、binding_id、metadata 列。

- [ ] **Step 5: 运行迁移并验证**

```bash
alembic upgrade head
```

验证：确认 rules、rule_bindings 表已创建，alerts 表有新增列。

- [ ] **Step 6: 提交**

```bash
git add src/core/database.py alembic/versions/
git commit -m "feat: add Rule, RuleBinding models + Alert extension"
```

---

### Task 2: RuleEngine 核心

**Files:**
- Create: `src/pipeline/rule_engine.py`
- Test: `tests/test_rule_engine.py`

**Interfaces:**
- Produces:
  - `Detection` dataclass
  - `RuleEvaluationResult` dataclass
  - `CameraRuleState` class: `get_or_create(camera_id, binding_id) -> dict`, `cleanup(max_age=60)`
  - `RuleEngine` class: `evaluate(rule, binding, camera_id, detections, state) -> RuleEvaluationResult | None`

- [ ] **Step 1: 编写 Detection 和 RuleEvaluationResult 数据类测试**

```python
# tests/test_rule_engine.py
from src.pipeline.rule_engine import Detection, RuleEvaluationResult


def test_detection_defaults() -> None:
    d = Detection(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.95, label="person")
    assert d.track_id is None


def test_detection_with_track_id() -> None:
    d = Detection(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.95, label="person", track_id="trk_001")
    assert d.track_id == "trk_001"


def test_rule_evaluation_result_fields() -> None:
    r = RuleEvaluationResult(
        triggered=True,
        rule_id=1,
        binding_id=1,
        camera_id="cam-1",
        rule_type="region_intrusion",
        matches=[{"track_id": "trk_001", "action": "enter"}],
        details={"polygon": [[0,0],[1,0],[1,1],[0,1]]},
    )
    assert r.triggered is True
```

- [ ] **Step 2: 实现数据类**

```python
# src/pipeline/rule_engine.py
from dataclasses import dataclass, field


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    label: str
    track_id: str | None = None

    def centroid(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)


@dataclass
class RuleEvaluationResult:
    triggered: bool
    rule_id: int
    binding_id: int
    camera_id: str
    rule_type: str
    matches: list[dict] = field(default_factory=list)
    details: dict = field(default_factory=dict)
```

- [ ] **Step 3: 运行测试验证通过**

```bash
pytest tests/test_rule_engine.py::test_detection_defaults tests/test_rule_engine.py::test_detection_with_track_id tests/test_rule_engine.py::test_rule_evaluation_result_fields -v
```

预期：PASS

- [ ] **Step 4: 编写 CameraRuleState 测试**

```python
# tests/test_rule_engine.py

def test_camera_rule_state_get_or_create() -> None:
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    assert isinstance(tracks, dict)
    assert len(tracks) == 0


def test_camera_rule_state_track_object() -> None:
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    tracks["trk_001"] = CameraRuleState.TrackedObject(
        track_id="trk_001", enter_time=100.0, last_seen=100.0, positions=[(0.5, 0.5)],
    )
    assert state.get_or_create("cam-1", 1)["trk_001"].track_id == "trk_001"


def test_camera_rule_state_separate_cameras() -> None:
    state = CameraRuleState()
    t1 = state.get_or_create("cam-1", 1)
    t2 = state.get_or_create("cam-2", 1)
    t1["trk_001"] = CameraRuleState.TrackedObject("trk_001", 0, 0, [(0, 0)])
    assert "trk_001" not in t2


def test_camera_rule_state_cleanup_removes_old() -> None:
    import time
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    tracks["old"] = CameraRuleState.TrackedObject("old", 0, 0, [(0, 0)])
    tracks["fresh"] = CameraRuleState.TrackedObject("fresh", time.time(), time.time(), [(0, 0)])
    state.cleanup(max_age_seconds=30)
    assert "old" not in state.get_or_create("cam-1", 1)
    assert "fresh" in state.get_or_create("cam-1", 1)
```

- [ ] **Step 5: 实现 CameraRuleState**

```python
import time
from dataclasses import dataclass, field


class CameraRuleState:
    @dataclass
    class TrackedObject:
        track_id: str
        enter_time: float
        last_seen: float
        positions: list[tuple[float, float]] = field(default_factory=list)

    def __init__(self) -> None:
        self._state: dict[tuple[str, int], dict[str, CameraRuleState.TrackedObject]] = {}

    def get_or_create(self, camera_id: str, binding_id: int) -> dict[str, "CameraRuleState.TrackedObject"]:
        key = (camera_id, binding_id)
        if key not in self._state:
            self._state[key] = {}
        return self._state[key]

    def cleanup(self, max_age_seconds: float = 60) -> None:
        now = time.time()
        for key in list(self._state.keys()):
            tracks = self._state[key]
            self._state[key] = {tid: t for tid, t in tracks.items() if now - t.last_seen <= max_age_seconds}
            if not self._state[key]:
                del self._state[key]
```

- [ ] **Step 6: 运行测试验证**

```bash
pytest tests/test_rule_engine.py::test_camera_rule_state_get_or_create tests/test_rule_engine.py::test_camera_rule_state_track_object tests/test_rule_engine.py::test_camera_rule_state_separate_cameras tests/test_rule_engine.py::test_camera_rule_state_cleanup_removes_old -v
```

预期：全部 PASS

- [ ] **Step 7: 编写 RuleEngine 测试**

```python
# tests/test_rule_engine.py

def test_point_in_polygon_inside() -> None:
    engine = RuleEngine()
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert engine.point_in_polygon((5, 5), polygon) is True


def test_point_in_polygon_outside() -> None:
    engine = RuleEngine()
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert engine.point_in_polygon((15, 15), polygon) is False


def test_region_intrusion_enter_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = Rule(id=1, name="test", rule_type="region_intrusion", config='{"polygon": [[0,0],[10,0],[10,10],[0,10]], "alert_on": "enter"}')
    binding = RuleBinding(id=1, rule_id=1, camera_id="cam-1", scene_type=None)
    detections = [Detection(bbox=(4, 4, 6, 6), confidence=0.9, label="person", track_id="trk_001")]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.rule_type == "region_intrusion"


def test_region_intrusion_no_repeat_trigger() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = Rule(id=1, name="test", rule_type="region_intrusion", config='{"polygon": [[0,0],[10,0],[10,10],[0,10]], "alert_on": "enter"}')
    binding = RuleBinding(id=1, rule_id=1, camera_id="cam-1", scene_type=None)
    detections = [Detection(bbox=(4, 4, 6, 6), confidence=0.9, label="person", track_id="trk_001")]
    engine.evaluate(rule, binding, "cam-1", detections, state)  # first trigger
    result = engine.evaluate(rule, binding, "cam-1", detections, state)  # second frame, still inside
    assert result is None  # no repeat


def test_count_threshold_above_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = Rule(id=2, name="test", rule_type="count_threshold", config='{"min": 0, "max": 2, "direction": "above"}')
    binding = RuleBinding(id=2, rule_id=2, camera_id="cam-1", scene_type=None)
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(5)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.details["count"] == 5
    assert result.details["threshold_max"] == 2


def test_count_threshold_below_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = Rule(id=3, name="test", rule_type="count_threshold", config='{"min": 3, "max": 100, "direction": "below"}')
    binding = RuleBinding(id=3, rule_id=3, camera_id="cam-1", scene_type=None)
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(1)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.details["count"] == 1


def test_count_threshold_no_trigger() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = Rule(id=4, name="test", rule_type="count_threshold", config='{"min": 0, "max": 5, "direction": "within"}')
    binding = RuleBinding(id=4, rule_id=4, camera_id="cam-1", scene_type=None)
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(3)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is None
```

- [ ] **Step 8: 实现 RuleEngine**

```python
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RuleEngine:
    def point_in_polygon(self, point: tuple[float, float], polygon: list[list[float]]) -> bool:
        x, y = point
        inside = False
        n = len(polygon)
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
                inside = not inside
        return inside

    def evaluate(
        self,
        rule: Any,
        binding: Any,
        camera_id: str,
        detections: list[Detection],
        state: CameraRuleState,
    ) -> RuleEvaluationResult | None:
        config = json.loads(rule.config) if isinstance(rule.config, str) else rule.config
        binding_overrides = None
        if binding and binding.config_overrides:
            binding_overrides = json.loads(binding.config_overrides) if isinstance(binding.config_overrides, str) else binding.config_overrides
            if binding_overrides:
                config = {**config, **binding_overrides}

        if rule.rule_type == "region_intrusion":
            return self._eval_region_intrusion(rule.id, binding.id if binding else 0, camera_id, config, detections, state)
        elif rule.rule_type == "loitering":
            return self._eval_loitering(rule.id, binding.id if binding else 0, camera_id, config, detections, state)
        elif rule.rule_type == "count_threshold":
            return self._eval_count_threshold(rule.id, binding.id if binding else 0, camera_id, config, detections)
        return None

    def _eval_region_intrusion(
        self, rule_id: int, binding_id: int, camera_id: str,
        config: dict, detections: list[Detection], state: CameraRuleState,
    ) -> RuleEvaluationResult | None:
        polygon = config["polygon"]
        alert_on = config.get("alert_on", "enter")
        tracks = state.get_or_create(camera_id, binding_id)
        current_ids = set()
        matches = []

        for det in detections:
            tid = det.track_id or f"anon_{id(det)}"
            current_ids.add(tid)
            cp = det.centroid()
            inside = self.point_in_polygon(cp, polygon)
            was_inside = tid in tracks

            if inside:
                if tid not in tracks:
                    tracks[tid] = CameraRuleState.TrackedObject(tid, time.time(), time.time(), [cp])
                    if alert_on in ("enter", "both"):
                        matches.append({"track_id": tid, "action": "enter", "centroid": list(cp)})
                else:
                    tracks[tid].last_seen = time.time()
                    tracks[tid].positions.append(cp)
            else:
                if was_inside:
                    del tracks[tid]
                    if alert_on in ("exit", "both"):
                        matches.append({"track_id": tid, "action": "exit", "centroid": list(cp)})

        state.cleanup(max_age_seconds=60)
        if matches:
            return RuleEvaluationResult(True, rule_id, binding_id, camera_id, "region_intrusion", matches, {"polygon": polygon})
        return None

    def _eval_loitering(
        self, rule_id: int, binding_id: int, camera_id: str,
        config: dict, detections: list[Detection], state: CameraRuleState,
    ) -> RuleEvaluationResult | None:
        polygon = config["polygon"]
        duration = config.get("duration_seconds", 30)
        alert_on_enter = config.get("alert_on_enter", True)
        tracks = state.get_or_create(camera_id, binding_id)
        current_ids = set()
        now = time.time()
        matches = []

        for det in detections:
            tid = det.track_id or f"anon_{id(det)}"
            current_ids.add(tid)
            cp = det.centroid()
            inside = self.point_in_polygon(cp, polygon)

            if inside:
                if tid not in tracks:
                    tracks[tid] = CameraRuleState.TrackedObject(tid, now, now, [cp])
                else:
                    tracks[tid].last_seen = now
                    tracks[tid].positions.append(cp)
                    if now - tracks[tid].enter_time >= duration:
                        if not tracks[tid].positions or tracks[tid].positions[-1] != ("alerted",):
                            tracks[tid].positions.append(("alerted",))
                            matches.append({"track_id": tid, "centroid": list(cp), "duration_seconds": round(now - tracks[tid].enter_time, 1)})
            else:
                tracks.pop(tid, None)

        for tid in list(tracks.keys()):
            if tid not in current_ids:
                if now - tracks[tid].last_seen > 5:
                    tracks.pop(tid, None)

        state.cleanup(max_age_seconds=60)
        if matches:
            return RuleEvaluationResult(True, rule_id, binding_id, camera_id, "loitering", matches, {"duration_seconds": duration, "polygon": polygon})
        return None

    def _eval_count_threshold(
        self, rule_id: int, binding_id: int, camera_id: str,
        config: dict, detections: list[Detection],
    ) -> RuleEvaluationResult | None:
        polygon = config.get("polygon")
        min_count = config.get("min", 0)
        max_count = config.get("max", 999999)
        direction = config.get("direction", "above")

        if polygon:
            count = sum(1 for d in detections if self.point_in_polygon(d.centroid(), polygon))
        else:
            count = len(detections)

        triggered = False
        if direction == "above" and count > max_count:
            triggered = True
        elif direction == "below" and count < min_count:
            triggered = True
        elif direction == "within" and (count < min_count or count > max_count):
            triggered = True

        if triggered:
            details = {"count": count, "threshold_min": min_count, "threshold_max": max_count, "direction": direction}
            return RuleEvaluationResult(True, rule_id, binding_id, camera_id, "count_threshold", [], details)
        return None
```

- [ ] **Step 9: 运行 RuleEngine 测试**

```bash
pytest tests/test_rule_engine.py -v
```

预期：全部 PASS

- [ ] **Step 10: 提交**

```bash
git add src/pipeline/rule_engine.py tests/test_rule_engine.py
git commit -m "feat: RuleEngine + CameraRuleState with 3 rule types"
```

---

### Task 3: AGGREGATE + CONDITION 处理器

**Files:**
- Create: `src/pipeline/aggregate_handler.py`
- Create: `src/pipeline/condition_handler.py`
- Modify: `src/api/app.py` (注册 handler)
- Test: `tests/test_aggregate_handler.py`, `tests/test_condition_handler.py`

**Interfaces:**
- Consumes: `RuleEngine.evaluate()`, `CameraRuleState`, 来自 Task 2
- Produces: 注册到 `DAGExecutor` 的 handler

- [ ] **Step 1: 编写 AGGREGATE handler 测试**

```python
# tests/test_aggregate_handler.py
import pytest
from src.pipeline.aggregate_handler import aggregate_handler


@pytest.mark.asyncio
async def test_aggregate_merges_multiple_sources() -> None:
    result = await aggregate_handler(
        {"frame": b"fake", "camera_id": "cam-1"},
        {
            "detect_objects": {"detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]},
            "detect_faces": {"detections": [{"label": "face", "bbox": [0.1, 0.1, 0.3, 0.3], "confidence": 0.95}]},
        },
        {},
    )
    assert len(result["all_detections"]) == 2
    assert "by_source" in result


@pytest.mark.asyncio
async def test_aggregate_empty_input() -> None:
    result = await aggregate_handler({"frame": b"fake"}, {}, {})
    assert result["all_detections"] == []
    assert result["by_source"] == {}


@pytest.mark.asyncio
async def test_aggregate_respects_max_detections() -> None:
    result = await aggregate_handler(
        {"frame": b"fake"},
        {"src1": {"detections": [{"label": "x", "bbox": [0, 0, 1, 1], "confidence": 0.5}] * 10}},
        {"max_detections": 3},
    )
    assert len(result["all_detections"]) == 3
```

- [ ] **Step 2: 实现 AGGREGATE handler**

```python
# src/pipeline/aggregate_handler.py
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def aggregate_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    all_detections: list[dict] = []
    by_source: dict[str, list[dict]] = {}

    for source_key, source_value in input_data.items():
        if isinstance(source_value, dict):
            dets = source_value.get("detections", [])
            all_detections.extend(dets)
            by_source[source_key] = dets

    max_dets = node_config.get("max_detections")
    if max_dets is not None and len(all_detections) > max_dets:
        all_detections = all_detections[:max_dets]

    return {"all_detections": all_detections, "by_source": by_source}
```

- [ ] **Step 3: 运行 AGGREGATE 测试**

```bash
pytest tests/test_aggregate_handler.py -v
```

预期：全部 PASS

- [ ] **Step 4: 编写 CONDITION handler 测试**

```python
# tests/test_condition_handler.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipeline.condition_handler import condition_handler


@pytest.mark.asyncio
async def test_condition_no_rules() -> None:
    result = await condition_handler(
        {"camera_id": "cam-1"},
        {},
        {},
    )
    assert result["condition_results"] == []
    assert result["triggered"] is False


@pytest.mark.asyncio
async def test_condition_with_rule_trigger() -> None:
    mock_result = MagicMock()
    mock_result.triggered = True
    mock_result.rule_id = 1
    mock_result.binding_id = 1
    mock_result.camera_id = "cam-1"
    mock_result.rule_type = "region_intrusion"
    mock_result.matches = [{"track_id": "trk_001", "action": "enter"}]
    mock_result.details = {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}

    mock_db = AsyncMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [MagicMock(rule_id=1, camera_id="cam-1", scene_type=None)]
    mock_rule = MagicMock()
    mock_rule.id = 1
    mock_rule.rule_type = "region_intrusion"
    mock_rule.config = json.dumps({"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "alert_on": "enter"})
    mock_rule.severity = "high"
    mock_db.get.return_value = mock_rule

    with patch("src.pipeline.condition_handler.RuleEngine") as MockEngine, \
         patch("src.pipeline.condition_handler.CameraRuleState") as MockState, \
         patch("src.pipeline.condition_handler.AsyncSession") as MockSession:
        MockEngine.return_value.evaluate.return_value = mock_result
        MockSession.return_value.__aenter__.return_value = mock_db

        result = await condition_handler({"camera_id": "cam-1"}, {"all_detections": []}, {"rule_refs": [1]})
        assert result["triggered"] is True
        assert len(result["condition_results"]) == 1
```

- [ ] **Step 5: 实现 CONDITION handler**

```python
# src/pipeline/condition_handler.py
import json
import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Rule, RuleBinding, Alert
from src.pipeline.rule_engine import RuleEngine, CameraRuleState, Detection, RuleEvaluationResult

logger = logging.getLogger(__name__)

_rule_engine = RuleEngine()
_camera_state = CameraRuleState()


def _parse_detections(input_data: dict) -> list[dict]:
    all_dets = input_data.get("all_detections", [])
    if isinstance(all_dets, list):
        return all_dets
    return []


def _detection_to_objects(dets: list[dict]) -> list[Detection]:
    return [
        Detection(
            bbox=tuple(d["bbox"]),
            confidence=d.get("confidence", 0.0),
            label=d.get("label", "unknown"),
            track_id=d.get("track_id"),
        )
        for d in dets if isinstance(d, dict) and "bbox" in d
    ]


async def condition_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    rule_refs: list[int] = node_config.get("rule_refs", [])
    camera_id: str | None = context.get("camera_id")
    if not camera_id or not rule_refs:
        return {"condition_results": [], "triggered": False}

    detections = _detection_to_objects(_parse_detections(input_data))
    results: list[dict] = []

    async with AsyncSession(_get_session_factory()) as session:
        for rule_id in rule_refs:
            # Find active bindings for this camera_id
            stmt = select(RuleBinding).where(
                RuleBinding.rule_id == rule_id,
                RuleBinding.enabled == True,
            )
            result = await session.execute(stmt)
            bindings = result.scalars().all()

            # Filter bindings matching this camera
            matching_bindings = []
            for b in bindings:
                if b.camera_id == camera_id:
                    matching_bindings.append(b)
                elif b.camera_id is None and b.scene_type == context.get("scene_type"):
                    matching_bindings.append(b)
                elif b.camera_id is None and b.scene_type is None:
                    matching_bindings.append(b)

            if not matching_bindings:
                continue

            rule = await session.get(Rule, rule_id)
            if not rule or not rule.enabled:
                continue

            for binding in matching_bindings:
                eval_result = _rule_engine.evaluate(rule, binding, camera_id, detections, _camera_state)
                if eval_result and eval_result.triggered:
                    # Write Alert to DB
                    alert = Alert(
                        task_id=context.get("task_id", ""),
                        alert_type=eval_result.rule_type,
                        label=rule.name,
                        confidence=max((m.get("confidence", 1.0) for m in eval_result.matches), default=1.0),
                        verified_by="model",
                        status="pending",
                        rule_id=rule.id,
                        binding_id=binding.id,
                        metadata=json.dumps({"matches": eval_result.matches, "details": eval_result.details}),
                    )
                    session.add(alert)
                    results.append({
                        "rule_id": rule.id,
                        "binding_id": binding.id,
                        "rule_type": eval_result.rule_type,
                        "matches": eval_result.matches,
                        "details": eval_result.details,
                    })

        await session.commit()

    return {"condition_results": results, "triggered": len(results) > 0}


_session_factory = None


def init_session_factory(factory: Any) -> None:
    global _session_factory
    _session_factory = factory


def _get_session_factory() -> Any:
    return _session_factory
```

注意：需要在 `app.py` 中调用 `condition_handler.init_session_factory(factory)` 来初始化 session factory。

- [ ] **Step 6: 运行 CONDITION handler 测试（可能需要调整 mock）**

```bash
pytest tests/test_condition_handler.py -v
```

- [ ] **Step 7: 在 app.py 中注册 handler**

在 `src/api/app.py` 的 `_init_components()` 函数中增加：

```python
from src.pipeline.aggregate_handler import aggregate_handler
from src.pipeline.condition_handler import condition_handler as condition_handler_mod

executor.register_handler(NodeType.AGGREGATE, aggregate_handler)
executor.register_handler(NodeType.CONDITION, condition_handler_mod.condition_handler)
condition_handler_mod.init_session_factory(factory)
```

- [ ] **Step 8: 提交**

```bash
git add src/pipeline/aggregate_handler.py src/pipeline/condition_handler.py src/api/app.py tests/test_aggregate_handler.py tests/test_condition_handler.py
git commit -m "feat: AGGREGATE + CONDITION node handlers"
```

---

### Task 4: Worker `_save_result()` 增强

**Files:**
- Modify: `src/worker.py`
- Test: `tests/test_worker.py`（扩展现有测试，或在 `tests/test_worker_rules.py` 中新增）

**Interfaces:**
- Consumes: `RuleEngine.evaluate()`、`CameraRuleState`、Rule/RuleBinding 模型查询

- [ ] **Step 1: 编写 Worker 兜底测试**

```python
# tests/test_worker_rules.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.worker import _save_result


@pytest.mark.asyncio
async def test_save_result_evaluates_rules() -> None:
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_binding = MagicMock()
    mock_binding.id = 1
    mock_binding.rule_id = 1
    mock_binding.camera_id = "cam-1"
    mock_binding.scene_type = None

    mock_rule = MagicMock()
    mock_rule.id = 1
    mock_rule.rule_type = "count_threshold"
    mock_rule.config = json.dumps({"min": 0, "max": 2, "direction": "above"})
    mock_rule.enabled = True

    with patch("src.worker.AsyncSession", return_value=mock_session), \
         patch("src.worker.RuleEngine") as MockEngine, \
         patch("src.worker.CameraRuleState") as MockState:
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_binding]
        mock_session.get.return_value = mock_rule
        MockEngine.return_value.evaluate.return_value = None  # no trigger

        result = await _save_result(
            task_id="t1", camera_id="cam-1", path_taken="fast",
            results={"detections": [{"label": "person", "bbox": [0, 0, 1, 1], "confidence": 0.9}]},
            context={"camera_id": "cam-1"},
        )
        # Should not create alert
        mock_session.add.assert_not_called()
```

注意：你需要查看当前 `_save_result` 的实际签名和实现，确定如何注入规则评估逻辑。本测试假设 `_save_result` 被改造为异步并接收 results/context。

- [ ] **Step 2: 修改 Worker._save_result**

查看 `src/worker.py` 中现有 `_save_result` 的签名和实现，在其末尾增加规则评估逻辑：

```python
# 在 _save_result 中，创建 Task 记录之后：
async def _evaluate_rules_for_task(task_id, camera_id, results, context):
    """查询摄像头绑定的规则并评估。"""
    from src.pipeline.rule_engine import RuleEngine, CameraRuleState, Detection
    from src.core.database import Rule, RuleBinding, Alert

    engine = RuleEngine()
    state = CameraRuleState()
    
    # 从 results 提取 detections
    detections = _extract_detections(results)
    detection_objects = [
        Detection(bbox=tuple(d["bbox"]), confidence=d.get("confidence", 0.0),
                  label=d.get("label", "unknown"), track_id=d.get("track_id"))
        for d in detections if "bbox" in d
    ]

    async with AsyncSession(factory) as session:
        # 查询 camera_id 匹配的绑定
        stmt = select(RuleBinding).where(
            RuleBinding.enabled == True,
            (RuleBinding.camera_id == camera_id) | (RuleBinding.camera_id == None),
        )
        bindings = (await session.execute(stmt)).scalars().all()

        for binding in bindings:
            if binding.camera_id is not None and binding.camera_id != camera_id:
                continue
            if binding.camera_id is None and binding.scene_type and binding.scene_type != context.get("scene_type"):
                continue

            rule = await session.get(Rule, binding.rule_id)
            if not rule or not rule.enabled:
                continue

            result = engine.evaluate(rule, binding, camera_id, detection_objects, state)
            if result and result.triggered:
                # 去重：同一 (task_id, rule_id) 已存在则不重复
                dup = select(Alert).where(Alert.task_id == task_id, Alert.rule_id == rule.id)
                existing = (await session.execute(dup)).scalars().first()
                if existing:
                    continue
                
                alert = Alert(
                    task_id=task_id,
                    alert_type=result.rule_type,
                    label=rule.name,
                    confidence=1.0,
                    verified_by="model",
                    status="pending",
                    rule_id=rule.id,
                    binding_id=binding.id,
                    metadata=json.dumps({"matches": result.matches, "details": result.details}),
                )
                session.add(alert)
        
        await session.commit()
```

- [ ] **Step 3: 运行 Worker 测试确认现有行为不被破坏**

```bash
pytest tests/test_worker.py -v
```

- [ ] **Step 4: 提交**

```bash
git add src/worker.py tests/test_worker_rules.py
git commit -m "feat: worker fallback rule evaluation on _save_result"
```

---

### Task 5: API 路由

**Files:**
- Create: `src/api/routes/rules.py`
- Modify: `src/api/app.py`（include router）

**Interfaces:**
- Produces: REST API 端点

- [ ] **Step 1: 编写规则 CRUD API 测试**

```python
# tests/test_rules_api.py
import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)
_TEST_API_KEY = "sk-test-rules-api-key-00000001"


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=1000)
    yield


def _headers() -> dict:
    return {"X-API-Key": _TEST_API_KEY}


def _auth_headers(token: str | None = None) -> dict:
    if token:
        return {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    t = resp.json().get("access_token", "")
    return {"Authorization": f"Bearer {t}"}


def test_create_rule() -> None:
    resp = client.post(
        "/api/v1/admin/rules",
        json={"name": "区域入侵", "rule_type": "region_intrusion", "config": {"polygon": [[0,0],[10,0],[10,10],[0,10]], "alert_on": "enter"}, "severity": "high"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "区域入侵"


def test_list_rules() -> None:
    resp = client.get("/api/v1/admin/rules", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_rule() -> None:
    resp = client.get("/api/v1/admin/rules/1", headers=_auth_headers())
    assert resp.status_code in (200, 404)


def test_update_rule() -> None:
    resp = client.put(
        "/api/v1/admin/rules/1",
        json={"name": "更新规则", "enabled": False},
        headers=_auth_headers(),
    )
    assert resp.status_code in (200, 404)


def test_delete_rule() -> None:
    resp = client.delete("/api/v1/admin/rules/1", headers=_auth_headers())
    assert resp.status_code in (200, 404)


def test_create_rule_binding() -> None:
    resp = client.post(
        "/api/v1/admin/rule-bindings",
        json={"rule_id": 1, "camera_id": "cam-001", "enabled": True},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_id"] == "cam-001"


def test_list_rule_bindings() -> None:
    resp = client.get("/api/v1/admin/rule-bindings", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_filter_bindings_by_camera() -> None:
    resp = client.get("/api/v1/admin/rule-bindings?camera_id=cam-001", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: 实现 Rule/RuleBinding API**

```python
# src/api/routes/rules.py
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Rule, RuleBinding

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin-rules"])
_db_session_factory = None


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


async def get_session():
    from sqlalchemy.ext.asyncio import AsyncSession
    async with AsyncSession(_db_session_factory) as session:
        yield session


# --- Rule CRUD ---

@router.get("/rules")
async def list_rules(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Rule).order_by(Rule.id))
    return [{"id": r.id, "name": r.name, "rule_type": r.rule_type, "config": json.loads(r.config) if isinstance(r.config, str) else r.config,
             "severity": r.severity, "enabled": r.enabled, "description": r.description,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in result.scalars().all()]


@router.post("/rules", status_code=200)
async def create_rule(data: dict, session: AsyncSession = Depends(get_session)):
    rule = Rule(
        name=data["name"],
        rule_type=data["rule_type"],
        config=json.dumps(data["config"], ensure_ascii=False),
        severity=data.get("severity", "medium"),
        enabled=data.get("enabled", True),
        description=data.get("description"),
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return {"id": rule.id, "name": rule.name, "rule_type": rule.rule_type}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: int, session: AsyncSession = Depends(get_session)):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return {"id": rule.id, "name": rule.name, "rule_type": rule.rule_type,
            "config": json.loads(rule.config) if isinstance(rule.config, str) else rule.config,
            "severity": rule.severity, "enabled": rule.enabled, "description": rule.description}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, data: dict, session: AsyncSession = Depends(get_session)):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    if "name" in data: rule.name = data["name"]
    if "rule_type" in data: rule.rule_type = data["rule_type"]
    if "config" in data: rule.config = json.dumps(data["config"], ensure_ascii=False)
    if "severity" in data: rule.severity = data["severity"]
    if "enabled" in data: rule.enabled = data["enabled"]
    if "description" in data: rule.description = data["description"]
    await session.commit()
    return {"ok": True}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, session: AsyncSession = Depends(get_session)):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    await session.delete(rule)
    await session.commit()
    return {"ok": True}


# --- RuleBinding CRUD ---

@router.get("/rule-bindings")
async def list_bindings(camera_id: str = None, scene_type: str = None, rule_id: int = None, session: AsyncSession = Depends(get_session)):
    stmt = select(RuleBinding)
    if camera_id: stmt = stmt.where(RuleBinding.camera_id == camera_id)
    if scene_type: stmt = stmt.where(RuleBinding.scene_type == scene_type)
    if rule_id: stmt = stmt.where(RuleBinding.rule_id == rule_id)
    result = await session.execute(stmt.order_by(RuleBinding.id))
    return [{"id": b.id, "rule_id": b.rule_id, "camera_id": b.camera_id, "scene_type": b.scene_type,
             "enabled": b.enabled} for b in result.scalars().all()]


@router.post("/rule-bindings", status_code=200)
async def create_binding(data: dict, session: AsyncSession = Depends(get_session)):
    binding = RuleBinding(
        rule_id=data["rule_id"],
        camera_id=data.get("camera_id"),
        scene_type=data.get("scene_type"),
        config_overrides=json.dumps(data["config_overrides"], ensure_ascii=False) if data.get("config_overrides") else None,
        enabled=data.get("enabled", True),
    )
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    return {"id": binding.id, "rule_id": binding.rule_id, "camera_id": binding.camera_id}


@router.put("/rule-bindings/{binding_id}")
async def update_binding(binding_id: int, data: dict, session: AsyncSession = Depends(get_session)):
    binding = await session.get(RuleBinding, binding_id)
    if not binding:
        raise HTTPException(404, "RuleBinding not found")
    if "rule_id" in data: binding.rule_id = data["rule_id"]
    if "camera_id" in data: binding.camera_id = data["camera_id"]
    if "scene_type" in data: binding.scene_type = data["scene_type"]
    if "config_overrides" in data: binding.config_overrides = json.dumps(data["config_overrides"], ensure_ascii=False)
    if "enabled" in data: binding.enabled = data["enabled"]
    await session.commit()
    return {"ok": True}


@router.delete("/rule-bindings/{binding_id}")
async def delete_binding(binding_id: int, session: AsyncSession = Depends(get_session)):
    binding = await session.get(RuleBinding, binding_id)
    if not binding:
        raise HTTPException(404, "RuleBinding not found")
    await session.delete(binding)
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 3: 在 app.py 中 include 路由**

```python
from src.api.routes import rules as rules_route
app.include_router(rules_route.router)
# 在 _init_components 中
rules_route.init_db_session_factory(factory)
```

- [ ] **Step 4: 运行 API 测试**

```bash
pytest tests/test_rules_api.py -v
```

- [ ] **Step 5: 提交**

```bash
git add src/api/routes/rules.py src/api/app.py tests/test_rules_api.py
git commit -m "feat: Rule + RuleBinding CRUD API"
```

---

### Task 6: 集成测试 + 最终验证

**Files:**
- Run full test suite

- [ ] **Step 1: 运行所有测试**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

预期：全部 PASS，新增 ~43 个测试

- [ ] **Step 2: 提交最终状态**

```bash
git add -A
git commit -m "chore: full test suite green after rule engine implementation"
```
