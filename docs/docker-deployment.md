# Docker Compose 部署指南

本文档适用于一台服务器运行多个项目的部署方式：本项目容器不直接占用宿主机 `80/443`，只把前端 Nginx 容器绑定到宿主机回环地址端口，再由宿主机统一 Nginx/Caddy 反代。

## 架构

```text
宿主机 Nginx/Caddy :80/:443
  -> 127.0.0.1:18080  staging frontend container
  -> 127.0.0.1:18081  prod frontend container

frontend container
  -> /api/ reverse proxy -> backend:8000

backend container
  -> postgres:5432
  -> redis:6379
```

PostgreSQL、Redis、Backend 都不暴露宿主机端口，只在 Compose 内部网络访问。

## 分支与服务器

建议：

```text
测试服务器：origin/master（或待验证的发布候选 tag）
生产服务器：release tag（当前首个正式版本为 v0.1.0）
```

> `develop` 分支已全部合入 `master`，不再作为集成分支使用，请勿从它部署。

如果测试和生产在不同服务器，可以使用相同的 `FRONTEND_PORT=18080`。

如果测试和生产在同一服务器，必须使用不同目录、不同 `.env`、不同 `COMPOSE_PROJECT_NAME`、不同 `FRONTEND_PORT`。

示例：

```text
/opt/insurance-staging  COMPOSE_PROJECT_NAME=insurance_staging  FRONTEND_PORT=18080
/opt/insurance-prod     COMPOSE_PROJECT_NAME=insurance_prod     FRONTEND_PORT=18081
```

## 首次部署测试环境

```bash
cd /opt
git clone https://github.com/nwm1314/insurance-recommendation.git insurance-staging
cd insurance-staging
git checkout master
cp .env.example .env
```

编辑 `.env`，至少修改：

```env
COMPOSE_PROJECT_NAME=insurance_staging
FRONTEND_PORT=18080
POSTGRES_DB=insurance_staging
POSTGRES_USER=insurance
POSTGRES_PASSWORD=替换为强密码
DATABASE_URL=postgresql+psycopg2://insurance:替换为强密码@postgres:5432/insurance_staging
REDIS_URL=redis://redis:6379
CORS_ALLOW_ORIGINS=https://staging.example.com
JWT_SECRET_KEY=替换为强随机字符串
FIRST_ADMIN_EMAIL=admin-staging@example.com
FIRST_ADMIN_PASSWORD=首次部署临时密码（启动时创建管理员并写审计日志 auth.first_admin.bootstrap，创建后请清空）
SCORING_WEIGHTS_FAIL_FAST=true
LLM_API_KEY=填写测试环境 LLM Key
APP_ENV=staging
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
TRUST_PROXY_HEADERS=true
TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12
SECURITY_HEADERS=true
# 必检项（OPEN-002）：推荐记录含健康描述等敏感个人信息，内测环境必须有真实用户，
# 因此该密钥属于内测硬性门禁，留空即明文落库。生成：
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
RECORD_ENCRYPTION_KEY=替换为强随机字符串
```

> `COOKIE_SECURE`：只有 HTTPS 才设 `true`（浏览器会拒绝非 HTTPS 连接上带 Secure 的 Cookie）；纯 HTTP 内网验证环境保持 `false`。

> 管理员初始化：公开注册的普通用户永远不会获得 admin 角色。受控初始化仅通过 `FIRST_ADMIN_EMAIL` + `FIRST_ADMIN_PASSWORD` 在首次启动时创建管理员（幂等，已存在则不重复创建，创建动作写入审计日志且不记录密码）。创建完成后请清空 `FIRST_ADMIN_PASSWORD`。后续新管理员由既有管理员调用 `POST /api/admin/users/{user_id}/roles`（请求体 `{"roles": ["admin"]}`，需 `admin:grant` 权限）授予，操作写入审计日志。

构建并启动基础服务：

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
docker compose up -d --build
docker compose ps
```

The backend image runs `alembic upgrade head` from its entrypoint before
starting Uvicorn. The explicit migration command above remains useful for
preflight visibility, but backend startup also repairs legacy databases that
are missing the Alembic version row or additive schema changes. A migration
failure still prevents the backend from becoming healthy.

> 迁移命令必须在 `/srv/backend` 下执行（镜像 `WORKDIR` 是 `/srv`）。后端启动时校验数据库模式：未迁移或迁移版本不是 head 会直接拒绝启动（fail-fast），不会静默建表或进入不一致状态。

验证：

```bash
curl http://127.0.0.1:18080/healthz
curl http://127.0.0.1:18080/api/products
docker compose logs -f backend
```

**【硬性卡点 · OPEN-002】推荐记录加密**：内测环境会有真实用户画像，未配置密钥即明文
落库。上一步骤必须逐字执行下面的检查（可直接放进部署脚本，命中即退出码 1）：

```bash
if docker compose logs backend | grep -qi "RECORD_ENCRYPTION_KEY"; then
  echo "FAIL: 推荐记录正在明文落库，请在 .env 配置 RECORD_ENCRYPTION_KEY 后重启"
  exit 1
