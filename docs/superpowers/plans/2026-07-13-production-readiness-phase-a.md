# Phase A — 生产就绪实现计划

> **供 agent 使用：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 以任务为单位执行此计划。步骤使用复选框（`- [ ]`）标记进度。

**目标：** 生产环境加固：MySQL 支持、密钥管理、Dockerfile 修复、K8s 清单升级、MinIO 集成。

**架构：** 所有更改向后兼容——开发/测试仍默认使用 SQLite，通过 `DATABASE_URL` 环境变量激活 MySQL。密钥从硬编码值迁移至环境变量。Dockerfile 从 pip 切换到 uv 以实现可复现构建。

**技术栈：** SQLAlchemy async（aiomysql）、uv、MinIO S3 SDK、Kustomize

## 全局约束

- Python >= 3.12，uv 包管理器
- 开发/测试默认使用 SQLite；生产环境使用 MySQL
- 所有环境变量使用 `os.getenv("KEY", "default_value")` 模式
- 无需 MySQL/MinIO 运行，现有测试必须继续通过
- Dockerfile 必须能够构建可用镜像，入口为 `uvicorn src.api.app:app`

---

### 任务 1：MySQL 支持

**文件：**
- 修改：`pyproject.toml` — 添加 aiomysql 依赖
- 创建：`src/core/db_url.py` — URL 解析与引擎创建工具
- 修改：`src/core/database.py` — 使用 `db_url.py` 创建引擎
- 修改：`src/api/app.py` — 从环境变量读取 DB URL
- 修改：`config/production.yaml` — 添加 database_url
- 修改：`alembic.ini` — 支持环境变量 DB URL
- 修改：`docker-compose.yml` — 添加 mysql 服务 + 环境变量覆盖
- 测试：`tests/test_db_url.py`

**接口：**
- 消费：`os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/aimp.db")`
- 产出：`create_db_engine(url: str)` → 异步 SQLAlchemy 引擎
- 产出：`get_db_url_from_config() → str`

- [ ] **步骤 1：添加 aiomysql 依赖**

```toml
# pyproject.toml dependencies 部分 — 在 aiosqlite 后添加
"aiomysql>=0.2.0",
```

- [ ] **步骤 2：创建 db_url.py 工具**

```python
# src/core/db_url.py
import os

DEFAULT_DB_URL = "sqlite+aiosqlite:///data/aimp.db"


def get_db_url_from_config() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


def is_mysql(url: str) -> bool:
    return url.startswith("mysql") or url.startswith("mysql+aiomysql")
```

- [ ] **步骤 3：更新 database.py**

```python
# src/core/database.py — 修改 init_db 签名和实现
from src.core.db_url import get_db_url_from_config, is_mysql

async def init_db(url: str | None = None):
    global _engine, _session_factory
    if url is None:
        url = get_db_url_from_config()
    if is_mysql(url) and not url.startswith("mysql+aiomysql"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    _engine = create_async_engine(url, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine
```

- [ ] **步骤 4：更新 app.py lifespan 从环境变量读取 DB URL**

```python
# src/api/app.py — 替换 lifespan() 中的硬编码行
db_url = os.getenv("DATABASE_URL") or settings.get("database.url") or "sqlite+aiosqlite:///data/aimp.db"
db_engine = await init_db(db_url)
```

在文件顶部添加导入：
```python
import os
```

- [ ] **步骤 5：更新 production.yaml 配置**

```yaml
# config/production.yaml — 在末尾追加
database:
  url: ${DATABASE_URL:-sqlite+aiosqlite:///data/aimp.db}
```

- [ ] **步骤 6：更新 alembic.ini 从环境变量读取**

```
# alembic.ini — 替换 sqlalchemy.url 行
sqlalchemy.url = %(DATABASE_URL)s
```

然后更新 `alembic/env.py` 允许环境变量覆盖：
```python
# alembic/env.py — 在 import config 后
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    sync_url = DATABASE_URL.replace("+aiosqlite", "").replace("+aiomysql", "")
    config.set_main_option("sqlalchemy.url", sync_url)
```

