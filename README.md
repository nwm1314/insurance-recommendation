# 智能保险推荐引擎

基于 **规则树召回 + AI 精排** 双引擎的全栈保险推荐系统。不依赖任何商业保险 API，通过 Python 爬虫 + 大模型结构化解析构建产品数据库，为用户提供个性化保险方案推荐。

## 架构概览

```
用户问卷(七维画像) → 规则树粗筛(一票否决) → 8维评分算法 → 贪心套餐构建 → 双引擎路由
                                                                          ├─ 极速模式: 直接输出 (<1s)
                                                                          └─ AI 模式: 在候选池白名单内选择排序并生成解释（同步 JSON）
```

- **数据采集层**: Playwright/BeautifulSoup 抓取 + OpenAI-compatible LLM 提取 + Pydantic 校验
- **推荐引擎层**: 规则引擎（合规筛选/评分/组包）+ AI 引擎（候选池白名单内精排与解释）
- **网关防护层**: 基于 Redis 原子计数器的固定窗口限流（故障时放行）

## 功能特性

- **七维用户画像**: 年龄、人生阶段、收入、职业风险、健康状态、家庭负担、已有保障；支持社保身份、职业名称自动解析等级、已有保单明细（参与保额缺口分析）
- **一票否决机制**: 年龄不符、职业超限、停售产品自动剔除；0-17 岁禁推寿险（硬禁止）；56 岁以上默认不推荐重疾险，产品可投时除外；防癌险按年龄与预算可选
- **8 维产品评分**: 分险种权重（见 `backend/config/scoring_weights.yaml` 的 `type_weights`）——保障全面性、保费竞争力、投保宽松度、等待期、豁免条款、保额充足度、品牌信任度、增值服务；保费竞争力按同险种排名百分位计分，未披露保费的产品取中性分
- **智能预算分配**: 按绝对年预算分层决定可选险种集合（`budget_rules.yaml` 的 `absolute_budget_tiers`），用户预算占比仅决定总预算
- **三层套餐方案**: 低保费优先 / 均衡配置 / 高保额优先，贪心算法在预算约束下自动组合；后两套带一次缺失险种置换与按险种保额缺口分析。三套方案仅**预算档位与保障完整度**不同，不存在"哪套更好"，命名刻意避免暗示价格越高越优
- **双引擎路由**: 极速规则模式与 AI 精排模式（同步 JSON）；硬规则粗筛与预算上限不可被 AI 覆盖，AI 仅在候选池白名单内做个性化选择与排序；AI 模式有每日配额与结果短缓存（Redis，故障时放行）
- **优雅降级**: LLM 异常时自动切换至极速模式，保证核心业务流程不中断
- **健康告知预警**: 异常项标红提示，引导智能核保
- **产品横向对比**: 高亮保费差异与保障差异，保费倒挂预警
- **结果页下一步说明**（OPEN-001）: 结果页明示本工具是辅助决策工具——不提供实时核保、不出具有效报价，评分与排序仅代表匹配度；引导用户核对产品来源页、逐项核对健康告知、投保前咨询保险公司官方客服。未披露保费上限的产品在产品卡与横向对比表中**一致标注「起」**，不被伪装成精确价格。本期**不提供投保跳转与留资入口**

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 后端 | FastAPI + SQLAlchemy + Pydantic + APScheduler |
| 爬虫 | Playwright + BeautifulSoup4 |
| AI | OpenAI 兼容接口 + Pydantic 结构化校验（支持 DeepSeek 等模型） |
| 存储 | SQLite（开发期）+ Redis（限流） |
| 部署 | Docker Compose（后端 + 前端 Nginx + Redis） |

## 项目结构

