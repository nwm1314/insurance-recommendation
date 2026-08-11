# 智能保险推荐项目全面审查与改造方案

> 历史审查与改造方案（2026-07-06）。文中的建议和问题是当时的快照，未标记为 DONE 的内容不得视为当前已交付能力；当前状态以代码、测试和最新任务卡为准。

日期：2026-07-06

## 1. 审查结论

当前项目已经具备“问卷画像 -> 规则筛选 -> 评分 -> 套餐组合 -> 结果展示”的 MVP 闭环，但离“公开部署、持续抓取各平台保险数据、可运营管理”的产品级系统还有较大差距。

主要短板集中在 5 类：

1. 数据来源仍是种子脚本和单页校验脚本，尚未形成可持续的数据接入平台。
2. 推荐算法可解释性有雏形，但评分口径、险种分组、预算约束和健康核保逻辑还不够严谨。
3. 前端问卷和结果展示可用，但缺少转化路径、保存方案、登录态、历史记录、风险解释和移动端优化。
4. 管理后台完全公开，`/api/admin/*` 无认证、无授权、无审计，不适合部署到公网。
5. 目前 SQLite + 开放 CORS + 无账号体系 + 无 HTTPS/安全头/迁移工具，不适合海外服务器公开运营。

## 2. 关键问题清单

### 2.1 高风险安全问题

1. `backend/app/api/admin.py` 的 `/api/admin/crawl` 完全无鉴权，任何公网用户都可以触发后台任务。
2. `frontend/src/App.tsx` 直接暴露“管理后台”入口，且没有路由保护。
3. `backend/main.py` CORS 使用 `allow_origins=["*"]` 且 `allow_credentials=True`，公网部署存在跨站调用风险。
4. `backend/app/middleware/rate_limiter.py` 只有 IP 级限流，没有 README 中描述的用户级 `3 次/分钟`、`50 次/天`。
5. 工作区存在 `.env` 文件，公开部署前必须确认未提交、未泄露、未被镜像打包。

### 2.2 中高风险工程问题

1. `backend/app/database.py` 使用 `Base.metadata.create_all` 自动建表，没有 Alembic 迁移。
2. `docker-compose.yml` 仍使用 SQLite，公开服务应迁移到 PostgreSQL。
3. `docker-compose.yml` 将 Redis 暴露到宿主机 `6379:6379`，线上不应公开 Redis 端口。
4. `backend/app/api/products.py` 产品不存在时返回 `({"error": ...}, 404)`，不是标准 FastAPI 404。
5. `backend/app/crawler/scheduler.py` 只启动 scheduler，没有注册任何定时抓取 job。

### 2.3 推荐算法问题

1. README、注释和代码存在“6 维/8 维评分”口径不一致。
2. `backend/app/engine/scoring.py` 的 `apply_price_scoring` 存在价格分重复加分问题。
3. 价格竞争力在所有险种混合池里算，不同险种保费量级不可直接比较。
4. `filter_candidate_pool` 用 `premium_max <= annual_income * budget_ratio` 做候选过滤，会剔除很多低档可选产品。
5. `preferred_companies` 的梯队加权逻辑区分度不足。
6. 健康风险只是“有异常就提示”，没有按疾病、险种、健康告知、核保宽松度做匹配。
7. 流式 AI 分支异常不会可靠触发 fallback，当前前端也没有真正使用 SSE。
8. YAML 中每个收入层的 `budget_ratio` 没被使用，需要明确产品策略。

### 2.4 数据采集问题

1. 种子数据依赖人工维护，缺少来源版本、置信度和审核状态。
2. 单页抓取没有 robots 检查、站点限速、失败重试、代理策略、反爬处理、截图/HTML 存档。
3. LLM 抽取只做 JSON parse，没有 Pydantic schema 校验、字段置信度、单位归一化、枚举纠错和人工审核队列。
4. 爬虫校验脚本只更新 `PageLog`，不更新产品主数据，也没有变更 diff 审核流。
5. `Rule.health_requirements` 类型语义不一致，字段声明为 `dict`，默认值是 `list`。
6. 目前没有 `source_registry`、`crawl_jobs`、`crawl_runs`、`extraction_runs`、`product_versions` 这类运营数据表。

### 2.5 前端问题

1. 首页点击“下一步”不会校验当前步骤字段。
2. 结果页 `useEffect` 依赖为空，但内部使用 `doRecommend`。
3. `useSSE` 只是 AbortController 容器，没有真正消费流式响应。
4. `CompareTable` 的等待期和豁免条款 tooltip 错位。
5. `ScoreDetail` 缺少 `brand` 和 `service`，后端实际返回 8 维。
6. 管理页请求失败没有 catch。
7. 结果页没有方案保存、分享、历史记录、线索收集、继续咨询 CTA。