- [ ] **步骤 7：更新 docker-compose.yml**

```yaml
# docker-compose.yml — 添加 mysql 服务，更新 aimp-api/worker 环境变量
services:
  # ... 现有服务 ...

  mysql:
    image: mysql:8.0
    container_name: aimp-mysql
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-aimp_root}
      MYSQL_DATABASE: aimp
      MYSQL_USER: aimp
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-aimp_pass}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # 更新 aimp-api 环境变量
  aimp-api:
    environment:
      - APP_ENV=production
      - QUEUE_REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=mysql+aiomysql://aimp:aimp_pass@mysql:3306/aimp
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production}

  # 同样更新 aimp-worker
  aimp-worker:
    environment:
      - APP_ENV=production
      - QUEUE_REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=mysql+aiomysql://aimp:aimp_pass@mysql:3306/aimp

volumes:
  redis_data:
  mysql_data:    # 添加此项
```

- [ ] **步骤 8：为 db_url.py 编写测试**

```python
# tests/test_db_url.py
import os
from unittest.mock import patch
from src.core.db_url import get_db_url_from_config, is_mysql


def test_default_url_is_sqlite():
    url = get_db_url_from_config()
    assert url.startswith("sqlite")


def test_env_var_overrides():
    with patch.dict(os.environ, {"DATABASE_URL": "mysql+aiomysql://u:p@h/db"}):
        url = get_db_url_from_config()
        assert url.startswith("mysql+aiomysql")


def test_is_mysql_true():
    assert is_mysql("mysql+aiomysql://u:p@h/db")
    assert is_mysql("mysql://u:p@h/db")


def test_is_mysql_false():
    assert not is_mysql("sqlite+aiosqlite:///data/aimp.db")
    assert not is_mysql("postgresql://u:p@h/db")
```

- [ ] **步骤 9：运行测试验证**

运行：`uv run pytest tests/test_db_url.py -v`
预期：4 个 PASSED

- [ ] **步骤 10：提交**

```bash
git add -A
git commit -m "feat: add MySQL support for production database"
```

---

### 任务 2：密钥管理

**文件：**
- 修改：`src/api/routes/admin/auth.py` — 从环境变量读取密钥
- 修改：`config/production.yaml` — 添加 JWT 配置项
- 创建：`.env.example` — 环境变量模板
- 测试：`tests/test_admin_auth.py`（现有测试 — 必须仍能通过）

**接口：**
- 消费：`os.getenv("JWT_SECRET_KEY")`、`os.getenv("ADMIN_USERNAME")`、`os.getenv("ADMIN_PASSWORD")`

- [ ] **步骤 1：更新 auth.py 使用环境变量**

```python
# src/api/routes/admin/auth.py — 替换硬编码值
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aimp-dev-secret---change-in-production")
ALGORITHM = "HS256"
ACCESS_EXPIRE = timedelta(hours=24)
REFRESH_EXPIRE = timedelta(days=7)

_ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
_ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
```

- [ ] **步骤 2：运行现有 auth 测试**

运行：`uv run pytest tests/test_admin_auth.py -v`
预期：PASS（默认值不变）

- [ ] **步骤 3：创建 .env.example**

```
# D:\projects\AIMiddlePlatform\.env.example
# 复制为 .env 并根据本地环境调整
DATABASE_URL=sqlite+aiosqlite:///data/aimp.db
JWT_SECRET_KEY=your-secret-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password
QUEUE_REDIS_URL=redis://localhost:6379/0
```

- [ ] **步骤 4：提交**

```bash
git add -A
git commit -m "fix: move secrets from hardcoded values to env vars"
```

---

### 任务 3：修复 Dockerfile 使用 uv

**文件：**
- 修改：`Dockerfile` — 用 uv 替换 pip

- [ ] **步骤 1：重写 Dockerfile Python 阶段**

