# 智能保险推荐引擎

基于 **规则树召回 + AI 精排** 双引擎的全栈保险推荐系统。不依赖任何商业保险 API，通过 Python 爬虫 + 大模型结构化解析构建产品数据库，为用户提供个性化保险方案推荐。

## 架构概览

```
用户问卷(七维画像) → 规则树粗筛(一票否决) → 6维评分算法 → 贪心套餐构建 → 双引擎路由
                                                                          ├─ 极速模式: 直接输出 (<1s)
                                                                          └─ AI 模式: LLM精排 + SSE流式推荐语
```

- **数据采集层**: Playwright 爬虫 + Instructor 大模型结构化提取
- **推荐引擎层**: 规则引擎（合规防线）+ AI 引擎（个性化精排）
- **网关防护层**: Redis 令牌桶限流 + 熔断降级

## 功能特性

- **七维用户画像**: 年龄、人生阶段、收入、职业风险、健康状态、家庭负担、已有保障
- **一票否决机制**: 年龄不符、职业超限、停售产品自动剔除；0-17 岁禁推寿险，55 岁以上替换防癌险
- **6 维产品评分**: 保障全面性(20%)、保费竞争力(18%)、投保宽松度(15%)、等待期(10%)、豁免条款(10%)、保额充足度(10%)、品牌信任度(10%)、增值服务(7%)
- **智能预算分配**: 按收入层级自动分配医疗/意外/重疾/寿险预算比例
- **三层套餐方案**: 极致性价比 / 全面保障 / 尊享无忧，贪心算法在预算约束下自动组合
- **双引擎路由**: 极速规则模式（<1s 响应）与 AI 专家模式（SSE 流式推荐语）
- **熔断降级**: LLM 异常时静默切换至极速模式，保证核心业务流程不中断
- **健康告知预警**: 异常项标红提示，引导智能核保
- **产品横向对比**: 高亮保费差异与保障差异，保费倒挂预警

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 后端 | FastAPI + SQLAlchemy + Pydantic + APScheduler |
| 爬虫 | Playwright + BeautifulSoup4 |
| AI | Instructor + OpenAI 兼容接口（支持 DeepSeek 等国产模型） |
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
│   │   │   ├── recommend.py        # POST /api/recommend (含 SSE 流式)
│   │   │   ├── products.py         # GET /api/products, /api/compare
│   │   │   └── admin.py            # 爬虫触发 & 健康检查
│   │   ├── engine/                 # 推荐引擎核心
│   │   │   ├── rule_engine.py      # 规则树粗筛（一票否决 → 候选池）
│   │   │   ├── scoring.py          # 8 维产品评分算法
│   │   │   ├── budget.py           # 预算分配 & 保额计算
│   │   │   ├── combo_builder.py    # 贪心套餐组合构建
│   │   │   ├── ai_engine.py        # LLM 精排 + SSE 流式
│   │   │   ├── fallback.py         # 熔断降级
│   │   │   └── models.py           # 引擎内部数据类
│   │   ├── crawler/                # Playwright 爬虫 + Instructor 结构化
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
│   │   ├── hooks/useSSE.ts         # SSE 流式读取 Hook
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

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/recommend` | 提交七维画像，返回套餐方案（支持 SSE 流式） |
| `GET` | `/api/products` | 产品列表（支持 `?type=` 筛选） |
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
- 保费 > 年收入 10% → 剔除

输出 10-20 款合法合规的「安全候选池」。

### 第二层：8 维评分算法

评分权重通过 `config/scoring_weights.yaml` 管理，支持按用户画像动态调整公司梯队偏好（高收入偏好品牌、健康异常偏好核保灵活、年轻用户偏好性价比）。

### 第三层：贪心套餐组合

候选池 → 险种匹配矩阵 → 预算约束贪心选取 → 3 套方案（性价比/全面/尊享），每套按基础层(医疗+意外) → 核心层(重疾+寿险) → 补充层(防癌/年金) 组织。

### 第四层：双引擎路由

- **极速模式** (`enable_llm_engine: false`): 规则树 → 评分 → 套餐组合 → 直接输出，1 秒内响应
- **AI 模式** (`enable_llm_engine: true`): 规则树 → 评分 → 套餐组合 → LLM 精选 3-4 款 + 200 字推荐语（SSE 流式打字机效果）
- **降级**: LLM 异常 → 静默切换极速模式，提示「AI 线路繁忙，已自动切换至极速专家推荐」

## 高可用设计

- **限流**: 10 次/分钟/IP，3 次/分钟/用户，50 次/天/用户（Redis 令牌桶），Redis 不可用时自动放行
- **超时**: LLM 连接 3s，读取 15-30s，前端总超时 35s
- **熔断降级**: LLM 异常静默切换极速模式，核心业务流程不中断

## 数据采集 Pipeline

```
Playwright 抓取 HTML → 提取纯文本 → Instructor + Pydantic 强制 JSON Mode → 入库
                                                                              ↓
                                                                     MD5 增量比对（周检）
                                                                              ↓
                                                                 变更触发重新解析 / 下架标记
```

## 免责声明

**本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准。**

## License

MIT
