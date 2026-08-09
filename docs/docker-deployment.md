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
测试服务器：origin/develop
生产服务器：origin/master 或 release tag
```

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
git checkout develop
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
FIRST_ADMIN_PASSWORD=首次部署临时密码
SCORING_WEIGHTS_FAIL_FAST=true
LLM_API_KEY=填写测试环境 LLM Key
```

构建并启动基础服务：

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend alembic -c alembic.ini upgrade head
docker compose up -d --build
docker compose ps
```

验证：

```bash
curl http://127.0.0.1:18080/healthz
curl http://127.0.0.1:18080/api/products
docker compose logs -f backend
```

## 更新测试环境

```bash
cd /opt/insurance-staging
git fetch origin
git checkout develop
git pull origin develop
docker compose build
docker compose run --rm backend alembic -c alembic.ini upgrade head
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
git checkout v0.3.0
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
```

启动：

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend alembic -c alembic.ini upgrade head
docker compose up -d --build
```

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
docker compose run --rm backend alembic -c alembic.ini upgrade head
```

备份数据库：

```bash
docker compose exec postgres pg_dump -U insurance insurance_prod > backup.sql
```

停止：

```bash
docker compose down
```

不要在生产执行 `docker compose down -v`，这会删除数据库 volume。

## 发布流程

1. 推送 `develop`。
2. 测试服务器部署 `develop` 并验证。
3. 验证通过后合并到 `master`。
4. 打 release tag。
5. 生产服务器部署 tag。

```bash
git checkout master
git pull origin master
git merge --no-ff develop
git push origin master
git tag -a v0.3.0 -m "release: auth ingestion and stage3 recommendations"
git push origin v0.3.0
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