## 3. 数据打通方案

建议不要一开始追求“全网自动抓取所有产品”，而是建立“合规可维护的数据供应链”，分三层接入。

### 3.1 第一层：官方与监管公开数据

1. 接入国家金融监督管理总局、保险行业协会、各保险公司公开产品页、条款 PDF、信息披露页。
2. 优先采集字段：公司、产品名、备案/条款名称、在售状态、险种、投保年龄、职业类别、等待期、保障期间、缴费期间、责任摘要、免责/健康告知链接。
3. 官方站点作为“权威校验源”，不一定作为价格源。
4. 每条产品数据增加 `official_url`、`terms_pdf_url`、`official_checked_at`、`official_md5`、`official_status`。

### 3.2 第二层：第三方保险平台数据

1. 优先调研和适配：慧择、开心保、中民保险网、深蓝保、小雨伞、支付宝蚂蚁保、微信保险服务、京东保险、水滴保、众安官网、平安健康、人保健康等。
2. 第三方平台适合作为“价格、卖点、保障责任、投保入口”的补充源。
3. 推荐策略是“第三方平台抓商品结构，官方站点校验条款和状态”。
4. 优先寻找公开 API、页面 JSON、SSR 数据、站点地图、RSS 或可公开访问的商品接口，最后才用 Playwright。

### 3.3 第三层：人工审核与运营维护

1. LLM 抽取后的数据不要直接进入推荐池，应进入 `pending_review`。
2. 后台提供字段 diff：旧值、新值、来源、置信度、截图/HTML/PDF 证据。
3. 审核通过后生成 `product_versions`，推荐引擎只读取 `approved + active` 的版本。
4. 对关键字段设置强审核：年龄、职业、等待期、保费、保额、责任免除、健康告知、是否在售。

### 3.4 推荐开源组件

1. `Scrapy`：多站点、可扩展、队列化、限速、重试、pipeline 入库。
2. `Playwright`：JS 渲染、反爬较强、需要交互的页面。
3. `BeautifulSoup4 + lxml`：静态页面和 HTML 清洗。
4. `Crawlee for Python`：现代化爬虫队列、请求去重、浏览器池。
5. `trafilatura`：正文抽取。
6. `pdfplumber` 或 `PyMuPDF`：保险条款 PDF 抽取。
7. `Instructor + Pydantic`：结构化抽取、校验和自动重试。
8. `Celery + Redis` 或 `RQ + Redis`：异步抓取任务。
9. `APScheduler`：保留做轻量定时，负责投递任务。
10. `Alembic`：数据库迁移。
11. `PostgreSQL + pgvector`：条款语义检索、产品相似度、问答解释。

### 3.5 建议新增采集模块结构

```text
backend/app/data_ingestion/
  sources/
    huize.py
    kaixinbao.py
    zhongmin.py
    pingan.py
    zhongan.py
  fetchers/
    http_fetcher.py
    playwright_fetcher.py
    pdf_fetcher.py
  extractors/
    html_extract.py
    pdf_extract.py
    llm_extract.py
  validators/
    product_schema.py
    normalize.py
    consistency.py
  pipelines/
    crawl_product.py
    verify_product.py
    publish_product.py
```

### 3.6 建议新增数据表

```text
source_platforms
source_pages
crawl_jobs
crawl_runs
raw_documents
extraction_runs
product_drafts
product_versions
product_review_tasks
product_field_evidence
```

## 4. 推荐算法改造方案

### 4.1 第一阶段：修正确性问题

1. 修复 `apply_price_scoring` 总分重复加价格分的问题。
2. 价格分按险种分别计算，不同险种不要混合比较保费。
3. 保费准入从 `premium_max <= budget` 改成 `premium_min <= type_budget` 或套餐阶段约束。
4. `ScoreDetail` 前后端统一为 8 维。
5. README、注释、前端 tooltip 统一为“8 维评分”。
6. 修复 CompareTable tooltip 错位。
7. `preferred_companies` 改成明确加分，只给命中的公司或同集团公司加分。

### 4.2 第二阶段：增强推荐质量

1. 建立“险种内评分模型”，医疗险、重疾险、意外险、寿险、防癌险分别有不同权重。
2. 医疗险重点：保证续保、免赔额、报销比例、特药、质子重离子、外购药、院外药、健康告知。
3. 重疾险重点：病种质量、轻中症赔付比例、多次赔付、身故责任可选、保费杠杆、等待期。
4. 意外险重点：意外医疗额度、免赔额、报销比例、猝死、交通意外、职业限制。
5. 寿险重点：免责条款、健康告知、等待期、可投保额、价格、职业范围。
6. 防癌险重点：可投年龄、既往症限制、保证续保、癌症医疗额度、特药服务。
7. 引入“刚性规则”和“软性偏好”分离，刚性规则不可被 AI 覆盖。
8. 增加“不推荐原因”。
9. 增加“方案完整度”。
10. 增加“预算利用率”。

