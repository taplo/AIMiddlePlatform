# 内网部署文档 — AI 算法调度中台

## 1 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 8 核 | 16 核+ |
| 内存 | 16 GB | 32 GB+ |
| 磁盘 | 100 GB SSD | 500 GB SSD |
| GPU | — | NVIDIA T4 / 昇腾 310P / 寒武纪 MLU370 |
| 操作系统 | Ubuntu 20.04+ / CentOS 7+ | Ubuntu 22.04 LTS |
| 内核 | Linux 5.4+ | Linux 5.15+ |
| Docker | 24.0+ | 24.0+ |
| Kubernetes | 1.24+ | 1.28+ |

### 基础软件

| 软件 | 版本 | 用途 |
|------|------|------|
| Python | 3.12+ | 运行环境 |
| Redis | 7.x | 帧队列与缓存 |
| MySQL (可选) | 8.0 | 持久化数据库（默认 SQLite） |
| NVIDIA Driver (可选) | 535+ | GPU 推理 |
| Ascend CANN (可选) | 8.0+ | 昇腾 NPU 推理 |

---

## 2 离线制品准备

在内网部署之前，在有外网的机器上提前下载以下制品，刻盘或通过内部文件服务器分发。

### 2.1 项目源码与依赖

```bash
# 克隆项目
git clone https://github.com/yourorg/aimiddleplatform.git -b v0.1.0
cd aimiddleplatform

# 创建离线依赖包目录
mkdir -p offline/packages

# 使用 uv 导出所有依赖（不含 dev）
uv export --no-dev --format requirements-txt > offline/requirements.txt

# 使用 pip 下载所有 wheel 包
pip download -r offline/requirements.txt -d offline/packages/ --platform manylinux2014_x86_64 --only-binary=:all:

# 下载 onnxruntime 等与架构相关的包（如果下载失败，补充 --platform 参数）
pip download onnxruntime onnx opencv-python-headless -d offline/packages/ --platform manylinux2014_x86_64

# 打包
tar czf offline-artifacts.tar.gz offline/ src/ config/ deploy/ scripts/ models/
```

### 2.2 模型权重

```bash
# 使用内置下载脚本提前下载模型权重
cd aimiddleplatform
python -c "from src.models.adapters.downloader import ensure_model; ensure_model('yolov8n', 'models'); ensure_model('yolov8s', 'models'); ensure_model('yolov8m', 'models')"

# 打包模型目录
tar czf models-offline.tar.gz models/
```

### 2.3 Docker 镜像

```bash
# 导出需要的 Docker 镜像列表
cat > offline/images.txt << 'EOF'
python:3.12-slim
redis:7-alpine
mysql:8.0
taplo/aimiddleplatform:latest   # 项目 API + Worker 镜像
EOF

# 在有外网的机器上拉取并保存
for img in $(cat offline/images.txt); do
  docker pull $img
  docker save $img | gzip > "offline/$(echo $img | tr '/:' '_').tar.gz"
done
```

### 2.4 Helm Chart（K8s 部署时可选）

```bash
# 项目 Helm Chart 已包含在 deploy/helm/aimp/ 目录下，无需额外下载
# 如需离线部署 K8s，预先拉取子 Chart（Redis 等）
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm pull bitnami/redis --version 19.0.2 --untar -d offline/charts/
```

---

## 3 方式一：Docker Compose 部署（单机）

适用于 100-500 路摄像头的小规模场景。

### 3.1 内网机器准备

```bash
# 将离线制品复制到目标机器
scp offline-artifacts.tar.gz user@internal-host:/opt/aimp/
scp models-offline.tar.gz user@internal-host:/opt/aimp/
# 如果有 Docker 镜像压缩包也一并复制
scp offline/*.tar.gz user@internal-host:/opt/aimp/images/
```

### 3.2 加载 Docker 镜像

```bash
cd /opt/aimp/images
for f in *.tar.gz; do
  gunzip -c "$f" | docker load
done
```

### 3.3 安装离线 Python 依赖

```bash
cd /opt/aimp
tar xzf offline-artifacts.tar.gz

# 推荐使用 uv 离线安装（uv 需先在内网分发）
uv venv .venv
uv pip install --no-index --find-links offline/packages/ -r offline/requirements.txt
```

### 3.4 配置

```bash
cd /opt/aimp
cp config/default.yaml config/production.yaml
vi config/production.yaml
```