```
insurance_recommendation/
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── app/
│   │   ├── api/                    # REST API 路由
│   │   │   ├── recommend.py        # POST /api/recommend（同步 JSON）
│   │   │   ├── products.py         # GET /api/products, /api/compare
│   │   │   └── admin.py            # 爬虫触发 & 健康检查
│   │   ├── engine/                 # 推荐引擎核心
│   │   │   ├── rule_engine.py      # 规则树粗筛（一票否决 → 候选池）
│   │   │   ├── scoring.py          # 8 维产品评分算法
│   │   │   ├── budget.py           # 预算分配 & 保额计算
│   │   │   ├── combo_builder.py    # 贪心套餐组合构建
│   │   │   ├── ai_engine.py        # LLM 解释 + JSON/白名单校验
│   │   │   ├── fallback.py         # 熔断降级
│   │   │   └── models.py           # 引擎内部数据类
│   │   ├── crawler/                # Playwright/BeautifulSoup + LLM 提取
│   │   ├── models/                 # SQLAlchemy ORM
│   │   ├── schemas/                # Pydantic 校验
│   │   ├── services/               # 业务逻辑
│   │   ├── middleware/             # Redis 令牌桶限流
│   │   ├── config.py               # 配置管理
│   │   └── database.py             # 数据库连接
│   ├── config/
│   │   ├── scoring_weights.yaml    # 评分权重 & 公司梯队配置
│   │   └── budget_rules.yaml       # 预算分配规则 & 保额公式
│   └── scripts/
│       ├── seed.py                 # 种子数据（165 款产品）
│       └── crawl_and_verify.py     # 爬虫巡检脚本
├── frontend/
│   ├── src/
│   │   ├── components/             # UI 组件
│   │   │   ├── ProgressSteps.tsx    # 步骤条
│   │   │   ├── EngineSwitch.tsx     # AI/极速模式开关
│   │   │   ├── BudgetPreview.tsx    # 预算分配饼图
│   │   │   ├── ScoreRadar.tsx       # 8 维评分雷达图
│   │   │   ├── ProductCard.tsx      # 产品卡片（可跳转 source_url）
│   │   │   ├── CompareTable.tsx     # 横向对比表格
│   │   │   ├── RiskBadge.tsx        # 健康风险预警标签
│   │   │   └── Disclaimer.tsx       # 合规声明
│   │   ├── pages/
│   │   │   ├── HomePage.tsx         # 4 步骤七维画像问卷
│   │   │   ├── ResultPage.tsx       # 推荐结果 & 横向对比
│   │   │   └── AdminPage.tsx        # 管理后台
│   │   ├── api/                    # Axios 封装
│   │   └── types/                  # TypeScript 类型定义
│   ├── nginx.conf                  # 生产环境 Nginx 配置
│   └── Dockerfile
├── docker-compose.yml              # 一键启动 Redis + 后端 + 前端
└── docs/                           # 设计文档 & 实施计划
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 22+
- Docker & Docker Compose（可选）
- Redis（Docker 模式自动启动，手动模式可选）

### Docker 一键启动

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 填入大写 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL；Compose 会拒绝缺少 LLM_API_KEY 的配置

# 启动所有服务
docker compose up -d --build

# 初始化种子数据
docker compose exec backend python scripts/seed.py
```

访问:
- 前端: http://localhost
- 后端 API 文档: http://localhost:8000/docs

> **单副本要求**：backend 内嵌 APScheduler（定时抓取调度），必须以单副本运行；多副本部署时在非主副本上设置 `SCHEDULER_DISABLED=true` 关闭调度，避免重复触发抓取任务。

### 手动启动

```bash
# 1. 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 初始化数据库和种子数据
python scripts/seed.py

# 启动后端 (http://localhost:8000)
python -m uvicorn main:app --reload

# 2. 前端 (新终端)
cd frontend
npm install
npm run dev  # http://localhost:3000
```

### 运行测试

在仓库根目录执行（三条命令相互独立）：

```powershell
# 1. 后端全量测试（每个测试文件使用独立临时 SQLite；Redis 由 tests/conftest.py 隔离）
./backend/venv/Scripts/python.exe -m pytest backend/tests -q

# 2. 前端构建（含 tsc 类型检查）
cd frontend; npm run build

# 3. E2E（自起真实后端 + vite，产物落 frontend/test-results/ 与 frontend/playwright-report/）
cd frontend; npx playwright test
```

