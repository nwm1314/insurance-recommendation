# 智能保险推荐工具 — 设计规范（终审版）

**日期：** 2026-05-24
**状态：** 已确认（v2.0 技术经理终审通过）

---

## 1. 项目概述

不依赖商业保险 API，基于 Python 爬虫 + 大模型结构化 + 双引擎推荐，打造智能保险推荐系统。

---

## 2. 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 后端 | FastAPI + SQLAlchemy + Pydantic + APScheduler |
| 爬虫 | Playwright + BeautifulSoup |
| AI | OpenAI 兼容接口（国产模型）+ Instructor |
| 存储 | SQLite（开发期）+ Redis（Docker Compose） |
| 部署 | Docker Compose（后端 + Redis + 前端 Nginx） |

---

## 3. 项目结构

```
insurance_recommendation/
├── backend/
│   ├── app/
│   │   ├── api/              # API 路由
│   │   ├── engine/           # 推荐引擎
│   │   │   ├── rule_engine.py      # 规则树粗筛（一票否决 → 候选池）
│   │   │   ├── scoring.py         # 6维产品评分算法
│   │   │   ├── budget.py          # 预算分配策略 + 保额计算模型
│   │   │   ├── combo_builder.py   # 套餐组合构建（基础+核心+补充层）
│   │   │   ├── ai_engine.py       # LLM 精排（候选池 → Prompt → 推荐语）
│   │   │   ├── fallback.py        # 熔断降级
│   │   │   └── models.py          # 引擎内部数据类
│   │   ├── crawler/          # Playwright 爬虫 + LLM 结构化
│   │   ├── models/           # SQLAlchemy 模型
│   │   ├── schemas/          # Pydantic 校验
│   │   ├── services/         # 业务逻辑
│   │   ├── middleware/       # 限流、熔断、超时
│   │   ├── config.py         # 配置管理 + 评分权重
│   │   └── database.py       # 数据库连接
│   ├── config/               # 配置文件
│   │   ├── scoring_weights.yaml  # 评分权重
│   │   └── budget_rules.yaml     # 预算分配规则
│   ├── requirements.txt
│   ├── main.py               # FastAPI 入口
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/       # 可复用组件
│   │   │   ├── EngineSwitch.tsx       # AI/极速模式开关
│   │   │   ├── BudgetPreview.tsx      # 预算分配饼图预览
│   │   │   ├── ProgressSteps.tsx      # 步骤条
│   │   │   ├── ScoreRadar.tsx         # 6维评分雷达图
│   │   │   ├── ProductCard.tsx        # 产品卡片
│   │   │   ├── CompareTable.tsx       # 横向对比表格
│   │   │   ├── RiskBadge.tsx          # 健康/风险预警标签
│   │   │   └── Disclaimer.tsx         # 合规声明
│   │   ├── pages/
│   │   │   ├── HomePage.tsx           # 首页问卷
│   │   │   ├── ResultPage.tsx         # 推荐结果
│   │   │   └── AdminPage.tsx          # 管理后台
│   │   ├── hooks/            # 自定义 hooks（useSSE 等）
│   │   ├── api/              # API 调用封装
│   │   ├── types/            # TypeScript 类型
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
└── develop_guidence.md
```

---

## 4. 数据库 Schema（完整版）

### products（产品主表）— 14 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `name` | TEXT | 产品名称 |
| `company` | TEXT | 保险公司 |
| `type` | TEXT | 险种（重疾险/医疗险/意外险/定期寿险/防癌险/年金险） |
| `status` | INTEGER | 1 在售 / 0 停售 |
| `premium_min` | REAL | 最低年保费（元） |
| `premium_max` | REAL | 最高年保费（元） |
| `sum_insured_min` | REAL | 最低可投保额（万元） |
| `sum_insured_max` | REAL | 最高可投保额（万元） |
| `coverage_period` | TEXT | 保障期限（"终身"/"至70岁"/"30年"） |
| `payment_period` | TEXT | 缴费期限（"趸交"/"20年"/"30年"） |
| `source_url` | TEXT | 产品原始页面链接（官网/保险网站详情页） |
| `disease_count` | INTEGER | 重疾种类数 |
| `mild_disease_count` | INTEGER | 轻症种类数（可空） |
| `moderate_disease_count` | INTEGER | 中症种类数（可空） |
| `has_mild_coverage` | BOOL | 是否包含轻症 |
| `has_moderate_coverage` | BOOL | 是否包含中症 |
| `has_multi_claim` | BOOL | 是否多次赔付 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

