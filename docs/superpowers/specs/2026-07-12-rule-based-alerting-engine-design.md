# Rule-Based Alerting Engine Design

> 规则告警引擎：基于 CONDITION 节点 + 独立 Rule 注册表 + AGGREGATE 节点，实现区域入侵、逗留检测、数量阈值等告警规则。

## Status

- **Phase:** Design (pre-implementation)
- **Priority:** High (next deliverable after P0-P6)
- **Design Date:** 2026-07-12

## 1. Architecture

```
POST /v1/analyze/frame
  → FramePreprocessor
  → Redis Stream
  → Worker
      → FastPath (DAGExecutor)
          → MODEL_INFERENCE → [detections]
          → AGGREGATE       → [merged detections]
          → CONDITION       → [RuleEngine.evaluate() → Alert DB]
          → OUTPUT
      → Agent (fallback)
  → _save_result() [also evaluates rules and creates Alerts]
```

Two paths for alert creation:
- **DAG with CONDITION handler**: RuleEngine evaluates after AGGREGATE merges results; matched rules write Alert records immediately.
- **DAG without CONDITION / Agent path**: Worker `_save_result()` queries RuleBindings for the camera_id and evaluates rules as a fallback.

## 2. Data Models

### 2.1 Rule (rule definition)

```python
class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    rule_type: Mapped[str] = mapped_column(String(32))  # region_intrusion | loitering | count_threshold
    config: Mapped[str] = mapped_column(Text)  # JSON: polygon, thresholds, duration, etc.
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

**Rule types and their config structures:**

| rule_type | config fields |
|---|---|
| `region_intrusion` | `{"polygon": [[x1,y1],...,[xn,yn]], "alert_on": "enter"` / `"exit"` / `"both"` |
| `loitering` | `{"polygon": [[x1,y1],...,[xn,yn]], "duration_seconds": 30, "alert_on_enter": true}` |
| `count_threshold` | `{"polygon": [[...]]` (optional), `"min": 0, "max": 10, "direction": "above"` / `"below"` / `"within"` |

### 2.2 RuleBinding (rule → camera/scene assignment)

```python
class RuleBinding(Base):
    __tablename__ = "rule_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("rules.id", ondelete="CASCADE"))
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scene_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON partial overrides
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

Constraints: at least one of `camera_id` / `scene_type` must be non-null. When both are set, it's a refined binding for "this camera under this scene type". Binding resolution: (1) exact camera+scene match, (2) exact camera match, (3) exact scene match.

### 2.3 Alert extension

Add optional fields to existing Alert model:

```python
rule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rules.id"), nullable=True)
binding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: evaluation context
```

Backward compatible: existing quality_rejected alerts remain with null rule_id.

## 3. RuleEngine

### 3.1 Evaluation Signatures

```python
class RuleEngine:
    def evaluate(
        self,
        rule: Rule,
        binding: RuleBinding,
        camera_id: str,
        detections: list[Detection],
        frame_context: FrameContext,
        state: CameraRuleState,
    ) -> RuleEvaluationResult | None:
        """Evaluate a single rule against current frame detections.
        Returns None if no match, or RuleEvaluationResult if triggered."""
```

### 3.2 Rule Type Logic

#### region_intrusion

- Input: detection bboxes
- Check if centroid of each bbox falls inside the configured polygon (ray-casting)
- Compare against previous frame state: was the object already inside?
- `enter` → alert when object was outside and now inside
- `exit` → alert when object was inside and now outside
- Requires cross-frame tracking state per (camera_id, binding_id)

#### loitering

- Track objects inside the polygon with their entry timestamps
- When an object has been inside for >= `duration_seconds`, trigger alert
- Dedup: don't re-alert for same object until it leaves and re-enters

#### count_threshold

- Count number of objects inside polygon (or full frame if no polygon)
- Compare against min/max threshold
- `direction=above` → alert if count > max
- `direction=below` → alert if count < min
- `direction=within` → alert if count outside [min, max]
- Single-frame evaluation, no cross-frame state needed

### 3.3 Cross-Frame State Management

In-memory `CameraRuleState` singleton:

```python
@dataclass
class TrackedObject:
    track_id: str
    enter_time: float
    last_seen: float
    positions: list[tuple[float, float]]  # recent centroids

class CameraRuleState:
    _state: dict[tuple[str, int], dict[str, TrackedObject]]  # (camera_id, binding_id) → track_id → state

    def cleanup(self, max_age_seconds: float = 60):
        """Remove tracks not seen for max_age_seconds."""
```

TTL-based cleanup prevents memory leaks. State is ephemeral (lost on restart), which is acceptable — loitering/intrusion alerts will simply start fresh.

## 4. AGGREGATE Node Handler

Registered handler for `NodeType.AGGREGATE`:

- Accepts all upstream node outputs as `input_data` dict
- Merges all detection arrays into a flat list `all_detections`
- Optionally deduplicates by IoU threshold (config `deduplicate: true`)
- Optionally limits total count (config `max_detections: 500`)
- Returns `{"all_detections": [...], "by_source": {"node_id": [...], ...}}`

## 5. CONDITION Node Handler

Registered handler for `NodeType.CONDITION`:

```python
async def condition_handler(context, input_data, node_config):
    rule_refs = node_config.get("rule_refs", [])
    camera_id = context.get("camera_id")
    detections = input_data.get("all_detections", [])
    results = []
    for rule_id in rule_refs:
        # Load rule from DB/cache
        # Check if any active binding applies to this camera_id
        # RuleEngine.evaluate() — if triggered → write Alert → append to results
    return {"condition_results": results, "triggered": any(r.triggered for r in results)}
```

The handler also sets a flag in DAG context that downstream OUTPUT nodes can read for conditional branching.

## 6. Worker `_save_result()` Enhancement

Current: only creates Task record without parsing results.

Enhanced flow:

```
_save_result(task_id, camera_id, path_taken, results, context):
  1. Create/update Task record
  2. Parse results for detection data (union of all model outputs)
  3. Query active RuleBindings for this camera_id (cached, TTL 30s)
  4. For each binding → load Rule → RuleEngine.evaluate()
  5. Matched rules → create Alert records
  6. Dedup: skip if same (task_id, rule_id) already exists
```

## 7. API Routes

### Rule CRUD (`/api/v1/admin/rules`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/admin/rules` | List rules with filters (type, enabled) |
| POST | `/api/v1/admin/rules` | Create rule |
| GET | `/api/v1/admin/rules/{id}` | Get rule detail |
| PUT | `/api/v1/admin/rules/{id}` | Update rule |
| DELETE | `/api/v1/admin/rules/{id}` | Delete rule (cascades bindings) |

### RuleBinding CRUD (`/api/v1/admin/rule-bindings`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/admin/rule-bindings` | List bindings with filters (rule_id, camera_id, scene_type) |
| POST | `/api/v1/admin/rule-bindings` | Create binding |
| PUT | `/api/v1/admin/rule-bindings/{id}` | Update binding |
| DELETE | `/api/v1/admin/rule-bindings/{id}` | Delete binding |

### Batch operations

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/admin/rule-bindings/batch` | Batch create/update bindings (accepts JSON array or CSV) |
| POST | `/api/v1/admin/rule-bindings/import` | Import from CSV file |

## 8. Testing Strategy

| Layer | Focus | Test Count (est.) |
|---|---|---|
| Unit: RuleEngine | Each rule type: trigger cases, non-trigger cases, edge cases (empty detections, polygon edge) | ~12 |
| Unit: AGGREGATE handler | Merging, dedup, max limit | ~4 |
| Unit: CONDITION handler | Integration with RuleEngine, Alert DB write | ~4 |
| Unit: CameraRuleState | Tracking, TTL cleanup | ~4 |
| Unit: Binding resolution | Priority order, partial match | ~4 |
| API: Rule CRUD | CRUD + validation | ~6 |
| API: RuleBinding CRUD | CRUD + batch import | ~6 |
| Integration: Worker fallback | _save_result() with rules | ~3 |
| **Total** | | **~43** |

## 9. Implementation Order

1. **Data models** — Rule, RuleBinding, Alert migration (add rule_id/binding_id/metadata)
2. **RuleEngine** — Core evaluation logic (region_intrusion, loitering, count_threshold) + CameraRuleState
3. **AGGREGATE handler** — Register in DAGExecutor
4. **CONDITION handler** — Rule-based evaluation + Alert DB write + DAGExecutor registration
5. **Worker `_save_result()` enhancement** — Fallback rule evaluation + Alert creation
6. **API routes** — Rule CRUD, RuleBinding CRUD, batch import
7. **Testing** — All layers