关键配置项：

```yaml
app:
  env: production

ingestion:
  max_streams: 500          # 按接入路数调整
  default_fps: 1.0

queue:
  redis_url: redis://localhost:6379/0
  type: redis_streams

database:
  url: sqlite+aiosqlite:///data/aimp.db   # 小规模推荐 SQLite
  # url: mysql+aiomysql://aimp:password@mysql-host:3306/aimp   # 大规模推荐 MySQL

result_cache:
  enabled: true
  ttl_seconds: 60

llm:
  api_url: http://internal-llm-endpoint:8000/v1   # 内网 LLM 地址
  api_key: ""                # 如果 LLM 不需要鉴权则为空
  model_name: Qwen/Qwen2.5-VL-7B-Instruct

data_collection:
  enabled: false             # 内网环境通常关闭
```

### 3.5 启动服务

```bash
# 启动 Redis（使用 docker-compose）
cat > docker-compose.yml << 'EOF'
services:
  redis:
    image: redis:7-alpine
    container_name: aimp-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  aimp:
    image: taplo/aimiddleplatform:latest
    container_name: aimp-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      - redis
    volumes:
      - ./config:/app/config
      - ./models:/app/models
      - ./data:/app/data
    environment:
      - APP_ENV=production
      - QUEUE_REDIS_URL=redis://redis:6379/0

volumes:
  redis_data:
EOF

# 如果是 CPU-only 环境
docker compose up -d

# 如果使用 NVIDIA GPU
docker compose up -d --gpus all
```

### 3.6 验证

```bash
# 检查服务健康
curl http://localhost:8000/api/v1/analyze/ping

# 检查模型加载
curl http://localhost:8000/api/v1/models

# 发送测试帧
# 见验证章节
```

---

## 4 方式二：Kubernetes 部署（集群）

适用于 500+ 路摄像头的大规模场景。

### 4.1 离线 Helm 安装

```bash
cd /opt/aimp

# 如果 Redis Chart 已离线下载
helm install aimp ./deploy/helm/aimp \
  --set redis.image=registry.internal/redis:7-alpine \
  --set image.repository=registry.internal/aimiddleplatform \
  --set image.tag=v0.1.0 \
  --set image.pullPolicy=Always \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=aimp.internal.company.com \
  --set config.QUEUE_REDIS_URL=redis://aimp-redis:6379/0 \
  --set config.APP_ENV=production \
  --namespace aimp --create-namespace
```

### 4.2 私有镜像仓库

如果内网有 Harbor 或其他镜像仓库：

```bash
# 在有外网的机器上
docker pull taplo/aimiddleplatform:latest
docker tag taplo/aimiddleplatform:latest registry.internal/aimiddleplatform:v0.1.0
docker push registry.internal/aimiddleplatform:v0.1.0

docker pull redis:7-alpine
docker tag redis:7-alpine registry.internal/redis:7-alpine
docker push registry.internal/redis:7-alpine
```

### 4.3 持久化存储

确保 PVC 使用的 StorageClass 对应内网存储后端：

```bash
# 查看可用 StorageClass
kubectl get storageclass

# 如果有 NFS 或 Ceph
helm upgrade aimp ./deploy/helm/aimp \
  --set persistence.models.storageClass=nfs-client \
  --set persistence.data.storageClass=nfs-client \
  --set persistence.logs.storageClass=nfs-client \
  --set redis.persistence.storageClass=nfs-client
```

### 4.4 GPU 节点标签

```bash
# NVIDIA GPU
kubectl label nodes gpu-node-1 nvidia.com/gpu=true

# 昇腾 NPU
kubectl label nodes ascend-node-1 ascend.com/npu=true

# 在 values.yaml 中启用
helm upgrade aimp ./deploy/helm/aimp \
  --set gpu.enabled=true \
  --set gpu.nodeSelector.ascend\\.com/npu=true
```

---

## 5 方式三：纯 Python 直接运行（开发/测试）

适用于快速验证和开发环境。

```bash
# 1. 安装依赖
uv venv .venv
source .venv/bin/activate
uv pip install --no-index --find-links offline/packages/ -r offline/requirements.txt

# 2. 配置 Redis（需内网已有 Redis 实例）
export QUEUE_REDIS_URL=redis://your-redis:6379/0

# 3. 启动 API 服务
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# 4. 启动 Worker（新终端）
export QUEUE_REDIS_URL=redis://your-redis:6379/0
uv run python -m src.worker
```

