<!-- GSD:project-start source:PROJECT.md -->
## Project

**AI 算法调度中台 (AIMiddlePlatform)**

一个大小模型协同的计算机视觉 AI 算法调度中台。集成 14+ 种 CV 算法能力（目标检测、人脸识别、OCR、车辆检测、ReID 等），以 LLM Agent（Qwen-VL / DeepSeek-VL）为决策大脑、专用小模型集群为高频推理引擎。系统采用三路径设计——快速 DAG 管线处理 80-90% 的常规请求（百毫秒级），LLM Agent 处理复杂/低置信度场景（秒级），视频缓存服务支持行为识别等时序算法。面向算法工程师和应用开发者，支持 1000+ 到 10000+ 路摄像头规模，可部署于云中心或私有化环境。

**Core Value:** 摄像头视频帧经过平台处理后，95% 以上的常规场景在 300ms 内自动输出结构化分析结果，剩余复杂场景由 LLM Agent 准确研判——让安防监控从"人工盯屏"变成"AI 自动分析，人工处理异常"。

### Constraints

- **Performance**: 快速路径 <300ms，Agent 路径 <5s
- **Scale**: 起始 1000+ 路，可扩展至 10000+
- **Deployment**: 同时支持云中心和完全内网私有化
- **Model**: 优先国产开源多模态大模型

---
*Last updated: 2026-07-08 after project initialization*
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
