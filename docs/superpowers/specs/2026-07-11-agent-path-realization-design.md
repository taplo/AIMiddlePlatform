# P2: Agent 路径真实化 — 设计文档

## 1. 目标

将 `QwenVLClient` 从 stub 替换为真实的 HTTP 调用（OpenAI 兼容接口），配合 CV 领域提示词和结构化输出解析，使 Agent 路径具备实际的场景理解能力。

## 2. 范围

### 包含
- LLM 配置项：api_url / api_key / model_name / timeout / max_retries
- `QwenVLClient` 真实 HTTP 实现（httpx.AsyncClient）
- `CVAgent` CV 领域提示词 + JSON 模式 + tool_calls 降级
- `DeepSeekVLClient` 同步更新
- Worker 中 Agent 路径的真实帧处理
- 全部现有测试继续通过

### 不包含
- 流式 tool_call (P2+)
- 多轮对话
- vLLM / TGI 本地部署
- VERIFY 节点 (P3)
- API 规范化 (P5)

## 3. 架构

```
POST /v1/analyze/frame + ?sync=true
        │
        ▼
AgentOrchestrator.process()
        │
        ├── FastPath 命中 → 返回结果 (已有)
        │
        └── FastPath 未命中 ──► CVAgent.analyze_with_image()
                                      │
                                      ▼
                                 QwenVLClient.chat_with_image()
                                      │
                                      ▼
                              OpenAI 兼容 API (SiliconFlow / vLLM / ...)
                                      │
                                      ▼
                                解析 tool_calls / JSON
                                      │
                                      ▼
                                执行 ToolRegistry 工具
                                      │
                                      ▼
                                返回 { path: "agent", analysis, tool_results }
```

## 4. 组件设计

### 4.1 配置 (default.yaml)

```yaml
llm:
  api_url: https://api.siliconflow.cn/v1
  api_key: ""                    # 优先 $LLM_API_KEY 环境变量
  model_name: Qwen/Qwen2.5-VL-7B-Instruct
  timeout: 30
  max_retries: 2
```

QwenVLClient 构造函数从 settings 读取默认值，同时允许构造时覆盖。

### 4.2 QwenVLClient

```python
class QwenVLClient(LLMClient):
    def __init__(self, api_url=None, api_key=None, model_name=None,
                 timeout=30, max_retries=2, http_client=None):
        self.api_url = api_url or settings.get("llm.api_url")
        self.api_key = api_key or settings.get("llm.api_key") or os.getenv("LLM_API_KEY", "")
        self.model_name = model_name or settings.get("llm.model_name", "Qwen/Qwen2.5-VL-7B-Instruct")
        self.timeout = timeout
        self.max_retries = max_retries
        # 接受外部 client 用于测试 mock
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
```

**chat(messages, tools, temperature):**
- POST `{api_url}/chat/completions`
- Body: `{ model, messages, tools (optional), temperature, max_tokens: 1024 }`
- 如果 tools 非空且 API 支持，传入 tools 参数
- 如果 API 不支持 tools（400 错误），降级为无 tools 调用 + `response_format={"type": "json_object"}`

**chat_with_image(prompt, image_data, tools, temperature):**
- 构造 content array: `[{ type: "text", text: prompt }, { type: "image_url", image_url: { url: "data:image/jpeg;base64,..." } }]`
- 其余同 chat()

**响应解析：**
```python
{
    "role": "assistant",
    "content": "...",           # 原始文本
    "tool_calls": [...] | None  # OpenAI 格式 tool_calls
}
```

**错误处理：**
- HTTP 4xx → raise `LLMAPIError` (含状态码和错误信息)
- HTTP 5xx → retry up to max_retries (指数退避)
- Timeout → raise `LLMTimeoutError`
- 非 JSON 响应 → raise `LLMResponseError`

### 4.3 CVAgent 提示词工程