---

## 6 配置清单

### 环境变量总表

| 变量 | 默认值 | 说明 |
|------|--------|------|
| APP_ENV | dev | 运行环境（dev/production） |
| QUEUE_REDIS_URL | redis://localhost:6379/0 | Redis 连接地址 |
| DATABASE_URL | sqlite+aiosqlite:///data/aimp.db | 数据库连接 |
| LLM_API_URL | — | LLM API 地址（内网端点） |
| LLM_API_KEY | — | LLM API 密钥 |
| LLM_MODEL_NAME | Qwen/Qwen2.5-VL-7B-Instruct | 模型名称 |
| CACHE_ENABLED | true | 结果缓存开关 |
| CACHE_TTL_SECONDS | 60 | 缓存 TTL |
| RATE_LIMIT_DEFAULT | 60 | 默认限流 QPS |
| MAX_STREAMS | 1000 | 最大摄像头接入数 |
| DATA_COLLECTION_ENABLED | false | 数据收集开关 |
| DATA_COLLECTION_OUTPUT_DIR | data/collected/agent_pairs | 收集数据输出目录 |

### 端口清单

| 端口 | 用途 | 协议 |
|------|------|------|
| 8000 | API 服务 | HTTP |
| 6379 | Redis | TCP |
| 3306 | MySQL（可选） | TCP |
| 9090 | Prometheus 指标 | HTTP |

---

## 7 模型管理

### 7.1 模型存放路径

默认从 `/app/models/` 加载模型权重。目录结构：

```
models/
├── yolov8n.onnx
├── yolov8s.onnx
├── object_detection.onnx
├── face_detection.onnx
├── ocr.onnx
└── packages/   # .aimp 离线模型包
```

### 7.2 使用 .aimp 模型包

```bash
# 在有外网的机器上创建离线包
from src.models.package_manager import ModelPackageManager
pkg_mgr = ModelPackageManager("models/packages")
pkg_mgr.create_package("models/yolov8n.onnx",
                       name="yolov8n",
                       version="1.0.0",
                       metadata={"framework": "onnx", "source": "ultralytics"})

# 将 packages/ 目录整体传到内网
# 在内网机器上加载
pkg_mgr.load_package("models/packages/yolov8n-1.0.0.aimp")
```

### 7.3 模型缓存预热

```bash
# 启动时自动加载默认模型
python -c "
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
adapter = YOLOv8Adapter(model_dir='models')
# 加载 ONNX 会话
adapter._load_model('object_detection')
print('Model loaded successfully')
"
```

---

## 8 日志与监控

### 8.1 日志位置

```
data/logs/
├── api.log          # API 服务日志
├── worker.log       # Worker 日志
└── access.log       # HTTP 访问日志
```

### 8.2 Prometheus 指标

API 服务在 `:8000/metrics` 暴露 Prometheus 指标：
- `request_total` — 请求计数
- `request_latency_seconds` — 请求延迟直方图
- `inference_total` — 推理计数
- `inference_latency_seconds` — 推理延迟直方图

### 8.3 Grafana Dashboard

部署在 `deploy/grafana/dashboards/aimp-core-metrics.json`，导入到 Grafana 即可。

### 8.4 告警通知配置

通过 API 配置通知渠道：

```bash
# 启用钉钉
curl -X PUT http://localhost:8000/api/v1/admin/notifications/DingTalk \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "config": {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"}}'

# 启用企微
curl -X PUT http://localhost:8000/api/v1/admin/notifications/WeChat%20Work \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "config": {"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"}}'

# 启用飞书
curl -X PUT http://localhost:8000/api/v1/admin/notifications/Feishu \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "config": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"}}'
```

---

## 9 验证

### 9.1 基础验证

```bash
# 健康检查
curl http://localhost:8000/api/v1/analyze/ping
# 预期: {"ok": true}

# 模型列表
curl http://localhost:8000/api/v1/models
# 预期: 返回注册的模型列表

# 摄像头流管理
curl http://localhost:8000/api/v1/admin/streams
# 预期: {"total_streams": 0, ...}
```

### 9.2 端到端推理验证

