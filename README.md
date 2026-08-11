# 智能保险推荐引擎

基于 **规则树召回 + AI 精排** 双引擎的全栈保险推荐系统。不依赖任何商业保险 API，通过 Python 爬虫 + 大模型结构化解析构建产品数据库，为用户提供个性化保险方案推荐。

## 架构概览

```
用户问卷(七维画像) → 规则树粗筛(一票否决) → 8维评分算法 → 贪心套餐构建 → 双引擎路由
                                                                          ├─ 极速模式: 直接输出 (<1s)
                                                                          └─ AI 模式: LLM解释规则引擎已选方案（同步 JSON）
```

- **数据采集层**: Playwright/BeautifulSoup 抓取 + OpenAI-compatible LLM 提取 + Pydantic 校验
- **推荐引擎层**: 规则引擎（合规筛选/评分/组包）+ AI 引擎（对已选方案做解释）
- **网关防护层**: Redis 令牌桶限流 + 熔断降级

## 功能特性

- **七维用户画像**: 年龄、人生阶段、收入、职业风险、健康状态、家庭负担、已有保障
- **一票否决机制**: 年龄不符、职业超限、停售产品自动剔除；0-17 岁禁推寿险，55 岁以上替换防癌险
- **8 维产品评分**: 保障全面性(20%)、保费竞争力(18%)、投保宽松度(15%)、等待期(10%)、豁免条款(10%)、保额充足度(10%)、品牌信任度(10%)、增值服务(7%)
- **智能预算分配**: 按收入层级自动分配医疗/意外/重疾/寿险预算比例
- **三层套餐方案**: 极致性价比 / 全面保障 / 尊享无忧，贪心算法在预算约束下自动组合
- **双引擎路由**: 极速规则模式与 AI 专家模式（同步 JSON 解释）；AI 不得新增或替换规则引擎选出的产品
- **熔断降级**: LLM 异常时静默切换至极速模式，保证核心业务流程不中断
- **健康告知预警**: 异常项标红提示，引导智能核保
- **产品横向对比**: 高亮保费差异与保障差异，保费倒挂预警

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
| `CORS_ALLOW_ORIGINS` | `http://localhost,http://localhost:3000,http://127.0.0.1:3000` | 逗号分隔的显式来源白名单（http/https，可含端口）；禁止带路径/查询串；`APP_ENV=production` 拒绝 `*`，且任何环境 `*` 都不能与 `allow_credentials=True`（Cookie 认证必需）并用 |

Cookie 登录用户计入用户级限流（限流优先解析 Bearer 头，其次解析 `access_token` Cookie）。详见 `docs/docker-deployment.md` 的“安全配置”章节。

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
- 55 岁以上 + 重疾险 → 替换为防癌险
- 报价下限超过对应险种预算 → 剔除
- 套餐组装同时检查已知报价上限；未披露上限的产品标记“起/以核保为准”，不被伪装成精确价格

输出 10-20 款合法合规的「安全候选池」。

### 第二层：8 维评分算法

评分权重通过 `config/scoring_weights.yaml` 管理，支持按用户画像动态调整公司梯队偏好（高收入偏好品牌、健康异常偏好核保灵活、年轻用户偏好性价比）。

### 第三层：贪心套餐组合

候选池 → 险种匹配矩阵 → 预算约束贪心选取 → 3 套方案（性价比/全面/尊享），每套按基础层(医疗+意外) → 核心层(重疾+寿险) → 补充层(防癌/年金) 组织。

### 第四层：双引擎路由

- **极速模式** (`enable_llm_engine: false`): 规则树 → 评分 → 套餐组合 → 直接输出，1 秒内响应
- **AI 模式** (`enable_llm_engine: true`): 规则树 → 评分 → 套餐组合 → LLM 对已选产品生成结构化解释；产品 ID 受输入白名单约束，不能新增/替换产品。当前接口为同步 JSON，不提供 SSE
- **降级**: LLM 异常 → 静默切换极速模式，提示「AI 线路繁忙，已自动切换至极速专家推荐」

## 高可用设计

- **限流**: 默认 120 次/分钟/IP、30 次/分钟/用户、300 次/天/用户（Redis 计数器）；Redis 不可用时当前实现放行并记录运行风险
- **超时**: LLM 连接默认 3s、读取默认 90s；实际值由 `LLM_CONNECT_TIMEOUT` / `LLM_READ_TIMEOUT` 配置
- **熔断降级**: LLM 异常静默切换极速模式，核心业务流程不中断

## 数据采集 Pipeline

```
配置的数据源页面 → SSRF/robots 校验 → 抓取 HTML/纯文本 → MD5 比对（内容未变化则跳过）
                                                        ↓
                         OpenAI-compatible LLM 提取 + Pydantic 白名单校验
                                                        ↓
                  `pending_review` → 管理员审核发布 Product/Rule/Benefit/Version
                                                        ↓
           识别停售/不可投保页面后生成下架审核任务；调度间隔由 `CRAWL_INTERVAL_MINUTES` 控制
```

采集结果不会直接进入推荐池；只有审核发布后的产品才可被推荐。开发环境首次启动会在空目录时补充种子目录，种子数据不代表实时市场报价。系统不提供实时核保或保险公司报价 API，保费区间、健康匹配和保额均为辅助信息，最终以保险公司官方条款、健康告知和核保结果为准。

## 免责声明

**本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准。**

## License

MIT
