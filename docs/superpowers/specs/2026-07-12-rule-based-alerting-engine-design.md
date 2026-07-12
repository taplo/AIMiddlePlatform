# 规则告警引擎设计

> 基于 CONDITION 节点 + 独立 Rule 注册表 + AGGREGATE 节点，实现区域入侵、逗留检测、数量阈值等告警规则。

## 状态

- **阶段:** 设计（实现前）
- **优先级:** 高（P0-P6 之后的下一个交付）
- **设计日期:** 2026-07-12

## 1. 整体架构

```
POST /v1/analyze/frame
  → FramePreprocessor
  → Redis Stream
  → Worker
      → FastPath (DAGExecutor)
          → MODEL_INFERENCE → [检测结果]
          → AGGREGATE       → [合并检测结果]
          → CONDITION       → [RuleEngine.evaluate() → 写入 Alert 表]
          → OUTPUT
      → Agent (fallback)
  → _save_result() [同时兜底评估规则并创建 Alert]
```

两条告警路径：
- **DAG 含 CONDITION handler**: AGGREGATE 合并多模型输出后，RuleEngine 当场评估；匹配则写入 Alert 表。
- **DAG 不含 CONDITION / Agent 路径**: Worker `_save_result()` 查询该 camera_id 绑定的规则，兜底评估并创建 Alert。

## 2. 数据模型

### 2.1 Rule（规则定义）