```dockerfile
# ---- Python runtime ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 同步精确依赖（不安装 dev 依赖，不安装项目本身，避免先复制源码）
RUN uv sync --no-dev --no-install-project

# 复制源代码
COPY config/ config/
COPY src/ src/
COPY models/ models/

# 复制前端构建产物
COPY --from=frontend-builder /app/dist/ frontend/dist/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health'); assert r.status==200"

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **步骤 2：提交**

```bash
git add Dockerfile
git commit -m "fix: use uv sync instead of pip in Dockerfile for reproducible builds"
```

---

### 任务 4：更新 K8s 部署清单

**文件：**
- 修改：`deploy/k8s/configmap.yaml` — 添加 DATABASE_URL
- 修改：`deploy/k8s/deployment.yaml` — 从 configmap 添加环境变量
- 创建：`deploy/k8s/worker-deployment.yaml` — Worker 部署
- 创建：`deploy/k8s/redis-deployment.yaml` — 专用 Redis 部署
- 修改：`deploy/k8s/kustomization.yaml` — 添加新资源

- [ ] **步骤 1：更新 configmap.yaml**

```yaml
# deploy/k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aimp-config
  labels:
    app: aimiddleplatform
data:
  APP_ENV: "production"
  QUEUE_REDIS_URL: "redis://aimp-redis:6379/0"
  DATABASE_URL: "mysql+aiomysql://aimp:aimp_pass@aimp-mysql:3306/aimp"
```

- [ ] **步骤 2：更新 deployment.yaml — 添加 envFrom**

部署已包含 `envFrom` 引用 `aimp-config`。ConfigMap 已包含所需变量。
只需添加 JWT 密钥（应来自 Secret，而非 ConfigMap）：

```yaml
# deploy/k8s/deployment.yaml — 在 env 下添加：
          - name: JWT_SECRET_KEY
            valueFrom:
              secretKeyRef:
                name: aimp-secret
                key: jwt_secret_key
```

- [ ] **步骤 3：创建 worker-deployment.yaml**

```yaml
# deploy/k8s/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aimp-worker
  labels:
    app: aimiddleplatform
    component: worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aimiddleplatform
      component: worker
  template:
    metadata:
      labels:
        app: aimiddleplatform
        component: worker
    spec:
      containers:
        - name: worker
          image: aimiddleplatform:0.1.0
          imagePullPolicy: IfNotPresent
          command: ["python", "-m", "src.worker"]
          envFrom:
            - configMapRef:
                name: aimp-config
          env:
            - name: JWT_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: aimp-secret
                  key: jwt_secret_key
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
```

- [ ] **步骤 4：创建 redis-deployment.yaml**

```yaml
# deploy/k8s/redis-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aimp-redis
  labels:
    app: aimiddleplatform
    component: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aimiddleplatform
      component: redis
  template:
    metadata:
      labels:
        app: aimiddleplatform
        component: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
```

- [ ] **步骤 5：更新 kustomization.yaml**

```yaml
# deploy/k8s/kustomization.yaml
resources:
  - configmap.yaml
  - deployment.yaml
  - worker-deployment.yaml
  - redis-deployment.yaml
  - service.yaml
  - hpa.yaml
```

- [ ] **步骤 6：提交**

```bash
git add deploy/k8s/
git commit -m "feat: add worker/redis K8s deployments, add DATABASE_URL to configmap"
```

---

### 任务 5：MinIO / S3 对象存储集成

**文件：**
- 创建：`src/core/storage.py` — 异步 S3 客户端封装
- 创建：`tests/test_storage.py` — 单元测试
- 修改：`pyproject.toml` — 添加 `minio` 依赖
- 修改：`config/default.yaml` — 添加 storage 配置
- 修改：`config/production.yaml` — 添加 storage 配置

**接口：**
- 产出：`StorageClient(url, access_key, secret_key, bucket, region)` 类
- 产出：`get_storage() → StorageClient` 单例
- 产出：`put_object(key, data, content_type)`、`get_object(key)`、`delete_object(key)`、`list_objects(prefix)`

- [ ] **步骤 1：添加 minio 依赖**

```toml
# pyproject.toml — 在 redis 后添加
"minio>=7.2.0",
```

- [ ] **步骤 2：创建 storage.py**

```python
# src/core/storage.py
import io
import os
import logging

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