**测试端口与常见故障**：E2E 默认占用 **3000**（前端）与 **8000**（后端），且
`reuseExistingServer: false` —— 端口被占用时 Playwright 会**直接失败**而不是复用，
vite 亦以 `--strictPort` 启动，不会静默改用 3001。

若报 `http://localhost:3000 is already used`，说明有残留的 dev server 占用端口（常见于
上次调试中断后）。处置：

```powershell
# 查看并结束占用 3000 / 8000 的进程（Windows）
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

也可用环境变量改端口：`$env:E2E_FRONTEND_PORT=3100; $env:E2E_BACKEND_PORT=8100; npx playwright test`。

**数据库迁移门禁**：应用启动时 `verify_schema_integrity()` 会校验模型与 Alembic 迁移一致。
若报 `Database schema is at migration 'xxxx' but the current Alembic head is 'yyyy'`，
说明本地库停留在旧版本（`data/insurance.db` 为默认开发库，位于 `.gitignore`），执行：

```bash
cd backend && alembic upgrade head
```

### 管理员初始化

公开注册的用户只获得普通 `user` 角色。首个管理员通过环境变量受控创建（幂等，已存在则不重复创建，创建动作写入审计日志 `auth.first_admin.bootstrap`，密码不写入日志；创建完成后建议清空 `FIRST_ADMIN_PASSWORD`）：

```bash
FIRST_ADMIN_EMAIL=admin@example.com FIRST_ADMIN_PASSWORD=强密码 python -m uvicorn main:app --reload
```

之后由既有管理员通过 `POST /api/admin/users/{user_id}/roles`（请求体 `{"roles": ["admin"]}`，需 `admin:grant` 权限）授予其他管理员，操作同样写入审计日志。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///data/insurance.db` | 数据库连接串 |
| `REDIS_URL` | `redis://localhost:6379` | Redis 连接串 |
| `LLM_API_KEY` | - | LLM API 密钥（DeepSeek/OpenAI 等） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM API 地址 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `LLM_MAX_TOKENS` | `2048` | 结构化 AI 输出上限 |
| `LLM_READ_TIMEOUT` | `90.0` | LLM 读取超时（秒） |

### 安全配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | `development\|test\|staging\|production`；`production` 下 `COOKIE_SECURE` 强制为 true |
| `COOKIE_SECURE` | 按环境推断 | httpOnly Cookie 的 Secure 标志；不设置时 production 自动为 true，显式设 false 且 APP_ENV=production 会启动失败 |
| `COOKIE_SAMESITE` | `lax` | `lax\|strict\|none`；`none` 必须配合 `COOKIE_SECURE=true`。SameSite=Lax 是本项目对 CSRF 的主要处置 |
| `TRUST_PROXY_HEADERS` | `false` | 为 true 且直连对端命中 `TRUSTED_PROXIES` 时才解析 `X-Forwarded-For`，否则一律用直连地址，伪造 XFF 无效 |
| `TRUSTED_PROXIES` | 空 | 可信代理列表（IP 或 CIDR，逗号分隔），格式非法启动报错 |
| `SECURITY_HEADERS` | `true` | 安全响应头开关（nosniff / X-Frame-Options / Referrer-Policy / CSP） |
| `HSTS_ENABLED` | `false` | 发送 `Strict-Transport-Security`，仅 `APP_ENV=production` 时生效 |
| `RECORD_ENCRYPTION_KEY` | 空 | 推荐记录落库加密密钥（Fernet，任意字符串自动派生）；为空明文落库并在启动时告警（测试/开发为 warning，`APP_ENV=production` 升级为 error）。**对外内测/生产必须配置** |
| `RECORD_RETENTION_DAYS` | `0` | 健康信息保留天数预留（0=永久），本期不实现清理任务 |
| `AI_DAILY_LIMIT_PER_USER` | `20` | AI 模式每日配额（登录按用户、匿名按 IP） |
| `AI_CACHE_TTL_SECONDS` | `3600` | AI narrative 短缓存 TTL（Redis，故障跳过） |
| `CORS_ALLOW_ORIGINS` | `http://localhost,http://localhost:3000,http://127.0.0.1:3000` | 逗号分隔的显式来源白名单（http/https，可含端口）；禁止带路径/查询串；`APP_ENV=production` 拒绝 `*`，且任何环境 `*` 都不能与 `allow_credentials=True`（Cookie 认证必需）并用 |