fi
echo "OK: 启动日志无 PLAINTEXT 告警，推荐记录已加密"
```

> 检查的是**日志**而不是 `.env` 文件：compose 只把 `environment:` 段列出的变量注入容器，
> 变量写进 `.env` 但没进 compose 段同样会明文落库（该透传行已由
> `backend/tests/test_compose_policy.py` 锁定）。

## 更新测试环境

升级前先备份数据库：

```bash
docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

```bash
cd /opt/insurance-staging
git fetch origin
git checkout master
git pull origin master
docker compose build
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
docker compose up -d --build
docker compose ps
```

## 生产部署

生产建议部署 release tag：

```bash
cd /opt
git clone https://github.com/nwm1314/insurance-recommendation.git insurance-prod
cd insurance-prod
git fetch --tags
git checkout v0.1.0
cp .env.example .env
```

生产 `.env` 示例：

```env
COMPOSE_PROJECT_NAME=insurance_prod
FRONTEND_PORT=18081
POSTGRES_DB=insurance_prod
POSTGRES_USER=insurance
POSTGRES_PASSWORD=替换为生产强密码
DATABASE_URL=postgresql+psycopg2://insurance:替换为生产强密码@postgres:5432/insurance_prod
REDIS_URL=redis://redis:6379
CORS_ALLOW_ORIGINS=https://example.com
JWT_SECRET_KEY=替换为生产强随机字符串
FIRST_ADMIN_EMAIL=admin@example.com
FIRST_ADMIN_PASSWORD=首次部署临时密码，创建管理员后清空
SCORING_WEIGHTS_FAIL_FAST=true
LLM_API_KEY=生产 LLM Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-flash
APP_ENV=production
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
TRUST_PROXY_HEADERS=true
TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12
SECURITY_HEADERS=true
HSTS_ENABLED=true
# 必检项（OPEN-002）：生产环境未配置该密钥时，启动日志会以 **error** 级输出
# PLAINTEXT 告警（应用不拒绝启动，见「推荐记录加密」章节）。必须配置。
RECORD_ENCRYPTION_KEY=替换为生产强随机字符串
```

启动：

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
docker compose up -d --build
```

**【硬性卡点 · OPEN-002】上线前必须通过**：推荐记录（含健康描述）明文落库属敏感个人
信息合规风险，生产部署不得带着该告警上线。

```bash
if docker compose logs backend | grep -qi "RECORD_ENCRYPTION_KEY"; then
  echo "FAIL: 生产环境推荐记录正在明文落库，请配置密钥后重启再上线"
  exit 1