**System Prompt:**
```
你是一个计算机视觉分析助手。分析图像内容并输出结构化 JSON。

任务：
1. 描述场景类型（室内/室外/交通/安防...）
2. 列出检测到的目标及其属性
3. 识别异常情况（如有）

输出格式：
{
    "scene_type": "string",
    "objects": [{"label": "string", "count": int, "details": "string"}],
    "anomalies": [{"type": "string", "description": "string", "confidence": float}],
    "summary": "string"
}
```

如果图像无法分析，返回 `{"error": "无法分析图像", "reason": "..."}`。

**执行流程：**
1. 调用 LLM（优先支持 tool_calls）
2. 如果有 tool_calls → 逐个执行 → 返回 tool_results
3. 如果无 tool_calls → 从 content 中解析 JSON
4. 两次解析尝试：直接 json.loads()，失败后尝试从 ```json ... ``` 代码块提取

### 4.4 DeepSeekVLClient

与 QwenVLClient 共享同一 HTTP 实现，仅默认参数不同：
```python
class DeepSeekVLClient(QwenVLClient):
    def __init__(self, api_url=None, api_key=None, model_name=None, **kwargs):
        super().__init__(
            api_url=api_url or "https://api.deepseek.com/v1",
            model_name=model_name or "deepseek-vl-7b-chat",
            **kwargs
        )
```

### 4.5 Worker 集成

Worker 中当前 Agent 路径返回 stub。修改为：
- `process_one()` 中 FastPath 返回 None 时
- 如果有 frame 数据 → decode → 传给 `agent.analyze_with_image()` 或 `agent.analyze()`
- Worker 需要持有 AgentOrchestrator 或 CVAgent 引用（当前只有 fast_path）

修改 Worker.__init__ 增加 agent 初始化：
```python
class Worker:
    def __init__(self, db_engine: AsyncEngine):
        self.db = db_engine
        # ... 现有 fast_path 初始化 ...
        # Agent 初始化
        tool_registry = ...
        agent = CVAgent(QwenVLClient(), tool_registry)
        self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)
```

## 5. 测试策略

| 层级 | 方法 | 覆盖 |
|------|------|------|
| 单元测试 | `httpx.AsyncClient` 注入 MockTransport | client 请求构建、响应解析、错误处理 |
| 集成测试 | mock transport + 真实 CVAgent | prompt 构造、tool_calls 路径、JSON 降级路径 |
| Worker 测试 | mock Agent path | Worker fallback 到 agent 路径 |
| 回归测试 | 全部 132+ 测试 | 不改坏现有功能 |

### HTTP Mock 方案

不引入新依赖，使用 httpx 内置的 MockTransport:
```python
transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
    "choices": [{"message": {"content": '{"scene_type": "traffic"}'}}]
}))
client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
```

## 6. 任务分解

| # | 任务 | 文件 | 测试文件 |
|---|------|------|---------|
| 1 | Config: default.yaml + settings 获取 | `config/default.yaml` | — |
| 2 | QwenVLClient 真实 HTTP | `src/agent/client.py` | `tests/test_agent.py` |
| 3 | CVAgent 提示词 + JSON 解析 | `src/agent/agent.py` | `tests/test_agent.py` |
| 4 | DeepSeekVLClient 同步 | `src/agent/client.py` | `tests/test_agent.py` |
| 5 | Worker Agent 路径集成 | `src/worker.py` | `tests/test_worker.py` |
| 6 | 回归测试 + 提交 | — | 全量 |

## 7. 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| OpenAI 兼容 API 不支持 tool_calls | 中 | 中 | JSON 模式降级（response_format） |
| 响应 token 数过大 | 中 | 低 | max_tokens=1024 限制 |
| API 延迟 >5s | 中 | 高 | timeout=30s；同时 config 允许调整 |
| API key 泄露 | 低 | 高 | .gitignore 禁止 .env；env vars 读取 |