### 4.3 第三阶段：AI 能力边界

1. AI 只做解释、摘要、相似产品对比、个性化话术，不直接选择不合规产品。
2. AI 输入只包含规则引擎筛选后的安全候选池。
3. AI 输出使用结构化 schema，例如 `selected_product_ids`、`reasoning`、`risk_notes`。
4. 对 AI 结果做产品 ID 白名单校验。
5. 对推荐语增加合规约束：不得承诺收益、不得保证承保、不得替代专业顾问、不得诱导隐瞒健康告知。

## 5. 前端改造方案

### 5.1 问卷流程

1. 改成“渐进式画像”，每一步提交前校验当前步骤字段。
2. 首页先问核心问题：年龄、预算、家庭责任、已有保障、健康异常。
3. 健康异常支持搜索、分组、严重程度、核保提示。
4. 增加“我不确定”选项。
5. 增加隐私提示。
6. 登录用户支持保存草稿，未登录用户本地临时保存。

### 5.2 结果页

1. 顶部展示“推荐结论摘要”：预算、保障缺口、首推方案、主要风险。
2. 每个方案增加“适合谁/不适合谁/注意事项”。
3. 产品卡增加官方条款、来源平台、数据更新时间、置信度。
4. 横向对比增加高亮差异。
5. 增加“为什么推荐这个产品”和“为什么没有推荐某类产品”。
6. 增加“保存方案”“重新生成”“导出 PDF”“预约咨询/联系顾问”。
7. 移动端将横向表格改为卡片对比或可折叠字段。

### 5.3 管理后台

1. 拆成产品管理、数据源管理、抓取任务、审核队列、用户管理、角色权限、系统日志。
2. 产品列表支持按公司、险种、状态、来源、置信度、更新时间筛选。
3. 审核页展示字段 diff、原网页证据、条款 PDF、LLM 抽取结果和人工确认按钮。
4. 爬虫页支持手动触发、任务进度、失败重试、错误原因、抓取日志。
5. 用户管理支持禁用用户、重置密码、调整角色、查看登录历史。

## 6. 注册与 RBAC 方案

### 6.1 核心能力

1. 用户注册。
2. 邮箱登录。
3. JWT access token + refresh token。
4. 密码哈希使用 `argon2` 或 `bcrypt`。
5. RBAC 权限模型。
6. 管理后台路由保护。
7. API 权限依赖。
8. 审计日志。
9. 用户状态管理：active、disabled、pending_verification。
10. 公开访问和登录访问分层。

### 6.2 建议角色

```text
anonymous:
  提交一次性推荐
  查看公开产品基础信息

user:
  保存问卷
  查看个人历史推荐
  收藏产品
  导出自己的方案

advisor:
  查看被授权用户方案
  添加咨询备注
  不可改产品基础数据

operator:
  管理产品草稿
  触发爬虫
  审核数据变更
  查看抓取日志

admin:
  用户管理
  角色管理
  权限管理
  系统配置

super_admin:
  全部权限
  安全配置
  API Key 管理
```

### 6.3 建议权限粒度

```text
product:read
product:create
product:update
product:publish
product:delete
crawl:read
crawl:trigger
crawl:cancel
review:read
review:approve
user:read
user:create
user:update
user:disable
role:read
role:update
recommendation:read_self
recommendation:read_all
audit:read
system:configure
```

### 6.4 建议新增表

```text
users
roles
permissions
user_roles
role_permissions
sessions
refresh_tokens
password_reset_tokens
email_verification_tokens
audit_logs
recommendation_records
saved_profiles
```

### 6.5 建议 API

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me

GET  /api/users
PATCH /api/users/{id}
POST /api/users/{id}/roles

GET  /api/roles
POST /api/roles
PATCH /api/roles/{id}
POST /api/roles/{id}/permissions

GET  /api/audit-logs