Cookie 登录用户计入用户级限流（限流优先解析 Bearer 头，其次解析 `access_token` Cookie）。详见 `docs/docker-deployment.md` 的“安全配置”章节。

**推荐记录加密与保留**：设置 `RECORD_ENCRYPTION_KEY` 后，推荐记录的画像与结果（含健康描述）以 Fernet 加密落库（任意字符串密钥自动派生）；密钥为空则明文落库并在启动时告警（显式降级，非静默），其中 `APP_ENV=production` 下升级为 **error** 级。由于推荐记录含 `health_status` / `health_issues` 等敏感个人信息，**对外内测与生产部署必须配置该密钥**（配置方式与注意事项见 `docs/docker-deployment.md` 的「推荐记录加密」章节）。加密仅覆盖推荐记录——数据库文件/备份仍需按敏感数据处理。健康信息保留期限以 `RECORD_RETENTION_DAYS`（0=永久）预留，当前版本不实现自动清理任务。

## 已知限制

- **报价口径**：接口返回的 `premium` 为报价区间下限，实际以核保为准；不同产品报价条件（年龄/保额/缴费期）可能不同（响应 `premium_basis_note` 有固定说明）
- **保额单位**：存储规范统一为万（`sum_insured_*` 单位=万，`premium_*`/`deductible` 单位=元）
- **地区维度**：投保地区字段未支持（产品侧暂无投保地区数据，画像未提供该字段）
- **AI 配额**：AI 模式每用户/匿名 IP 每日 20 次（`AI_DAILY_LIMIT_PER_USER`），超限自动降级极速模式

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/recommend` | 提交七维画像，返回同步 JSON 套餐方案（AI 模式为解释性补充） |
| `GET` | `/api/products` | 产品列表（支持分页、`type`、名称/公司搜索） |
| `GET` | `/api/products/{id}` | 产品详情 + 保障责任明细 |
| `POST` | `/api/compare` | 多产品横向对比 |
| `POST` | `/api/admin/crawl` | 手动触发爬虫 |
| `GET` | `/api/admin/logs` | 爬虫/解析日志 |
| `GET` | `/api/admin/health` | 健康检查 |

推荐请求示例:

```json
{
  "age": 32,
  "gender": "male",
  "annual_income": 200000,
  "job_class": 2,
  "life_stage": "married_with_kids",
  "family_burden": "dual",
  "health_status": "substandard",
  "health_issues": ["nodule"],
  "existing_coverage": ["social"],
  "budget_ratio": 0.08,
  "enable_llm_engine": false
}
```

## 推荐引擎详解

### 第一层：规则树粗筛（纯 SQL，不可绕过）

- 年龄不在 [min_age, max_age] → 剔除
- 职业等级 > job_class_limit → 剔除
- status = 0（停售）→ 剔除
- 0-17 岁 + 寿险 → 绝对不推
- 56 岁以上 + 重疾险 → 默认不推荐；产品自身投保年龄覆盖用户时该产品仍可入池
- 报价下限超过对应险种预算 → 剔除
- 套餐组装同时检查已知报价上限；未披露上限的产品标记"起/以核保为准"，不被伪装成精确价格

输出合法合规的「安全候选池」。

### 第二层：8 维评分算法

评分权重通过 `config/scoring_weights.yaml` 管理，按险种配置（`type_weights`）；等待期最优值支持按险种覆盖（意外险 0 天满分、医疗险 30 天）。保费竞争力在同险种内按排名百分位计分（最便宜满分、最贵 0 分），未披露保费的产品取中性分不参与排名。公司梯队偏好按用户画像动态调整（高收入偏好品牌、健康异常偏好核保灵活、年轻用户偏好性价比）。

### 第三层：贪心套餐组合

候选池 → 险种匹配矩阵 → 预算约束贪心选取 → 3 套方案（性价比/全面/尊享），每套按基础层(医疗+意外) → 核心层(重疾+寿险) → 补充层(防癌/年金) 组织。全面/尊享套餐在缺失 required 险种时执行一次置换（completeness 提升才采纳）；每套输出按险种的保额缺口（建议保额、已有覆盖、缺口，单位元）。

### 第四层：双引擎路由

- **极速模式** (`enable_llm_engine: false`): 规则树 → 评分 → 套餐组合 → 直接输出，1 秒内响应
- **AI 模式** (`enable_llm_engine: true`): 规则树 → 评分 → 套餐组合 → LLM 在候选池白名单内做个性化选择排序并生成结构化解释；产品 ID 受输入白名单约束，不能新增/替换产品。当前接口为同步 JSON，不提供 SSE。AI 模式有每日配额（登录用户 20 次/天，匿名按 IP）与 narrative 短缓存（1 小时，命中时返回 `ai_from_cache=true`）；Redis 故障时跳过缓存与配额（fail-open）
- **降级**: LLM 异常 → 自动切换极速模式，提示「AI 线路繁忙，已自动切换至极速专家推荐」

## 高可用设计

- **限流**: 默认 120 次/分钟/IP、30 次/分钟/用户、300 次/天/用户，基于 Redis 原子计数器（Lua 脚本单次完成 INCR+EXPIRE）的固定窗口限流；Redis 不可用时放行（fail-open）并记录运行风险，恢复后自动回归限流
- **超时**: LLM 连接默认 3s、读取默认 90s；实际值由 `LLM_CONNECT_TIMEOUT` / `LLM_READ_TIMEOUT` 配置
- **降级**: LLM 异常自动切换极速模式，核心业务流程不中断

## 数据采集 Pipeline 与产品池维护

```
聚合站列表页发现（慧择/开心保，robots 校验）→ 注册产品页采集任务
                                                        ↓