_client: Minio | None = None
_bucket: str = "aimp-results"


def get_storage() -> Minio | None:
    global _client
    if _client is None:
        endpoint = os.getenv("S3_ENDPOINT", "")
        if not endpoint:
            logger.warning("S3_ENDPOINT 未设置，存储功能已禁用")
            return None
        access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
        secure = os.getenv("S3_SECURE", "false").lower() == "true"
        region = os.getenv("S3_REGION", "us-east-1")
        _client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure, region=region)
        _bucket = os.getenv("S3_BUCKET", "aimp-results")
        try:
            if not _client.bucket_exists(_bucket):
                _client.make_bucket(_bucket)
                logger.info("已创建 S3 存储桶 '%s'", _bucket)
        except S3Error as e:
            logger.warning("无法访问 S3 存储桶 '%s'：%s", _bucket, e)
    return _client


def put_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    client = get_storage()
    if client is None:
        return False
    try:
        client.put_object(_bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
        return True
    except Exception as e:
        logger.error("S3 对象上传失败 %s：%s", key, e)
        return False


def get_object(key: str) -> bytes | None:
    client = get_storage()
    if client is None:
        return None
    try:
        resp = client.get_object(_bucket, key)
        data = resp.read()
        resp.close()
        resp.release_conn()
        return data
    except S3Error as e:
        if e.code == "NoSuchKey":
            return None
        logger.error("S3 对象获取失败 %s：%s", key, e)
        return None


def delete_object(key: str) -> bool:
    client = get_storage()
    if client is None:
        return False
    try:
        client.remove_object(_bucket, key)
        return True
    except Exception as e:
        logger.error("S3 对象删除失败 %s：%s", key, e)
        return False


def list_objects(prefix: str = "") -> list[str]:
    client = get_storage()
    if client is None:
        return []
    try:
        objects = client.list_objects(_bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
    except Exception as e:
        logger.error("S3 对象列表获取失败：%s", e)
        return []
```

- [ ] **步骤 3：编写存储测试**

```python
# tests/test_storage.py
import os
from unittest.mock import patch, MagicMock
from src.core.storage import get_storage, put_object, get_object, delete_object, list_objects


def test_get_storage_returns_none_when_not_configured():
    with patch.dict(os.environ, {}, clear=True):
        assert get_storage() is None


def test_put_object_returns_false_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert put_object("test.txt", b"data") is False


def test_get_object_returns_none_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert get_object("test.txt") is None


def test_delete_object_returns_false_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert delete_object("test.txt") is False


def test_list_objects_returns_empty_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert list_objects() == []


def test_get_storage_creates_client():
    mock_client = MagicMock()
    with patch.dict(os.environ, {"S3_ENDPOINT": "play.min.io:9000"}, clear=True):
        with patch("src.core.storage.Minio", return_value=mock_client):
            client = get_storage()
            assert client is not None
```

- [ ] **步骤 4：添加存储配置**

```yaml
# config/default.yaml — 追加
storage:
  enabled: false
  endpoint: ""
  access_key: ""
  secret_key: ""
  bucket: aimp-results
  secure: false
```

```yaml
# config/production.yaml — 追加
storage:
  enabled: true
  endpoint: ${S3_ENDPOINT:-minio:9000}
  access_key: ${S3_ACCESS_KEY:-minioadmin}
  secret_key: ${S3_SECRET_KEY:-minioadmin}
  bucket: ${S3_BUCKET:-aimp-results}
  secure: false
```

- [ ] **步骤 5：运行存储测试**

运行：`uv run pytest tests/test_storage.py -v`
预期：6 个 PASSED

- [ ] **步骤 6：运行全部测试确认无回归**

运行：`uv run pytest tests/ -v --tb=short 2>&1 | Select-String -Pattern "failed|passed|collected"`
预期：300+ 通过，0 失败（测试数量增加）

- [ ] **步骤 7：提交**

```bash
git add -A
git commit -m "feat: add MinIO/S3 object storage client"
```