```python
# test_deployment.py — 部署验证脚本
import base64
import cv2
import httpx

# 用一张测试图片发送推理请求
img = cv2.imread("bus_test.jpg")
_, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
frame_b64 = base64.b64encode(buf).decode()

resp = httpx.post(
    "http://localhost:8000/api/v1/analyze/frame?sync=false",
    json={"camera_id": "test-cam", "frame": frame_b64, "scene_type": "detection"},
    headers={"X-API-Key": "your-api-key"},
)
assert resp.status_code in (200, 202), f"Unexpected: {resp.status_code}"
print("E2E 推理验证通过")
```

### 9.3 压力测试

```bash
# 使用 wrk 或 hey 进行基准测试
# 安装 hey: go install github.com/rakyll/hey@latest
hey -n 1000 -c 10 -m POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"camera_id":"bench","frame":"'$(base64 -w0 bus_test.jpg)'","scene_type":"detection"}' \
  http://localhost:8000/api/v1/analyze/frame?sync=true
```

---

## 10 运维

### 10.1 健康检查

```yaml
# Kubernetes liveness / readiness 探针（已配置在 Helm Chart 中）
livenessProbe:
  httpGet:
    path: /api/v1/analyze/ping
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 15

readinessProbe:
  httpGet:
    path: /api/v1/analyze/ping
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

### 10.2 备份

```bash
# SQLite 数据库
cp data/aimp.db data/backups/aimp-$(date +%Y%m%d).db

# 配置
cp -r config/ data/backups/config-$(date +%Y%m%d)

# 使用 cron 自动备份
echo "0 3 * * * root cp /opt/aimp/data/aimp.db /opt/aimp/data/backups/aimp-$(date +\\%Y\\%m\\%d).db" >> /etc/crontab
```

### 10.3 扩缩容

```bash
# K8s: 调整 worker 数量
kubectl scale deployment aimp-worker --replicas=5 -n aimp

# Docker Compose: 修改 docker-compose.yml 后重新启动
docker compose up -d --scale aimp=3
```

### 10.4 常见问题

| 问题 | 排查方法 |
|------|----------|
| Redis 连接失败 | 检查 `QUEUE_REDIS_URL` 和 Redis 是否运行 |
| 模型加载失败 | 确认模型文件在 `models/` 目录且格式正确 |
| API Key 认证失败 | 通过 `/api/v1/admin/api-keys` 接口生成新 Key |
| LLM 请求超时 | 检查内网 LLM 端点是否可达 |
| 视频流接入失败 | 确认 RTSP 地址正确、网络可达 |

---

## 11 内网 LLM 部署建议

平台 Agent 路径依赖多模态大模型。内网环境下推荐以下方案：

### 11.1 vLLM 部署（推荐）

```bash
# 在有外网的机器上拉取镜像
docker pull vllm/vllm-openai:latest

# 下载模型权重
# 以 Qwen2.5-VL-7B-Instruct 为例
git lfs install
git clone https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct

# 在内网启动
docker run --gpus all -p 8000:8000 \
  -v /path/to/Qwen2.5-VL-7B-Instruct:/models \
  vllm/vllm-openai:latest \
  --model /models \
  --trust-remote-code \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9
```

### 11.2 Ollama 部署（轻量级）

```bash
# 在有外网的机器上
ollama pull qwen2.5-vl:7b

# 导出模型
ollama export qwen2.5-vl:7b > /tmp/qwen2.5-vl-7b.tar

# 在内网
ollama import /tmp/qwen2.5-vl-7b.tar
ollama run qwen2.5-vl:7b
```

### 11.3 配置对接

```yaml
# config/production.yaml
llm:
  api_url: http://vllm-server:8000/v1    # vLLM 默认兼容 OpenAI API
  # api_url: http://ollama-server:11434/v1  # Ollama
  api_key: ""
  model_name: Qwen/Qwen2.5-VL-7B-Instruct
  timeout: 30
```

---

## 12 离线升级

```bash
# 1. 备份
cp -r /opt/aimp /opt/aimp-backup-$(date +%Y%m%d)

# 2. 上传新版本离线包
tar xzf aimp-v0.2.0-offline.tar.gz -C /opt/aimp-new/

# 3. 更新依赖
source /opt/aimp/.venv/bin/activate
uv pip install --no-index --find-links /opt/aimp-new/offline/packages/ -r /opt/aimp-new/offline/requirements.txt

# 4. 替换代码
cp -r /opt/aimp-new/src/* /opt/aimp/src/

# 5. 迁移数据库（如果有 schema 变更）
python -m src.scripts.migrate

# 6. 重启服务
docker compose restart
```