配置的数据源页面 → SSRF/robots 校验 → 抓取 HTML/纯文本 → MD5 比对（内容未变化则跳过）
                                                        ↓
                         OpenAI-compatible LLM 提取 + Pydantic 白名单校验
                                                        ↓
            高置信草稿（LLM 提取、置信度 ≥ AUTO_PUBLISH_CONFIDENCE、字段完整、
            精确匹配门控）自动发布并写审计；其余 `pending_review` 人工审核
                                                        ↓
                  发布 Product/Rule/Benefit/Version（真实来源页 URL）
                                                        ↓
           识别停售/不可投保页面后自动下架（精确匹配）；调度间隔由 `CRAWL_INTERVAL_MINUTES` 控制
```

**产品池策略**：以聚合站（慧择、开心保，robots.txt 均允许产品页抓取）为主数据源，深蓝保等测评站与保险公司官网作为补充验证源；中民保险网等 robots.txt 全站禁抓的站点已停用。只有审核（或达标自动）发布后的产品才进入推荐池，产品链接指向真实来源页（`source_type=aggregator` 标"产品页"，官网链接标"官网"）。生产环境不注入演示目录（`SEED_DEMO_PRODUCTS=false`），演示种子仅用于本地开发与 E2E。自动发布有硬性安全门：启发式抽取永不自动发布、占位值/缺失关键字段拦截、模糊匹配（同名系列产品）必须人工确认。系统不提供实时核保或保险公司报价 API，保费区间、健康匹配和保额均为辅助信息，最终以保险公司官方条款、健康告知和核保结果为准。

## 免责声明

**本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准。**

## License

MIT