```python
class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))          # 规则名称
    rule_type: Mapped[str] = mapped_column(String(32))       # region_intrusion | loitering | count_threshold
    config: Mapped[str] = mapped_column(Text)                # JSON：多边形坐标、阈值、持续时间等
    severity: Mapped[str] = mapped_column(String(16), default="medium")  # low / medium / high / critical
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

**规则类型及 config 结构：**

| rule_type | config 字段 |
|---|---|
| `region_intrusion` | `{"polygon": [[x1,y1],...,[xn,yn]], "alert_on": "enter"` / `"exit"` / `"both"` |
| `loitering` | `{"polygon": [[x1,y1],...,[xn,yn]], "duration_seconds": 30, "alert_on_enter": true}` |
| `count_threshold` | `{"polygon": [[...]]` (可选), `"min": 0, "max": 10, "direction": "above"` / `"below"` / `"within"` |

### 2.2 RuleBinding（规则绑定）

```python
class RuleBinding(Base):
    __tablename__ = "rule_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("rules.id", ondelete="CASCADE"))
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scene_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 部分覆盖
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

约束：`camera_id` 和 `scene_type` 至少一个非空。两者都非空时表示"该场景下的该摄像头"的细化绑定。

绑定解析优先级：精确 camera+scene → 精确 camera → 精确 scene。

### 2.3 Alert 扩展

为现有 Alert 模型增加可选字段：

```python
rule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rules.id"), nullable=True)
binding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON：规则评估上下文
```

向后兼容：现有的 quality_rejected 告警保持 rule_id 为 null。

## 3. 规则引擎

### 3.1 评估接口

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
        """评估单条规则。返回 None（不匹配）或 RuleEvaluationResult（触发）。"""
```

### 3.2 规则类型逻辑

#### region_intrusion（区域入侵）

- 输入：目标检测框列表
- 对每个检测框，计算中心点与多边形的位置关系（ray-casting 算法）
- 与上一帧状态对比：之前不在区域内、当前在 → `enter` 触发；反之 → `exit` 触发
- 需要跨帧跟踪状态（per camera_id, binding_id）

#### loitering（逗留检测）

- 跟踪区域内目标及其进入时间戳
- 同一目标在区域内连续停留 >= `duration_seconds` 时触发告警
- 去重：同一目标离开并重新进入前不重复告警

#### count_threshold（数量阈值）

- 统计区域内（或全帧，如无 polygon）的目标数量
- 与 min/max 阈值比较：`above` 超过上限触发，`below` 低于下限触发，`within` 在范围外触发
- 单帧评估，无需跨帧状态

### 3.3 跨帧状态管理

内存级 `CameraRuleState` 单例：

```python
@dataclass
class TrackedObject:
    track_id: str
    enter_time: float
    last_seen: float
    positions: list[tuple[float, float]]  # 最近质心坐标序列

class CameraRuleState:
    _state: dict[tuple[str, int], dict[str, TrackedObject]]  # (camera_id, binding_id) → track_id → state

    def cleanup(self, max_age_seconds: float = 60):
        """移除超过 max_age_seconds 未出现的 track。"""
```

TTL 定期清理防止内存泄漏。状态是临时的（重启丢失），这对入侵/逗留可接受——重新开始跟踪即可。

## 4. AGGREGATE 节点处理器

注册为 `NodeType.AGGREGATE` 的处理程序：

- 接收所有上游节点的输出作为 `input_data` 字典
- 将所有检测数组合并为一个扁平列表 `all_detections`
- 可选按 IoU 阈值去重（`deduplicate: true`）
- 可选限制总数（`max_detections: 500`）
- 返回 `{"all_detections": [...], "by_source": {"node_id": [...], ...}}`

## 5. CONDITION 节点处理器

注册为 `NodeType.CONDITION` 的处理程序：

```python
async def condition_handler(context, input_data, node_config):
    rule_refs = node_config.get("rule_refs", [])
    camera_id = context.get("camera_id")
    detections = input_data.get("all_detections", [])
    results = []
    for rule_id in rule_refs:
        加载规则（DB/缓存）
        检查是否有绑定适用于此 camera_id
        RuleEngine.evaluate() — 触发 → 写入 Alert → 追加到 results
    return {"condition_results": results, "triggered": any(r.triggered for r in results)}
```

同时设置 DAG context 标记，下游 OUTPUT 节点可读取实现条件分支。

## 6. Worker `_save_result()` 增强

当前：只创建 Task，不解析检测结果。

增强后流程：

```
_save_result(task_id, camera_id, path_taken, results, context):
  1. 创建/更新 Task 记录
  2. 解析 results 提取检测数据（合并所有模型输出）
  3. 查询该 camera_id 启用的 RuleBinding（缓存，TTL 30s）
  4. 对每个绑定 → 加载 Rule → RuleEngine.evaluate()
  5. 匹配 → 创建 Alert 记录
  6. 去重：同一 (task_id, rule_id) 已存在则跳过
```

## 7. API 路由

### 规则 CRUD（`/api/v1/admin/rules`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/rules` | 列出规则（按类型、状态过滤） |
| POST | `/api/v1/admin/rules` | 创建规则 |
| GET | `/api/v1/admin/rules/{id}` | 规则详情 |
| PUT | `/api/v1/admin/rules/{id}` | 更新规则 |
| DELETE | `/api/v1/admin/rules/{id}` | 删除规则（级联绑定） |

### 规则绑定 CRUD（`/api/v1/admin/rule-bindings`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/rule-bindings` | 列出绑定（按 rule_id, camera_id, scene_type 过滤） |
| POST | `/api/v1/admin/rule-bindings` | 创建绑定 |
| PUT | `/api/v1/admin/rule-bindings/{id}` | 更新绑定 |
| DELETE | `/api/v1/admin/rule-bindings/{id}` | 删除绑定 |

### 批量操作

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/rule-bindings/batch` | 批量创建/更新绑定（接收 JSON 数组或 CSV） |
| POST | `/api/v1/admin/rule-bindings/import` | 从 CSV 文件导入 |

## 8. 测试策略

| 层次 | 重点 | 预估用例数 |
|---|---|---|
| 单元测试：RuleEngine | 每种规则类型的触发/不触发/边界情况 | ~12 |
| 单元测试：AGGREGATE handler | 合并、去重、上限限制 | ~4 |
| 单元测试：CONDITION handler | RuleEngine 集成、Alert DB 写入 | ~4 |
| 单元测试：CameraRuleState | 跟踪、TTL 清理 | ~4 |
| 单元测试：绑定解析 | 优先级顺序、部分匹配 | ~4 |
| API 测试：Rule CRUD | CRUD + 验证 | ~6 |
| API 测试：RuleBinding CRUD | CRUD + 批量导入 | ~6 |
| 集成测试：Worker 兜底 | _save_result() 规则评估 | ~3 |
| **合计** | | **~43** |

## 9. 实现顺序

1. **数据模型** — Rule、RuleBinding 表、Alert 迁移（加 rule_id/binding_id/metadata 字段）
2. **RuleEngine** — 核心评估逻辑（region_intrusion、loitering、count_threshold）+ CameraRuleState
3. **AGGREGATE handler** — 注册到 DAGExecutor
4. **CONDITION handler** — 规则评估 + Alert DB 写入 + 注册到 DAGExecutor
5. **Worker `_save_result()` 增强** — 兜底规则评估 + Alert 创建
6. **API 路由** — Rule CRUD、RuleBinding CRUD、批量导入
7. **测试** — 全层次覆盖