### rules（投保规则表）— 9 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_id` | FK → products.id | 外键 |
| `min_age` | INTEGER | 最小投保年龄 |
| `max_age` | INTEGER | 最大投保年龄 |
| `job_class_limit` | INTEGER | 职业类别上限（1-6，6 为拒保类） |
| `waiting_period_days` | INTEGER | 等待期天数（30/90/180） |
| `has_insured_waiver` | BOOL | 是否包含被保人豁免 |
| `has_insurer_waiver` | BOOL | 是否包含投保人豁免 |
| `health_disclosure_count` | INTEGER | 健康告知条款数（评价投保宽松度） |
| `health_requirements` | JSON | 健康告知明细列表 |

### benefits（保障责任表）— 5 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_id` | FK → products.id | 外键 |
| `benefit_type` | TEXT | 分类（basic/optional/waiver/special） |
| `benefit_name` | TEXT | 责任名称 |
| `benefit_amount` | TEXT | 赔付金额描述 |
| `payment_limit` | TEXT | 赔付上限或次数限制 |

### page_logs（页面监控表）— 不变

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_id` | FK → products.id | 外键 |
| `page_url` | TEXT | 产品页面 URL |
| `page_md5_hash` | TEXT | 核心文本 MD5 指纹 |
| `last_checked` | DATETIME | 上次检查时间 |

---

## 5. 推荐引擎（完整版）

### 5.1 用户画像（七维模型）

| 维度 | 字段 | 分级 |
|------|------|------|
| 年龄 | `age` | 0-17 / 18-25 / 26-35 / 36-45 / 46-55 / 56+ |
| 人生阶段 | `life_stage` | single / married / married_with_kids / empty_nest / retired |
| 收入层级 | `annual_income` | <5万 / 5-15万 / 15-30万 / 30-50万 / 50万+ |
| 职业风险 | `job_class` | 1-2类(低) / 3-4类(中) / 5-6类(高) |
| 健康状态 | `health_status` | standard / substandard / history |
| 家庭负担 | `family_burden` | none / parents / children / dual |
| 已有保障 | `existing_coverage` | none / social / commercial |

### 5.2 第一层：规则树粗筛（纯 SQL，不可绕过）

**一票否决规则：**
- 年龄不在 [min_age, max_age] 范围 → 剔除
- 职业等级 > job_class_limit → 剔除
- status = 0（停售） → 剔除
- 0-17 岁 + 寿险 → 绝对不推
- 55 岁以上 + 重疾险 → 替换为防癌险（保费倒挂风险）

**预算控制：**
- 保费 > 年收入 10% → 剔除
- 保费 < 年收入 3% → 只推医疗 + 意外
- 预算 3-5% → 医疗 + 意外 + 定期重疾
- 预算 5-8% → 医疗 + 意外 + 终身重疾 + 定期寿险
- 预算 8-10% → 医疗 + 意外 + 终身重疾 + 长期寿险 + 补充险

**输出：** 10-20 款合法合规的"安全候选池"

### 5.3 第二层：保额计算模型

| 险种 | 计算公式 | 说明 |
|------|----------|------|
| 医疗险 | 固定 200-400 万 | 百万医疗标配 |
| 意外险 | 年收入 × 8-10 | 致残收入补偿 |
| 重疾险 | 年收入 × 3 + 30 万 | 3 年康复 + 30 万治疗基准，上限 100 万 |
| 定期寿险 | 年收入 × 5 + 负债（估算） | 保至 60/70 岁，不低于 50 万 |
| 防癌险 | 固定 10-20 万 | 老年专项 |

### 5.4 第三层：预算分配策略

| 年收入 | 总预算 | 医疗 | 意外 | 重疾 | 寿险 |
|--------|--------|------|------|------|------|
| < 5 万 | ≤5% | 30% | 30% | 30% | 10% |
| 5-15 万 | 5-8% | 15% | 15% | 45% | 25% |
| 15-30 万 | 6-9% | 10% | 10% | 50% | 30% |
| > 30 万 | 8-10% | 10% | 10% | 45% | 35% |

优先级：医疗险（打底） > 意外险（杠杆） > 重疾险（核心） > 定期寿险（责任）

### 5.5 第四层：6 维产品评分算法

| 评分维度 | 权重 | 计算方式 | 数据来源 |
|----------|------|----------|----------|
| 保障全面性 | 25% | 重疾种类数 + 轻/中症覆盖 + 多次赔付 + 责任条数 | products + benefits |
| 保费竞争力 | 25% | 同保额下保费在同类型产品中的 percentile 排名 | products.premium_min/max |
| 投保宽松度 | 20% | 健康告知条款数（少→高）+ 职业限制（宽→高） | rules |
| 等待期优势 | 10% | ≤90 天满分，180 天计 50% | rules.waiting_period_days |
| 豁免条款 | 10% | 含被保人豁免 +5，含投保人豁免 +5 | rules |
| 保额充足度 | 10% | 实际可投保额 / 建议保额 | products.sum_insured_max |

**综合得分 = Σ(维度得分 × 权重)**

权重从 `config/scoring_weights.yaml` 读取。

### 5.6 第五层：套餐组合构建

候选池 → 险种匹配矩阵 → 预算约束贪心选取 → 输出 3 套方案：

- 🛡 **极致性价比**（预算 < 5%）
- ⭐ **全面保障**（预算 5-8%）
- 👑 **尊享无忧**（预算 8-10%）

每套方案按三层结构组织：
- **基础层（必配）：** 医疗险 + 意外险
- **核心层（强烈建议）：** 重疾险 + 定期寿险
- **补充层（按需）：** 防癌险 / 年金险

套餐组合算法采用贪心逼近：在每个险种类别中选评分最高的产品，在预算约束下组合。

### 5.7 第六层：双引擎路由

- **极速模式** (enable_llm_engine=false)：规则树 → 评分 → 套餐组合 → 直接输出，1 秒内响应
- **AI 模式** (enable_llm_engine=true)：规则树 → 评分 → 套餐组合 → LLM 精选 3-4 款 + 200 字推荐语（SSE 流式）
- **降级**：LLM 异常 → 静默切换极速模式，提示"AI 线路繁忙，已自动切换至极速专家推荐"

### 5.8 险种匹配矩阵

| 年龄/阶段 | 医疗险 | 意外险 | 重疾险 | 定期寿险 | 防癌险 |
|-----------|--------|--------|--------|----------|--------|
| 0-17 岁 | ✓ | ✓ | ✓ | ✗ | ✗ |
| 18-25 单身 | ✓ | ✓ | ✓ | △ | ✗ |
| 26-35 有孩 | ✓ | ✓ | ✓ | ✓ | ✗ |
| 36-45 顶梁柱 | ✓ | ✓ | ✓ | ✓ | ✗ |
| 46-55 岁 | ✓ | ✓ | △ | △ | ✓ |
| 56+ 岁 | ✓ | ✓ | ✗ | ✗ | ✓ |

✓ = 必推   △ = 按预算可选   ✗ = 禁推

---

## 6. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/recommend` | 提交七维画像，返回套餐方案（SSE 流式支持） |
| GET | `/api/products` | 产品列表（支持 type/status 筛选） |
| GET | `/api/products/{id}` | 产品详情 + 保障责任明细 |
| POST | `/api/compare` | 多产品横向对比 |
| POST | `/api/admin/crawl` | 手动触发爬虫 |
| GET | `/api/admin/logs` | 爬虫/解析日志 |
| GET | `/api/health` | 健康检查 |