fi
echo "OK: 生产启动日志无 PLAINTEXT 告警"
```

> 该检查与 `APP_ENV` 无关：warning（非生产）与 error（生产）两条日志都含
> `RECORD_ENCRYPTION_KEY`，命中任意一条即说明未加密。

## 宿主机 Nginx 反代

测试环境：

```nginx
server {
    listen 80;
    server_name staging.example.com;

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

生产环境：

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:18081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用 HTTPS 建议使用 Certbot 或 Caddy。Caddy 示例：

```caddyfile
staging.example.com {
    reverse_proxy 127.0.0.1:18080
}

example.com {
    reverse_proxy 127.0.0.1:18081
}
```

## 安全配置（Cookie、可信代理、限流、响应头）

### 环境变量透传

以下安全变量已写入 `docker-compose.yml` 的 backend 服务 `environment:` 段，与 `.env` / `.env.example` 对应。未设置时走 fail-safe 开发默认：不信任代理头、不发 HSTS、Cookie Secure 为 false（`APP_ENV=production` 时须在 `.env` 显式设 `COOKIE_SECURE=true`，否则启动失败）。

```yaml
APP_ENV: ${APP_ENV:-development}
COOKIE_SECURE: ${COOKIE_SECURE:-false}
COOKIE_SAMESITE: ${COOKIE_SAMESITE:-lax}
TRUST_PROXY_HEADERS: ${TRUST_PROXY_HEADERS:-false}
TRUSTED_PROXIES: ${TRUSTED_PROXIES:-}
SECURITY_HEADERS: ${SECURITY_HEADERS:-true}
HSTS_ENABLED: ${HSTS_ENABLED:-false}
RECORD_ENCRYPTION_KEY: ${RECORD_ENCRYPTION_KEY:-}   # 留空=明文落库，内测/生产必配，见下节
```

### 推荐记录加密（敏感个人信息，内测/生产必须配置）

推荐记录包含用户画像与推荐结果，其中 `health_status` / `health_issues`（70+ 健康编码）
属**敏感个人信息**。未配置密钥时应用**不会拒绝启动**（本地开发显式降级，保证可用），
但会明文落库并在启动日志输出告警——非生产为 warning，`APP_ENV=production` 升级为 error：

```
WARNING backend.main:main.py:35 RECORD_ENCRYPTION_KEY is not set: recommendation records
(profile/result, including health disclosures) will be stored in PLAINTEXT.
Set the key in .env before exposing the system to real users.
```

**对外内测 / 生产部署的硬性卡点**（`§首次部署测试环境` 与 `§生产部署` 的操作清单已各含
一份，可直接放进部署脚本）：

```bash
# 1. 生成密钥并写入 .env（任意非空字符串，应用内部派生 Fernet 密钥）
python -c "import secrets; print('RECORD_ENCRYPTION_KEY=' + secrets.token_urlsafe(48))" >> .env

# 2. 确认 compose 已把它注入容器（缺这一行则 .env 写了也不生效）
docker compose config | grep -A1 "RECORD_ENCRYPTION_KEY"

# 3. 启动后检查日志：命中 PLAINTEXT 告警即判定不合格（退出码 1）
if docker compose logs backend | grep -qi "RECORD_ENCRYPTION_KEY"; then
  echo "FAIL: 推荐记录正在明文落库"
  exit 1
fi
echo "OK: 推荐记录已加密"
```

> 为什么第 2 步不可省：Compose 只把 `environment:` 段显式列出的变量注入容器，
> `.env` 里存在但段里缺失的变量对进程不可见。该透传行由
> `backend/tests/test_compose_policy.py::test_backend_forwards_record_encryption_key` 锁定。

注意事项：

- 密钥一旦更换，**既有密文记录将无法解密**（上层按"不可解密记录"处理，与 fail-open 边界
  一致，见 `backend/app/models/auth.py`）。上线前设定并妥善备份。
- 加密仅覆盖推荐记录；**数据库文件与备份仍需按敏感数据处理**。
- 健康信息保留期限由 `RECORD_RETENTION_DAYS` 控制：`0`（默认）永久保留；正数时后端每日清理一次早于该天数的推荐记录（硬删除，仅 `recommendation_records`，不影响用户保存的画像）。`SCHEDULER_DISABLED=true` 的副本可用 `python backend/scripts/purge_expired_records.py --days N [--dry-run]` 手动执行；缩短窗口前先导出归档，删除不可恢复。

### 产品池维护（聚合站采集 + 自动发布）

backend 服务已按以下键透传产品池维护配置（默认值见 `.env.example`）：

```yaml
CRAWL_INTERVAL_MINUTES: ${CRAWL_INTERVAL_MINUTES:-720}   # 定时维护间隔（分钟）
SEED_DEMO_PRODUCTS: ${SEED_DEMO_PRODUCTS:-false}         # 演示目录注入（生产必须 false）
AUTO_PUBLISH_ENABLED: ${AUTO_PUBLISH_ENABLED:-true}      # 高置信草稿自动发布
AUTO_PUBLISH_CONFIDENCE: ${AUTO_PUBLISH_CONFIDENCE:-0.8}
DISCOVERY_ENABLED: ${DISCOVERY_ENABLED:-true}            # 聚合站列表页产品发现
DISCOVERY_MAX_NEW_PER_SOURCE: ${DISCOVERY_MAX_NEW_PER_SOURCE:-20}
```

部署后产品池由定时任务自动维护：先从慧择/开心保列表页发现新产品详情页并注册采集任务，再抓取全部启用任务；LLM 提取的高置信草稿（字段完整、精确匹配）自动发布并写审计（`review.auto_publish`），其余进入管理后台人工审核队列。首次部署后产品池为空属预期（演示目录默认关闭），需要等首批采集发布完成或由管理员在后台手工录入产品。抓取遵守各站 robots.txt 与平台限速（慧择/开心保 10s，众安 65s 遵循 Crawl-delay: 60）。

### CORS 白名单

- 后端 `allow_credentials=True` 配合 httpOnly Cookie 认证，`CORS_ALLOW_ORIGINS` 必须配置**显式来源白名单**（逗号分隔，`http`/`https` + 主机名，可含端口）。来源值禁止带路径、查询串或片段（`http://example.com/api`、`http://example.com?x=1` 等会在启动时校验报错）。
- **任何环境都禁止 `*` 与凭据并用**（浏览器规范拒绝 `Access-Control-Allow-Origin: *` 与 `Access-Control-Allow-Credentials: true` 共存）：配置 `*` 时后端启动即失败（fail-closed）。其中 `APP_ENV=production` 在配置校验层直接拒绝 `*`；非生产环境也会被 CORSMiddleware 注册前的守卫拒绝，提示改用显式来源。
- 生产 `.env` 示例（上方）中 `CORS_ALLOW_ORIGINS=https://example.com` 即前端的部署域名；如有多个入口（如管理子域）用逗号追加：`CORS_ALLOW_ORIGINS=https://example.com,https://admin.example.com`。
- 本地开发使用默认值 `http://localhost,http://localhost:3000,http://127.0.0.1:3000`（显式 localhost 列表），无需通配。

### Cookie 与 CSRF 处置

- 登录/刷新/登出均通过 httpOnly Cookie 携带令牌，`SameSite=Lax`（默认，可设 `strict`）为对本项目 CSRF 的主要处置：跨站 POST 不再携带 Cookie，配合后端 `allow_credentials=True` 的严格 CORS 白名单（TASK-009）形成双层防护。
- `COOKIE_SECURE`：不设置时按 `APP_ENV` 推断（`production` 自动为 `true`）；`APP_ENV=production` 且显式设 `false` 会启动失败（fail-fast）。生产必须 HTTPS。
- `SameSite=None` 仅用于第三方嵌入场景，且必须同时 `COOKIE_SECURE=true`，否则浏览器拒绝该 Cookie。
- 未引入 CSRF token：纯 API 后端无表单渲染面，SameSite + CORS 已覆盖浏览器端风险；自定义客户端不受浏览器 SameSite 约束，由各自机密保护。

### 可信代理与 X-Forwarded-For

后端默认**不信任**任何代理头，一律使用直连地址；客户端伪造 `X-Forwarded-For` 无效。仅当同时满足以下条件才解析 `X-Forwarded-For`：

1. `TRUST_PROXY_HEADERS=true`；
2. 请求直连对端（`request.client`）的 IP 命中 `TRUSTED_PROXIES`（支持 IP 与 CIDR，逗号分隔）。

解析算法：从 `X-Forwarded-For` 最右端向左，跳过命中 `TRUSTED_PROXIES` 的地址，第一个非可信地址即真实客户端；全部可信或格式非法时回退到直连地址。

本仓库 Compose 拓扑为两层代理：宿主机 Nginx/Caddy（回环 `127.0.0.1`）→ frontend Nginx 容器（Compose 默认网络 `172.16.0.0/12` 段）→ backend。因此标准配置为：

```env
TRUST_PROXY_HEADERS=true
TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12
```

如改用固定网络或自定义段，`TRUSTED_PROXIES` 需包含 frontend 容器所在子网及所有在链的代理地址；直连部署（无代理）保持 `TRUST_PROXY_HEADERS=false`。

### 限流

- 按 IP：仅使用可信解析后的真实客户端 IP。
- 按用户：优先解析 `Authorization: Bearer`，其次解析 `access_token` Cookie（Cookie 登录用户级限流此前失效，已修复），两者均无效时只做匿名 IP 限流。

### 安全响应头

后端对所有响应（含限流 429）设置：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`、`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`。`SECURITY_HEADERS=false` 可整体关闭（仅测试用）。`Strict-Transport-Security: max-age=31536000; includeSubDomains` 仅在 `APP_ENV=production` 且 `HSTS_ENABLED=true` 时发送。页面本身的 CSP 建议由宿主机 Nginx 或 CDN 补充（超出本项目范围）。

## 常用命令

查看服务：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

进入后端容器：

```bash
docker compose exec backend sh
```

执行迁移：

```bash
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
```

查看当前迁移版本：

```bash
docker compose run --rm backend sh -c "cd /srv/backend && alembic current"
```

回滚到上一个版本（`alembic downgrade` 只回退迁移记录并尽量保留数据；完整回滚用备份恢复）：

```bash
docker compose run --rm backend sh -c "cd /srv/backend && alembic downgrade -1"
```

备份数据库（PostgreSQL）：

```bash
docker compose exec postgres pg_dump -U insurance insurance_prod > backup.sql
```

备份数据库（SQLite，手动/本地部署时）：

```bash
cp data/insurance.db backup-$(date +%F).db
```

恢复：先停后端，再把备份文件放回原路径（PostgreSQL 用 `psql -f backup.sql` 导入），确认无误后重启。

停止：

```bash
docker compose down
```

不要在生产执行 `docker compose down -v`，这会删除数据库 volume。

## 数据库迁移与模式门禁

### 迁移链

```text
20260706_0001 (auth/rbac) -> 20260706_0002 (data ingestion + catalog) -> 20260811_0001 (align with models, head)
```

- 空库执行 `alembic upgrade head` 会依次创建全部 23 张业务表（auth、抓取/审核、产品/规则/责任/页面日志）。
- 历史迁移按幂等方式实现：对旧版 `create_all()` 建出的库（有表、无 `alembic_version`），迁移会跳过已存在的表，只补齐与当前模型不一致的部分（例如为 `products` 补充 `deductible` 列），并写入迁移版本记录；不会删表、不会重 seed。
- 兼容 SQLite 与 PostgreSQL，无方言特有语法（列增补使用标准 `ADD COLUMN`）。

### 启动门禁

后端启动时（`init_db`）检查数据库：

1. 空库：自动 `create_all()` 建表并 stamp 到当前迁移 head（保留开发便利）。
2. 已有表但无 `alembic_version`：拒绝启动，提示先执行 `alembic upgrade head`。
3. 迁移版本不是 head：拒绝启动，提示先升级。
4. 版本是 head 但表/列与模型不一致（漂移）：拒绝启动，提示先升级。

门禁保证部署前模式不匹配被阻断，而不是静默 `create_all` 忽略差异。

### 从旧库升级

```bash
# 1. 备份
cp data/insurance.db backup-$(date +%F).db

# 2. 迁移（SQLite 本地）
cd backend && alembic upgrade head

# 或 PostgreSQL（容器内）
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"

# 3. 验证
alembic current
```

升级成功后 `alembic current` 显示 `20260811_0001`，产品数据保留，`products.deductible` 等新增列可用。

### 回滚

```bash
# 回退一个版本（保留数据，仅回退迁移记录）
alembic downgrade -1

# 完整回滚：恢复升级前的备份
cp backup-2026-08-11.db data/insurance.db
```

## 发布流程

主干为 `master`（trunk-based）。功能分支 → PR → 合入 `master` → 在 `master` 上打 tag →
生产部署 tag。完整门禁与版本号规则见 `docs/en/release-process.md`。

1. 功能分支通过 PR 合入 `master`。
2. 测试服务器部署 `master` 并验证。
3. 验证通过后在 `master` 的发布提交上打 annotated tag。
4. 生产服务器部署该 tag。

```bash
git checkout master
git pull origin master
# 版本号、CHANGELOG 已在发布提交中就位
git tag -a vX.Y.Z -m "release: vX.Y.Z"
git push origin master
git push origin vX.Y.Z
```

## AI expert mode verification

The backend reads the three LLM settings from the uppercase names used by
Compose. Keep `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in the deployment
`.env`; a lowercase-only copy such as `llm_api_key` is not interpolated by
Compose. Do not print the key while checking it.

Before starting the stack, make Compose resolve the file successfully:

```bash
test -n "${LLM_API_KEY:-}" || { echo "LLM_API_KEY is missing"; exit 1; }
docker compose config --quiet
docker compose up -d --build
docker compose logs --tail=200 backend | grep -i -E "LLM configuration|AI mode degraded|AI rerank"
```

The backend startup log reports only `configured`, `model`, and `base_url`.
For an end-to-end check, the response must contain `engine_mode: "ai"` and a
non-empty `llm_narrative`:

```bash
curl -s -X POST http://127.0.0.1:18080/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"age":30,"gender":"male","annual_income":200000,"job_class":2,"life_stage":"single","enable_llm_engine":true}'
```

If the mode is `degraded`, inspect the corresponding `AI rerank failed` log.
It includes the exception, model, and base URL but never the API key. A
`no candidate packages available` message means the product seed did not run;
check the `products` table and the backend startup logs.