GET  /api/my/recommendations
POST /api/my/profiles
GET  /api/my/profiles
```

## 7. 海外公开部署方案

### 7.1 基础架构

1. 后端：FastAPI + Uvicorn/Gunicorn。
2. 前端：Nginx 静态托管。
3. 数据库：PostgreSQL。
4. 缓存/队列：Redis 私网访问。
5. 对象存储：保存 HTML 快照、PDF 条款、截图。
6. 反向代理：Nginx 或 Caddy。
7. TLS：Let's Encrypt。
8. 日志：结构化 JSON 日志。
9. 监控：Prometheus + Grafana 或轻量 Uptime Kuma + Sentry。

### 7.2 线上安全基线

1. 关闭 `allow_origins=["*"]`，改成明确域名白名单。
2. Redis 不暴露公网端口。
3. PostgreSQL 不暴露公网端口。
4. 所有 secrets 使用服务器环境变量或 Secret Manager，不写入镜像。
5. 设置 `SECURE_COOKIE`、`SameSite=Lax/Strict`、`HttpOnly`。
6. Nginx 增加 `X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy`、`Content-Security-Policy`。
7. 增加全局请求体大小限制。
8. 登录、注册、AI 推荐、爬虫触发分别设置不同限流。
9. 后台管理路径必须强认证，建议支持 MFA。
10. 定期备份 PostgreSQL 和对象存储。

### 7.3 合规与免责声明

1. 明确产品为“信息展示与算法辅助推荐”，不是保险销售代理或承保承诺。
2. 结果页显著提示“最终以保险公司官方条款、健康告知和核保结果为准”。
3. 如果公开面向海外用户，需要确认目标地区是否涉及保险销售牌照、金融建议牌照、数据隐私要求。
4. 对中国保险产品面向海外访问时，避免误导非适用地区用户投保。
5. 健康、收入、家庭信息属于敏感数据，应提供隐私政策、删除账户、导出数据能力。
6. 如果服务面向欧盟用户，需要考虑 GDPR；面向加州用户需考虑 CCPA/CPRA。

## 8. 实施路线

### 8.1 第 0 阶段：立即修复，1-2 天

1. 隐藏或保护管理后台入口。
2. 给 `/api/admin/*` 加临时 admin token 或 Basic Auth，作为正式 RBAC 前的止血。
3. 修复 CORS 白名单。
4. 修复价格评分重复加分。
5. 修复产品详情 404。
6. 修复 CompareTable tooltip 错位。
7. 前后端统一 8 维评分类型。
8. Redis 端口不再公开暴露。
9. 确认 `.env` 未提交，轮换可能泄露的密钥。

### 8.2 第 1 阶段：账号与权限，1-2 周

1. 引入 Alembic。
2. 迁移 PostgreSQL。
3. 新增 users、roles、permissions、audit_logs。
4. 实现注册、登录、JWT、刷新 token。
5. 实现 `require_permission`。
6. 管理后台接入登录态和权限菜单。
7. 推荐记录与用户绑定。
8. 加用户级限流。

### 8.3 第 2 阶段：数据采集平台，2-4 周

1. 设计 source registry 和数据版本表。
2. 将现有 `crawl_and_verify.py` 拆成 fetch、extract、validate、review、publish。
3. 优先接入 3 个第三方平台 + 3 个官方站点。
4. 引入 Pydantic/Instructor 严格抽取。
5. 加 HTML/PDF 原文存档。
6. 加字段置信度和人工审核队列。
7. APScheduler 投递任务到 Celery/RQ。
8. 后台展示抓取任务和审核 diff。

### 8.4 第 3 阶段：推荐算法升级，2-3 周

1. 险种分模型。
2. 预算按险种分配和套餐约束。
3. 健康异常与产品健康告知建立映射。
4. 增加不推荐原因。
5. 增加推荐解释。
6. AI 输出结构化并二次校验。
7. 增加推荐质量测试集。
8. 对典型用户画像做回归测试。

### 8.5 第 4 阶段：前端产品化，2-3 周

1. 优化问卷校验与步骤体验。
2. 结果页改成“摘要 + 方案 + 解释 + 对比 + CTA”。
3. 移动端适配结果卡片和对比表。
4. 增加方案保存、历史记录、导出 PDF。
5. 管理后台新增用户、角色、权限、审核队列。
6. 增加错误态、空态、加载态和权限态。

### 8.6 第 5 阶段：公网部署与运营，1-2 周

1. Docker Compose 拆分 dev/prod。
2. 上 PostgreSQL、Redis 私网、Nginx TLS。
3. 配置域名、HTTPS、安全头。
4. 配置备份和恢复演练。
5. 接入 Sentry 或日志监控。
6. 压测推荐接口和 AI 降级链路。
7. 完成隐私政策、服务条款、免责声明。
8. 上线灰度，只开放少量用户测试。

## 9. 优先级建议

第一优先级是安全止血：管理后台鉴权、CORS、Redis 端口、评分 bug。

第二优先级是数据可信：采集管线、审核流、产品版本和来源证据。

第三优先级是账号体系：注册登录、RBAC、用户历史、审计。

第四优先级是推荐体验：险种分模型、健康核保解释、结果页转化。