### POST /api/recommend 请求体

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
  "preferred_type": null,
  "enable_llm_engine": false
}
```

### POST /api/recommend 响应体

```json
{
  "user_profile": { "...回显..." },
  "budget_analysis": {
    "annual_income": 200000,
    "total_budget": 16000,
    "allocation": { "medical": 0.15, "accident": 0.15, "critical_illness": 0.45, "life": 0.25 }
  },
  "sum_insured_advice": {
    "medical": 3000000,
    "accident": 1600000,
    "critical_illness": 900000,
    "life": 1000000
  },
  "packages": [
    {
      "tag": "star",
      "tag_label": "⭐ 全面保障",
      "total_premium": 13800,
      "budget_ratio": 0.069,
      "products": [
        {
          "id": 1,
          "name": "XX百万医疗险",
          "type": "医疗险",
          "layer": "basic",
          "premium": 2400,
          "sum_insured": 3000000,
          "source_url": "https://www.example.com/product/123",
          "score": 87.5,
          "score_detail": {
            "coverage": 22.5, "price": 20.0, "flexibility": 16.0,
            "waiting": 10.0, "waiver": 10.0, "adequacy": 9.0
          }
        }
      ],
      "risk_warnings": [
        { "type": "health", "product_name": "XX重疾险", "message": "健康告知涉及结节，建议走智能核保" }
      ]
    }
  ],
  "llm_narrative": null,
  "engine_mode": "rule",
  "disclaimer": "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
}
```

---

## 7. 前端页面

### 首页问卷（4 步骤七维画像）

| 步骤 | 内容 | 交互组件 |
|------|------|----------|
| 1. 基本信息 | 年龄、性别、人生阶段、家庭负担 | InputNumber + Select + Radio.Group |
| 2. 职业与收入 | 年收入、职业类别、已有保障、预算占比 | InputNumber + Cascader + Checkbox + Slider（实时显示预算金额） |
| 3. 健康告知 | 健康状态 + 异常项勾选 | Radio + Checkbox（住院/结节/三高/其他） |
| 4. 偏好确认 | 引擎模式开关 + 预算分配预览 + 提交 | Switch + 简易饼图 + SubmitButton |

### 结果页

```
ResultPage
├── BudgetSummary（预算总览：年收入/总预算/占比/保额建议 + 分配饼图）
├── EngineStatusTag（极速/AI/降级模式标签）
├── PackageTabs（套餐切换：性价比/全面/尊享）
│   └── 每个Tab：
│       ├── ProductList（基础层→核心层→补充层）
│       │   └── ProductCard（产品名可点击跳转source_url+公司+保费+保额+ScoreRadar+RiskBadge）
│       └── AIRecommendText（SSE流式，仅AI模式）
├── CompareTable（横向对比，产品名可点击跳转详情页，高亮保费差异>20%/保障差异，保费倒挂预警行）
└── Disclaimer（合规声明）
```

### 管理页

- ProductTable（产品 CRUD）
- CrawlTrigger（触发爬虫按钮 + 状态显示）
- LogViewer（爬虫/解析日志列表）

---

## 8. 高可用防护

- **限流**：10 次/分钟/IP，3 次/分钟/用户，50 次/天/用户（Redis 令牌桶）
- **超时**：LLM 连接 3s，读取 15-30s，前端总超时 35s
- **熔断降级**：LLM 异常 → 静默切换极速模式，不抛错误

---

## 9. LLM 结构化解析流程

Playwright 抓取 HTML → 提取纯文本 → Instructor + Pydantic 强制 JSON Mode → 入库
异常时 retry 3 次 → 仍失败记入 error_log

---

## 10. 实施注意事项

- LLM 结构化提取新增字段依赖 Prompt 设计质量，需充分测试
- 评分算法权重通过 `config/scoring_weights.yaml` 管理，不硬编码
- 预算分配比例表存入 `config/budget_rules.yaml`
- 套餐组合算法是预算约束组合优化问题，先用贪心逼近
- 保费倒挂检测仅适用于长期险（重疾/寿险），短期险不适用
