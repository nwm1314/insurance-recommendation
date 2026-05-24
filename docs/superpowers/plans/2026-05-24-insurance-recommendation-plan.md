# 智能保险推荐工具 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零构建智能保险推荐全栈系统（React 前端 + FastAPI 后端 + 爬虫 + LLM + Redis）

**Architecture:** Monorepo 结构，backend/ 与 frontend/ 分离。后端 FastAPI 提供 REST API + SSE，前端 React+Ant Design SPA 通过 Vite 代理。Redis 做限流令牌桶，SQLite 存储数据，Playwright+Instructor 做爬虫和结构化。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, APScheduler, Playwright, Instructor, React 18, TypeScript, Ant Design 5, Vite, Redis, Docker Compose

**依赖顺序：** 项目脚手架 → 数据库模型 → 推荐引擎 → API 层 → 中间件 → 爬虫 → 前端基础 → 前端页面 → Docker 部署 → 种子数据

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `backend/main.py` | FastAPI 入口，注册路由/中间件/调度器 |
| `backend/app/config.py` | 环境变量 + 评分权重 + 预算规则加载 |
| `backend/app/database.py` | SQLite 连接 + Session 管理 |
| `backend/app/models/product.py` | products 表 ORM（13 字段） |
| `backend/app/models/rule.py` | rules 表 ORM（9 字段） |
| `backend/app/models/benefit.py` | benefits 表 ORM（5 字段） |
| `backend/app/models/page_log.py` | page_logs 表 ORM |
| `backend/app/engine/models.py` | 引擎内部 dataclass（UserProfile, ScoredProduct, ComboPackage） |
| `backend/app/engine/rule_engine.py` | 规则树粗筛（一票否决 → 候选池） |
| `backend/app/engine/scoring.py` | 6 维评分算法 |
| `backend/app/engine/budget.py` | 预算分配 + 保额计算 |
| `backend/app/engine/combo_builder.py` | 套餐组合构建（贪心） |
| `backend/app/engine/ai_engine.py` | LLM 精排 + SSE 流式 |
| `backend/app/engine/fallback.py` | 熔断降级 |
| `backend/app/schemas/user_profile.py` | 七维画像 Pydantic 模型 |
| `backend/app/schemas/recommendation.py` | 推荐响应 Pydantic 模型 |
| `backend/app/services/product_service.py` | 产品查询业务逻辑 |
| `backend/app/api/recommend.py` | POST /api/recommend（含 SSE） |
| `backend/app/api/products.py` | GET /api/products, /api/products/{id}, POST /api/compare |
| `backend/app/api/admin.py` | POST /api/admin/crawl, GET /api/admin/logs |
| `backend/app/middleware/rate_limiter.py` | Redis 令牌桶限流 |
| `backend/app/crawler/scraper.py` | Playwright 页面抓取 |
| `backend/app/crawler/llm_extractor.py` | Instructor + Pydantic 结构化提取 |
| `backend/app/crawler/scheduler.py` | APScheduler 定时巡检 |
| `backend/config/scoring_weights.yaml` | 评分权重配置 |
| `backend/config/budget_rules.yaml` | 预算分配规则 |
| `frontend/src/types/index.ts` | TypeScript 类型定义 |
| `frontend/src/api/client.ts` | Axios 实例 + 请求拦截 |
| `frontend/src/api/recommend.ts` | 推荐 API + SSE 调用 |
| `frontend/src/api/products.ts` | 产品 API 调用 |
| `frontend/src/hooks/useSSE.ts` | SSE 流式读取 Hook |
| `frontend/src/components/ProgressSteps.tsx` | 步骤条 |
| `frontend/src/components/EngineSwitch.tsx` | AI/极速模式开关 |
| `frontend/src/components/BudgetPreview.tsx` | 预算分配饼图 |
| `frontend/src/components/ScoreRadar.tsx` | 6 维评分雷达图 |
| `frontend/src/components/ProductCard.tsx` | 产品卡片 |
| `frontend/src/components/CompareTable.tsx` | 横向对比表格 |
| `frontend/src/components/RiskBadge.tsx` | 健康/风险预警标签 |
| `frontend/src/components/Disclaimer.tsx` | 合规声明 |
| `frontend/src/pages/HomePage.tsx` | 4 步骤问卷页 |
| `frontend/src/pages/ResultPage.tsx` | 推荐结果页 |
| `frontend/src/pages/AdminPage.tsx` | 管理后台页 |
| `frontend/src/App.tsx` | 路由 + 布局 |
| `docker-compose.yml` | Redis + 后端 + 前端 Nginx |

---

### Task 1: 项目脚手架 + 根目录文件

**Files:**
- Create: `backend/requirements.txt`, `backend/Dockerfile`
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: 创建所有目录结构**

```bash
mkdir -p backend/app/{api,engine,crawler,models,schemas,services,middleware}
mkdir -p backend/config
mkdir -p frontend/src/{components,pages,hooks,api,types}
```

- [ ] **Step 2: 创建 backend/requirements.txt**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pydantic==2.10.3
pydantic-settings==2.7.0
apscheduler==3.11.0
playwright==1.49.1
beautifulsoup4==4.12.3
instructor==1.7.0
openai==1.58.1
redis==5.2.1
httpx==0.28.1
pyyaml==6.5
python-dotenv==1.0.1
```

- [ ] **Step 3: 创建 backend/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: 创建 frontend/package.json**

```json
{
  "name": "insurance-recommendation-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "antd": "^5.22.0",
    "@ant-design/icons": "^5.5.0",
    "@ant-design/charts": "^2.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "axios": "^1.7.9"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "~5.6.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 5: 创建 frontend/vite.config.ts**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 6: 创建 frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 7: 创建 frontend/tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 8: 创建 frontend/index.html**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>智能保险推荐</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 9: 创建 frontend/Dockerfile**

```dockerfile
FROM node:22-alpine as build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 10: 创建 docker-compose.yml**

```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/insurance.db
      - REDIS_URL=redis://redis:6379
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL:-https://api.openai.com/v1}
      - LLM_MODEL=${LLM_MODEL:-gpt-4o-mini}
    volumes:
      - ./backend/data:/app/data
      - ./backend/config:/app/config
    depends_on:
      - redis
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
```

- [ ] **Step 11: 安装前端依赖并验证**

```bash
cd frontend && npm install
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "chore: project scaffolding with backend, frontend, docker-compose"
```

---

### Task 2: 后端配置 + 数据库初始化

**Files:**
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/database.py`

- [ ] **Step 1: 创建 backend/app/__init__.py（空文件）**

```bash
touch backend/app/__init__.py
```

- [ ] **Step 2: 创建 backend/app/config.py**

```python
import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_yaml(filename: str) -> dict:
    path = BASE_DIR / "config" / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/insurance.db"
    redis_url: str = "redis://localhost:6379"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_retries: int = 3
    llm_connect_timeout: float = 3.0
    llm_read_timeout: float = 30.0

    rate_limit_ip_per_minute: int = 10
    rate_limit_user_per_minute: int = 3
    rate_limit_user_per_day: int = 50

    class Config:
        env_file = ".env"


settings = Settings()

# 从 YAML 加载可调参数
SCORING_WEIGHTS = _load_yaml("scoring_weights.yaml")
BUDGET_RULES = _load_yaml("budget_rules.yaml")
```

- [ ] **Step 3: 创建 backend/app/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.app.models.product import Product  # noqa
    from backend.app.models.rule import Rule  # noqa
    from backend.app.models.benefit import Benefit  # noqa
    from backend.app.models.page_log import PageLog  # noqa
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/__init__.py backend/app/config.py backend/app/database.py
git commit -m "feat: add backend config and database initialization"
```

---

### Task 3: SQLAlchemy 数据模型（4 张表）

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/product.py`, `backend/app/models/rule.py`, `backend/app/models/benefit.py`, `backend/app/models/page_log.py`

- [ ] **Step 1: 创建 backend/app/models/__init__.py（空文件）**

```bash
touch backend/app/models/__init__.py
```

- [ ] **Step 2: 创建 backend/app/models/product.py**

```python
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=1)

    premium_min: Mapped[float] = mapped_column(Float, nullable=True)
    premium_max: Mapped[float] = mapped_column(Float, nullable=True)
    sum_insured_min: Mapped[float] = mapped_column(Float, nullable=True)
    sum_insured_max: Mapped[float] = mapped_column(Float, nullable=True)
    coverage_period: Mapped[str] = mapped_column(String(50), nullable=True)
    payment_period: Mapped[str] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=True)

    disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    mild_disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    moderate_disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    has_mild_coverage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_moderate_coverage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_multi_claim: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    rules = relationship("Rule", back_populates="product", uselist=False)
    benefits = relationship("Benefit", back_populates="product")
```

- [ ] **Step 3: 创建 backend/app/models/rule.py**

```python
from sqlalchemy import String, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), unique=True, nullable=False)

    min_age: Mapped[int] = mapped_column(Integer, default=0)
    max_age: Mapped[int] = mapped_column(Integer, default=100)
    job_class_limit: Mapped[int] = mapped_column(Integer, default=6)

    waiting_period_days: Mapped[int] = mapped_column(Integer, default=90)
    has_insured_waiver: Mapped[bool] = mapped_column(Boolean, default=False)
    has_insurer_waiver: Mapped[bool] = mapped_column(Boolean, default=False)
    health_disclosure_count: Mapped[int] = mapped_column(Integer, default=0)
    health_requirements: Mapped[dict] = mapped_column(JSON, default=list)

    product = relationship("Product", back_populates="rules")
```

- [ ] **Step 4: 创建 backend/app/models/benefit.py**

```python
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Benefit(Base):
    __tablename__ = "benefits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)

    benefit_type: Mapped[str] = mapped_column(String(50), default="basic")
    benefit_name: Mapped[str] = mapped_column(String(200), nullable=False)
    benefit_amount: Mapped[str] = mapped_column(String(200), nullable=True)
    payment_limit: Mapped[str] = mapped_column(String(200), nullable=True)
    desc: Mapped[str] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="benefits")
```

- [ ] **Step 5: 创建 backend/app/models/page_log.py**

```python
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.database import Base


class PageLog(Base):
    __tablename__ = "page_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    page_md5_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    last_checked: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 6: 验证模型可导入**

```bash
cd backend && python -c "from app.database import init_db; init_db(); print('OK')"
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add SQLAlchemy models (products, rules, benefits, page_logs)"
```

---

### Task 4: 推荐引擎 — 内部数据模型 + 配置文件

**Files:**
- Create: `backend/app/engine/__init__.py`, `backend/app/engine/models.py`
- Create: `backend/config/scoring_weights.yaml`, `backend/config/budget_rules.yaml`

- [ ] **Step 1: 创建 backend/app/engine/__init__.py（空文件）**

```bash
touch backend/app/engine/__init__.py
```

- [ ] **Step 2: 创建 backend/app/engine/models.py**

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserProfile:
    age: int
    gender: str
    annual_income: float
    job_class: int
    life_stage: str          # single / married / married_with_kids / empty_nest / retired
    family_burden: str       # none / parents / children / dual
    health_status: str        # standard / substandard / history
    health_issues: list[str] = field(default_factory=list)
    existing_coverage: list[str] = field(default_factory=list)
    budget_ratio: float = 0.08
    preferred_type: Optional[str] = None
    enable_llm_engine: bool = False


@dataclass
class ScoredProduct:
    product_id: int
    name: str
    company: str
    type: str
    premium: float
    sum_insured: float
    source_url: str = ""
    layer: str = "core"        # basic / core / supplement
    score: float = 0.0
    score_detail: dict[str, float] = field(default_factory=dict)
    risk_warnings: list[dict] = field(default_factory=list)


@dataclass
class ComboPackage:
    tag: str                   # budget / star / premium
    tag_label: str
    total_premium: float
    budget_ratio: float
    products: list[ScoredProduct] = field(default_factory=list)


@dataclass
class BudgetAnalysis:
    annual_income: float
    total_budget: float
    allocation: dict[str, float] = field(default_factory=dict)


@dataclass
class SumInsuredAdvice:
    medical: float
    accident: float
    critical_illness: float
    life: float
    cancer: float = 100000


@dataclass
class RecommendationResult:
    user_profile: dict
    budget_analysis: BudgetAnalysis
    sum_insured_advice: SumInsuredAdvice
    packages: list[ComboPackage] = field(default_factory=list)
    llm_narrative: Optional[str] = None
    engine_mode: str = "rule"
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
```

- [ ] **Step 3: 创建 backend/config/scoring_weights.yaml**

```yaml
weights:
  coverage: 0.25       # 保障全面性
  price: 0.25          # 保费竞争力
  flexibility: 0.20    # 投保宽松度
  waiting: 0.10        # 等待期优势
  waiver: 0.10         # 豁免条款
  adequacy: 0.10       # 保额充足度

scoring:
  waiting_period_best: 90     # 等待期满分阈值（天）
  waiting_period_worst: 180   # 等待期最低分阈值（天）
  health_disclosure_best: 3   # 健康告知最少条数（满分）
  health_disclosure_worst: 15 # 健康告知最多条数（最低分）
  job_class_best: 6           # 职业限制最宽松
```

- [ ] **Step 4: 创建 backend/config/budget_rules.yaml**

```yaml
income_tiers:
  - max_income: 50000
    budget_ratio: 0.05
    allocation:
      medical: 0.30
      accident: 0.30
      critical_illness: 0.30
      life: 0.10
  - max_income: 150000
    budget_ratio: 0.08
    allocation:
      medical: 0.15
      accident: 0.15
      critical_illness: 0.45
      life: 0.25
  - max_income: 300000
    budget_ratio: 0.09
    allocation:
      medical: 0.10
      accident: 0.10
      critical_illness: 0.50
      life: 0.30
  - max_income: 999999999
    budget_ratio: 0.10
    allocation:
      medical: 0.10
      accident: 0.10
      critical_illness: 0.45
      life: 0.35

budget_tiers:
  - max_ratio: 0.03
    types: [医疗险, 意外险]
  - max_ratio: 0.05
    types: [医疗险, 意外险, 重疾险]
  - max_ratio: 0.08
    types: [医疗险, 意外险, 重疾险, 定期寿险]
  - max_ratio: 0.10
    types: [医疗险, 意外险, 重疾险, 定期寿险, 防癌险]

sum_insured:
  medical: 3000000
  accident_multiplier: 8
  critical_illness_multiplier: 3
  critical_illness_base: 300000
  critical_illness_max: 1000000
  life_multiplier: 5
  life_min: 500000
  cancer_default: 150000
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/__init__.py backend/app/engine/models.py backend/config/
git commit -m "feat: add engine internal models and config files"
```

---

### Task 5: 推荐引擎 — 规则树粗筛

**Files:**
- Create: `backend/app/engine/rule_engine.py`

- [ ] **Step 1: 创建 backend/app/engine/rule_engine.py**

```python
from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.engine.models import UserProfile

# 险种匹配矩阵：{age_group: {insurance_type: rule}}
TYPE_MATRIX = {
    "0-17":    {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "forbidden", "防癌险": "forbidden"},
    "18-25":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "optional", "防癌险": "forbidden"},
    "26-35":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "36-45":   {"医疗险": "required", "意外险": "required", "重疾险": "required", "定期寿险": "required", "防癌险": "forbidden"},
    "46-55":   {"医疗险": "required", "意外险": "required", "重疾险": "optional", "定期寿险": "optional", "防癌险": "required"},
    "56+":     {"医疗险": "required", "意外险": "required", "重疾险": "forbidden", "定期寿险": "forbidden", "防癌险": "required"},
}


def _get_age_group(age: int) -> str:
    if age <= 17: return "0-17"
    if age <= 25: return "18-25"
    if age <= 35: return "26-35"
    if age <= 45: return "36-45"
    if age <= 55: return "46-55"
    return "56+"


def get_allowed_types(user: UserProfile) -> set[str]:
    """返回用户可投保的险种类别集合"""
    budget_tier = _get_budget_tier(user.budget_ratio)
    age_group = _get_age_group(user.age)
    allowed = set()
    for ins_type, rule in TYPE_MATRIX.get(age_group, {}).items():
        if rule == "forbidden":
            continue
        if rule in ("required", "optional") and ins_type in budget_tier:
            allowed.add(ins_type)
    return allowed


def _get_budget_tier(ratio: float) -> set[str]:
    if ratio <= 0.03:
        return {"医疗险", "意外险"}
    if ratio <= 0.05:
        return {"医疗险", "意外险", "重疾险"}
    if ratio <= 0.08:
        return {"医疗险", "意外险", "重疾险", "定期寿险"}
    return {"医疗险", "意外险", "重疾险", "定期寿险", "防癌险"}


def filter_candidate_pool(db: Session, user: UserProfile) -> list[Product]:
    """规则树粗筛：一票否决 → 安全候选池"""
    allowed_types = get_allowed_types(user)

    query = (
        db.query(Product)
        .join(Rule, Product.id == Rule.product_id)
        .filter(Product.status == 1)
        .filter(Product.type.in_(allowed_types))
        .filter(Rule.min_age <= user.age)
        .filter(Rule.max_age >= user.age)
        .filter(Rule.job_class_limit >= user.job_class)
    )

    if user.annual_income > 0:
        max_premium = user.annual_income * user.budget_ratio
        if max_premium > 0:
            query = query.filter(Product.premium_max <= max_premium)

    return query.all()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/engine/rule_engine.py
git commit -m "feat: add rule engine with veto filter and age-type matrix"
```

---

### Task 6: 推荐引擎 — 6 维评分算法

**Files:**
- Create: `backend/app/engine/scoring.py`

- [ ] **Step 1: 创建 backend/app/engine/scoring.py**

```python
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit
from backend.app.config import SCORING_WEIGHTS

WEIGHTS = SCORING_WEIGHTS.get("weights", {})
SCORING = SCORING_WEIGHTS.get("scoring", {})


def score_product(product: Product, rule: Rule, benefits: list[Benefit], suggested_sum_insured: float) -> dict:
    """对单个产品进行 6 维评分，返回总分 + 明细"""

    # 保障全面性 (25%)
    coverage = _score_coverage(product, benefits)

    # 保费竞争力 (25%)
    price = WEIGHTS.get("price", 0.25) * 100  # 默认满分，实际在候选池内做 percentile

    # 投保宽松度 (20%)
    flexibility = _score_flexibility(rule)

    # 等待期优势 (10%)
    waiting = _score_waiting(rule)

    # 豁免条款 (10%)
    waiver = _score_waiver(rule)

    # 保额充足度 (10%)
    adequacy = _score_adequacy(product, suggested_sum_insured)

    detail = {
        "coverage": coverage,
        "price": price,
        "flexibility": flexibility,
        "waiting": waiting,
        "adequacy": adequacy,
        "waiver": waiver,
    }
    total = sum(detail.values())
    detail["total"] = total
    return detail


def _score_coverage(product: Product, benefits: list[Benefit]) -> float:
    w = WEIGHTS.get("coverage", 0.25)
    score = 0.0
    max_score = 100.0

    # 重疾种类数（80-180种 → 0-50分）
    if product.disease_count:
        disease_score = min(50, (product.disease_count - 80) / 100 * 50)
        score += max(0, disease_score)

    # 含轻症 +10，含中症 +10
    if product.has_mild_coverage:
        score += 10
    if product.has_moderate_coverage:
        score += 10

    # 多次赔付 +15
    if product.has_multi_claim:
        score += 15

    # 责任条数（benefits 越多越好，但上限 15）
    benefit_count = len([b for b in benefits if b.benefit_type == "basic"])
    score += min(15, benefit_count * 1.5)

    return round((score / max_score) * w * 100, 1)


def _score_flexibility(rule: Rule) -> float:
    w = WEIGHTS.get("flexibility", 0.20)
    best = SCORING.get("health_disclosure_best", 3)
    worst = SCORING.get("health_disclosure_worst", 15)
    job_best = SCORING.get("job_class_best", 6)

    # 健康告知宽松度（条款越少越宽松，0-50分）
    health_count = rule.health_disclosure_count or 0
    if health_count <= best:
        health_score = 50
    elif health_count >= worst:
        health_score = 0
    else:
        health_score = 50 * (1 - (health_count - best) / (worst - best))

    # 职业限制宽松度（等级越高越宽松，0-50分）
    job_score = 50 * (rule.job_class_limit / job_best)

    return round(((health_score + job_score) / 100) * w * 100, 1)


def _score_waiting(rule: Rule) -> float:
    w = WEIGHTS.get("waiting", 0.10)
    best = SCORING.get("waiting_period_best", 90)
    worst = SCORING.get("waiting_period_worst", 180)

    days = rule.waiting_period_days or 90
    if days <= best:
        return round(w * 100, 1)
    if days >= worst:
        return round(w * 50, 1)
    return round(w * (100 - 50 * (days - best) / (worst - best)), 1)


def _score_waiver(rule: Rule) -> float:
    w = WEIGHTS.get("waiver", 0.10)
    score = 0
    if rule.has_insured_waiver:
        score += 50
    if rule.has_insurer_waiver:
        score += 50
    return round((score / 100) * w * 100, 1)


def _score_adequacy(product: Product, suggested: float) -> float:
    w = WEIGHTS.get("adequacy", 0.10)
    if not suggested or not product.sum_insured_max:
        return round(w * 80, 1)
    ratio = min(product.sum_insured_max / suggested, 1.5)
    score = min(100, ratio * 100)
    return round((score / 100) * w * 100, 1)


def apply_price_scoring(scored_products: list[dict]) -> list[dict]:
    """对候选池内产品计算保费竞争力 percentile 排名"""
    if not scored_products:
        return scored_products
    premiums = [p.get("premium", 0) for p in scored_products]
    min_p, max_p = min(premiums), max(premiums)
    w = WEIGHTS.get("price", 0.25)
    for p in scored_products:
        premium = p.get("premium", 0)
        if max_p > min_p:
            percentile = 1 - (premium - min_p) / (max_p - min_p)
        else:
            percentile = 1.0
        price_score = round(percentile * w * 100, 1)
        p["score_detail"]["price"] = price_score
        p["score_detail"]["total"] = sum(p["score_detail"].values()) - p["score_detail"]["total"] + price_score
        p["score"] = p["score_detail"]["total"]
    return scored_products
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/engine/scoring.py
git commit -m "feat: add 6-dimension product scoring algorithm"
```

---

### Task 7: 推荐引擎 — 预算分配 + 保额计算

**Files:**
- Create: `backend/app/engine/budget.py`

- [ ] **Step 1: 创建 backend/app/engine/budget.py**

```python
from backend.app.engine.models import UserProfile, BudgetAnalysis, SumInsuredAdvice
from backend.app.config import BUDGET_RULES


def calculate_budget(user: UserProfile) -> BudgetAnalysis:
    """根据收入层级计算总预算和险种分配比例"""
    income = user.annual_income
    tiers = BUDGET_RULES.get("income_tiers", [])
    for tier in tiers:
        if income <= tier["max_income"]:
            total_budget = income * user.budget_ratio
            return BudgetAnalysis(
                annual_income=income,
                total_budget=round(total_budget, 2),
                allocation=tier["allocation"],
            )
    # fallback
    return BudgetAnalysis(
        annual_income=income,
        total_budget=round(income * 0.08, 2),
        allocation={"medical": 0.15, "accident": 0.15, "critical_illness": 0.45, "life": 0.25},
    )


def calculate_sum_insured(user: UserProfile) -> SumInsuredAdvice:
    """根据用户画像计算各险种建议保额"""
    income = user.annual_income
    config = BUDGET_RULES.get("sum_insured", {})
    is_breadwinner = user.life_stage in ("married_with_kids", "married") and user.family_burden in ("children", "dual")
    life_mult = config.get("life_multiplier", 5)

    medical = config.get("medical", 3000000)
    accident = income * config.get("accident_multiplier", 8)
    ci = min(
        income * config.get("critical_illness_multiplier", 3) + config.get("critical_illness_base", 300000),
        config.get("critical_illness_max", 1000000),
    )
    life = max(income * life_mult, config.get("life_min", 500000))
    if is_breadwinner:
        life *= 2

    return SumInsuredAdvice(
        medical=round(medical),
        accident=round(accident),
        critical_illness=round(ci),
        life=round(life),
        cancer=config.get("cancer_default", 150000),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/engine/budget.py
git commit -m "feat: add budget allocation and sum insured calculation"
```

---

### Task 8: 推荐引擎 — 套餐组合构建

**Files:**
- Create: `backend/app/engine/combo_builder.py`

- [ ] **Step 1: 创建 backend/app/engine/combo_builder.py**

```python
from backend.app.engine.models import UserProfile, ScoredProduct, ComboPackage, BudgetAnalysis
from backend.app.engine.rule_engine import get_allowed_types


def build_combos(
    scored_products: list[dict],
    user: UserProfile,
    budget: BudgetAnalysis,
) -> list[ComboPackage]:
    """贪心算法构建 3 套方案"""
    allowed_types = get_allowed_types(user)
    products_by_type: dict[str, list[dict]] = {}
    for p in scored_products:
        ptype = p.get("type", "")
        if ptype not in products_by_type:
            products_by_type[ptype] = []
        products_by_type[ptype].append(p)
    for plist in products_by_type.values():
        plist.sort(key=lambda x: x.get("score", 0), reverse=True)

    combos = []

    # 方案1: 极致性价比
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "budget", "🛡 极致性价比", user))

    # 方案2: 全面保障
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "star", "⭐ 全面保障", user))

    # 方案3: 尊享无忧
    combos.append(_build_single_combo(products_by_type, allowed_types, budget, "premium", "👑 尊享无忧", user))

    return [c for c in combos if c.products]


def _build_single_combo(
    products_by_type: dict[str, list[dict]],
    allowed_types: set[str],
    budget: BudgetAnalysis,
    tag: str,
    label: str,
    user: UserProfile,
) -> ComboPackage:
    """贪心选取：每个险种选最高分产品，在预算约束下组合"""
    budget_mult = {"budget": 0.5, "star": 0.8, "premium": 1.0}
    max_spend = budget.total_budget * budget_mult.get(tag, 0.8)

    scored_list: list[ScoredProduct] = []
    layer_map = {
        "医疗险": "basic", "意外险": "basic",
        "重疾险": "core", "定期寿险": "core",
        "防癌险": "supplement", "年金险": "supplement",
    }

    total = 0.0
    type_order = ["医疗险", "意外险", "重疾险", "定期寿险", "防癌险"]

    for ins_type in type_order:
        if ins_type not in allowed_types:
            continue
        candidates = products_by_type.get(ins_type, [])
        if not candidates:
            continue
        best = candidates[0]
        premium = best.get("premium", 0) or 0
        if total + premium > max_spend:
            continue
        total += premium
        scored_list.append(ScoredProduct(
            product_id=best.get("product_id", 0),
            name=best.get("name", ""),
            company=best.get("company", ""),
            type=ins_type,
            premium=premium,
            sum_insured=best.get("sum_insured", 0),
            source_url=best.get("source_url", ""),
            layer=layer_map.get(ins_type, "core"),
            score=best.get("score", 0),
            score_detail=best.get("score_detail", {}),
            risk_warnings=best.get("risk_warnings", []),
        ))

    ratio = total / budget.annual_income if budget.annual_income > 0 else 0
    return ComboPackage(
        tag=tag,
        tag_label=label,
        total_premium=round(total, 2),
        budget_ratio=round(ratio, 4),
        products=scored_list,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/engine/combo_builder.py
git commit -m "feat: add combo builder with greedy package construction"
```

---

### Task 9: 推荐引擎 — AI 精排 + 降级

**Files:**
- Create: `backend/app/engine/ai_engine.py`, `backend/app/engine/fallback.py`

- [ ] **Step 1: 创建 backend/app/engine/ai_engine.py**

```python
from typing import AsyncGenerator
from openai import AsyncOpenAI
from backend.app.config import settings
from backend.app.engine.models import UserProfile, ScoredProduct

SYSTEM_PROMPT = """你是一位资深保险精算师和家庭财务规划顾问。根据以下候选保险产品池和用户画像，挑选最适合用户的 3-4 款产品组合，并撰写约 200 字的个性化推荐理由。

要求：
1. 推荐语要有人情味，体现对用户家庭情况的关怀
2. 说明为什么选这几款产品（从保障全面性、性价比、投保宽松度角度）
3. 若有健康异常，友好提醒核保注意事项
4. 必须只推荐候选池中存在的产品
5. 严格按 JSON 格式输出"""


async def ai_rerank(
    user: UserProfile,
    scored_products: list[ScoredProduct],
) -> AsyncGenerator[str, None]:
    """LLM 精排，SSE 流式输出推荐语"""
    products_text = "\n".join([
        f"- {p.name}（{p.type}）：保费 ¥{p.premium}/年，保额 {p.sum_insured} 万，评分 {p.score}，公司 {p.company}"
        for p in scored_products
    ])
    user_text = f"""
用户画像：
- 年龄：{user.age} 岁，性别：{user.gender}
- 年收入：{user.annual_income} 元
- 人生阶段：{user.life_stage}，家庭负担：{user.family_burden}
- 健康状况：{user.health_status}，异常项：{', '.join(user.health_issues) if user.health_issues else '无'}
"""

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_read_timeout,
    )

    try:
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text + "\n候选产品池：\n" + products_text},
            ],
            stream=True,
            response_format={"type": "json_object"},
            timeout=settings.llm_read_timeout,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        yield f'{{"error": "{str(e)}"}}'


async def ai_rerank_or_fallback(
    user: UserProfile,
    scored_products: list[ScoredProduct],
) -> tuple[AsyncGenerator[str, None] | None, str]:
    """包装 AI 调用，异常时返回 None 触发降级"""
    try:
        gen = ai_rerank(user, scored_products)
        return gen, "ai"
    except Exception:
        return None, "degraded"
```

- [ ] **Step 2: 创建 backend/app/engine/fallback.py**

```python
from backend.app.engine.models import ScoredProduct


FALLBACK_MESSAGE = "AI 线路繁忙，已自动切换至极速专家推荐"


def get_fallback_narrative(products: list[ScoredProduct]) -> str:
    """降级时生成规则推荐语"""
    if not products:
        return "暂未找到完全匹配的产品方案，请调整筛选条件后重试。"
    names = "、".join([p.name for p in products[:3]])
    return f"{FALLBACK_MESSAGE}。为您推荐：{names}，该方案基于您的画像通过精算规则筛选，确保合规与性价比。"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/engine/ai_engine.py backend/app/engine/fallback.py
git commit -m "feat: add AI reranking engine with SSE and graceful degradation"
```

---

### Task 10: Pydantic Schema + 业务服务

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/user_profile.py`, `backend/app/schemas/recommendation.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/product_service.py`

- [ ] **Step 1: 创建 backend/app/schemas/__init__.py 和 backend/app/services/__init__.py**

```bash
touch backend/app/schemas/__init__.py backend/app/services/__init__.py
```

- [ ] **Step 2: 创建 backend/app/schemas/user_profile.py**

```python
from typing import Optional
from pydantic import BaseModel, Field


class UserProfileRequest(BaseModel):
    age: int = Field(..., ge=0, le=120, description="年龄")
    gender: str = Field(..., pattern="^(male|female)$", description="性别")
    annual_income: float = Field(..., gt=0, description="年收入（元）")
    job_class: int = Field(..., ge=1, le=6, description="职业风险等级 1-6")
    life_stage: str = Field(..., description="人生阶段")
    family_burden: str = Field(default="none", description="家庭负担")
    health_status: str = Field(default="standard", description="健康状态")
    health_issues: list[str] = Field(default_factory=list, description="健康异常项")
    existing_coverage: list[str] = Field(default_factory=list, description="已有保障")
    budget_ratio: float = Field(default=0.08, ge=0.03, le=0.10, description="预算占比")
    preferred_type: Optional[str] = Field(default=None, description="指定险种偏好")
    enable_llm_engine: bool = Field(default=False, description="是否启用 AI 模式")
```

- [ ] **Step 3: 创建 backend/app/schemas/recommendation.py**

```python
from typing import Optional
from pydantic import BaseModel


class ScoreDetail(BaseModel):
    coverage: float = 0
    price: float = 0
    flexibility: float = 0
    waiting: float = 0
    adequacy: float = 0
    waiver: float = 0


class ProductItem(BaseModel):
    id: int
    name: str
    company: str
    type: str
    layer: str = "core"
    premium: float
    sum_insured: float
    source_url: str = ""
    score: float
    score_detail: ScoreDetail
    risk_warnings: list[dict] = []


class Allocation(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float


class BudgetAnalysisResponse(BaseModel):
    annual_income: float
    total_budget: float
    allocation: Allocation


class SumInsuredAdviceResponse(BaseModel):
    medical: float
    accident: float
    critical_illness: float
    life: float


class ComboPackageResponse(BaseModel):
    tag: str
    tag_label: str
    total_premium: float
    budget_ratio: float
    products: list[ProductItem]


class RecommendationResponse(BaseModel):
    user_profile: dict
    budget_analysis: BudgetAnalysisResponse
    sum_insured_advice: SumInsuredAdviceResponse
    packages: list[ComboPackageResponse] = []
    llm_narrative: Optional[str] = None
    engine_mode: str = "rule"
    disclaimer: str = "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准"
```

- [ ] **Step 4: 创建 backend/app/services/product_service.py**

```python
from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit


def get_product_with_details(db: Session, product_id: int) -> dict | None:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None
    rule = db.query(Rule).filter(Rule.product_id == product_id).first()
    benefits = db.query(Benefit).filter(Benefit.product_id == product_id).all()
    return {
        "product": product,
        "rule": rule,
        "benefits": benefits,
    }


def list_products(db: Session, product_type: str | None = None, status: int = 1) -> list[Product]:
    query = db.query(Product).filter(Product.status == status)
    if product_type:
        query = query.filter(Product.type == product_type)
    return query.all()


def compare_products(db: Session, product_ids: list[int]) -> list[dict]:
    results = []
    for pid in product_ids:
        detail = get_product_with_details(db, pid)
        if detail:
            results.append(detail)
    return results
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/ backend/app/services/
git commit -m "feat: add Pydantic schemas and product service"
```

---

### Task 11: API 路由 — 产品 + 管理 + 健康检查

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/products.py`, `backend/app/api/admin.py`

- [ ] **Step 1: 创建 backend/app/api/__init__.py（空文件）**

```bash
touch backend/app/api/__init__.py
```

- [ ] **Step 2: 创建 backend/app/api/products.py**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.services.product_service import list_products, get_product_with_details, compare_products

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products")
def api_list_products(
    type: str | None = Query(None, alias="type"),
    db: Session = Depends(get_db),
):
    products = list_products(db, product_type=type)
    return {
        "products": [
            {
                "id": p.id, "name": p.name, "company": p.company,
                "type": p.type, "status": p.status,
                "premium_min": p.premium_min, "premium_max": p.premium_max,
                "sum_insured_max": p.sum_insured_max,
            }
            for p in products
        ]
    }


@router.get("/products/{product_id}")
def api_product_detail(product_id: int, db: Session = Depends(get_db)):
    detail = get_product_with_details(db, product_id)
    if not detail:
        return {"error": "产品不存在"}, 404
    p = detail["product"]
    r = detail["rule"]
    return {
        "product": {
            "id": p.id, "name": p.name, "company": p.company, "type": p.type,
            "premium_min": p.premium_min, "premium_max": p.premium_max,
            "sum_insured_min": p.sum_insured_min, "sum_insured_max": p.sum_insured_max,
            "coverage_period": p.coverage_period, "payment_period": p.payment_period,
            "disease_count": p.disease_count,
            "has_mild_coverage": p.has_mild_coverage,
            "has_moderate_coverage": p.has_moderate_coverage,
            "has_multi_claim": p.has_multi_claim,
        },
        "rule": {
            "min_age": r.min_age, "max_age": r.max_age,
            "job_class_limit": r.job_class_limit,
            "waiting_period_days": r.waiting_period_days,
            "has_insured_waiver": r.has_insured_waiver,
            "has_insurer_waiver": r.has_insurer_waiver,
            "health_disclosure_count": r.health_disclosure_count,
        } if r else None,
        "benefits": [
            {
                "benefit_type": b.benefit_type, "benefit_name": b.benefit_name,
                "benefit_amount": b.benefit_amount, "payment_limit": b.payment_limit,
            }
            for b in detail["benefits"]
        ],
    }


@router.post("/compare")
def api_compare(product_ids: list[int], db: Session = Depends(get_db)):
    details = compare_products(db, product_ids)
    return {"comparison": [
        {
            "name": d["product"].name,
            "company": d["product"].company,
            "type": d["product"].type,
            "premium": f"{d['product'].premium_min}-{d['product'].premium_max}",
            "sum_insured": f"{d['product'].sum_insured_min}-{d['product'].sum_insured_max}",
            "benefits": [b.benefit_name for b in d["benefits"]],
        }
        for d in details
    ]}
```

- [ ] **Step 3: 创建 backend/app/api/admin.py**

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/crawl")
def trigger_crawl():
    return {"message": "爬虫任务已提交", "status": "pending"}


@router.get("/logs")
def get_logs():
    return {"logs": []}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/
git commit -m "feat: add products, admin, and health check API routes"
```

---

### Task 12: API 路由 — 推荐接口（含 SSE 流式）

**Files:**
- Create: `backend/app/api/recommend.py`

- [ ] **Step 1: 创建 backend/app/api/recommend.py**

```python
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.schemas.user_profile import UserProfileRequest
from backend.app.schemas.recommendation import RecommendationResponse
from backend.app.engine.models import UserProfile
from backend.app.engine.rule_engine import filter_candidate_pool
from backend.app.engine.scoring import score_product, apply_price_scoring
from backend.app.engine.budget import calculate_budget, calculate_sum_insured
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.ai_engine import ai_rerank_or_fallback
from backend.app.engine.fallback import get_fallback_narrative

router = APIRouter(prefix="/api", tags=["recommend"])


def _run_rule_engine(db: Session, user: UserProfile) -> dict:
    """执行完整的规则引擎链路"""
    # Step 1: 规则树粗筛
    candidates = filter_candidate_pool(db, user)

    # Step 2: 预算 + 保额
    budget = calculate_budget(user)
    sum_insured = calculate_sum_insured(user)

    # Step 3: 6 维评分
    scored = []
    si_map = {
        "医疗险": sum_insured.medical,
        "意外险": sum_insured.accident,
        "重疾险": sum_insured.critical_illness,
        "定期寿险": sum_insured.life,
        "防癌险": sum_insured.cancer,
    }

    for product in candidates:
        rule = product.rules
        benefits = product.benefits
        suggested_si = si_map.get(product.type, 500000)
        detail = score_product(product, rule, benefits, suggested_si)
        risk_warnings = _check_health_warnings(user, rule, product)
        scored.append({
            "product_id": product.id,
            "name": product.name,
            "company": product.company,
            "type": product.type,
            "premium": product.premium_min or 0,
            "sum_insured": product.sum_insured_max or 0,
            "source_url": product.source_url or "",
            "score": detail["total"],
            "score_detail": {k: v for k, v in detail.items() if k != "total"},
            "risk_warnings": risk_warnings,
        })

    # Step 4: 保费竞争力重新计算
    scored = apply_price_scoring(scored)

    # Step 5: 套餐组合
    packages = build_combos(scored, user, budget)

    return {
        "budget": budget,
        "sum_insured": sum_insured,
        "packages": packages,
        "scored": scored,
    }


def _check_health_warnings(user: UserProfile, rule, product) -> list[dict]:
    warnings = []
    if user.health_status != "standard" and user.health_issues:
        warnings.append({
            "type": "health",
            "product_name": product.name,
            "message": f"您的健康异常项可能涉及该产品健康告知，建议走智能核保",
        })
    return warnings


@router.post("/recommend")
def recommend(request: UserProfileRequest, db: Session = Depends(get_db)):
    user = UserProfile(
        age=request.age, gender=request.gender,
        annual_income=request.annual_income, job_class=request.job_class,
        life_stage=request.life_stage, family_burden=request.family_burden,
        health_status=request.health_status, health_issues=request.health_issues,
        existing_coverage=request.existing_coverage,
        budget_ratio=request.budget_ratio,
        preferred_type=request.preferred_type,
        enable_llm_engine=request.enable_llm_engine,
    )

    result = _run_rule_engine(db, user)

    if not request.enable_llm_engine:
        # 极速模式
        return _build_response(user, result, engine_mode="rule")

    # AI 模式走 SSE，此处返回 SSE 流
    return StreamingResponse(
        _sse_recommend_stream(user, result),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _sse_recommend_stream(user: UserProfile, result: dict):
    """SSE 流式输出 AI 推荐结果"""
    # 先发送规则引擎结果
    base = _build_response(user, result, engine_mode="ai")
    base["llm_narrative"] = ""
    yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"

    scored_products = result.get("scored", [])
    ai_gen, mode = await ai_rerank_or_fallback(user, scored_products)

    if mode == "degraded" or ai_gen is None:
        base["llm_narrative"] = get_fallback_narrative(
            result["packages"][0].products if result["packages"] else []
        )
        base["engine_mode"] = "degraded"
        yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    narrative_parts = []
    async for chunk in ai_gen:
        narrative_parts.append(chunk)
        base["llm_narrative"] = "".join(narrative_parts)
        yield f"data: {json.dumps(base, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _build_response(user: UserProfile, result: dict, engine_mode: str = "rule") -> dict:
    budget = result["budget"]
    si = result["sum_insured"]
    packages = result["packages"]

    return {
        "user_profile": {
            "age": user.age, "gender": user.gender,
            "annual_income": user.annual_income,
            "life_stage": user.life_stage, "health_status": user.health_status,
        },
        "budget_analysis": {
            "annual_income": budget.annual_income,
            "total_budget": budget.total_budget,
            "allocation": budget.allocation,
        },
        "sum_insured_advice": {
            "medical": si.medical,
            "accident": si.accident,
            "critical_illness": si.critical_illness,
            "life": si.life,
        },
        "packages": [
            {
                "tag": p.tag,
                "tag_label": p.tag_label,
                "total_premium": p.total_premium,
                "budget_ratio": p.budget_ratio,
                "products": [
                    {
                        "id": sp.product_id, "name": sp.name, "company": sp.company,
                        "type": sp.type, "layer": sp.layer,
                        "premium": sp.premium, "sum_insured": sp.sum_insured,
                        "source_url": sp.source_url,
                        "score": sp.score, "score_detail": sp.score_detail,
                        "risk_warnings": sp.risk_warnings,
                    }
                    for sp in p.products
                ],
            }
            for p in packages
        ],
        "llm_narrative": None,
        "engine_mode": engine_mode,
        "disclaimer": "本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准",
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/recommend.py
git commit -m "feat: add recommendation API with SSE streaming support"
```

---

### Task 13: 限流中间件

**Files:**
- Create: `backend/app/middleware/__init__.py`, `backend/app/middleware/rate_limiter.py`

- [ ] **Step 1: 创建 backend/app/middleware/__init__.py（空文件）**

```bash
touch backend/app/middleware/__init__.py
```

- [ ] **Step 2: 创建 backend/app/middleware/rate_limiter.py**

```python
import time
import redis
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.config import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Redis 令牌桶限流中间件"""

    def __init__(self, app):
        super().__init__(app)
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            self.redis.ping()
        except Exception:
            self.redis = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"

            if not self._check_ip_limit(client_ip):
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

        response = await call_next(request)
        return response

    def _check_ip_limit(self, ip: str) -> bool:
        if self.redis is None:
            return True  # Redis 不可用时放行
        key = f"rate_limit:ip:{ip}"
        current = self.redis.get(key)
        limit = settings.rate_limit_ip_per_minute
        if current is None:
            self.redis.setex(key, 60, 1)
            return True
        if int(current) >= limit:
            return False
        self.redis.incr(key)
        return True
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/middleware/
git commit -m "feat: add Redis token-bucket rate limiter middleware"
```

---

### Task 14: 爬虫 — Playwright 抓取 + LLM 结构化 + 调度器

**Files:**
- Create: `backend/app/crawler/__init__.py`
- Create: `backend/app/crawler/scraper.py`, `backend/app/crawler/llm_extractor.py`, `backend/app/crawler/scheduler.py`

- [ ] **Step 1: 创建 backend/app/crawler/__init__.py（空文件）**

```bash
touch backend/app/crawler/__init__.py
```

- [ ] **Step 2: 创建 backend/app/crawler/scraper.py**

```python
import hashlib
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def fetch_page_text(url: str, timeout: int = 30000) -> tuple[str, str]:
    """使用 Playwright 抓取页面并返回纯文本 + 原始 HTML"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout)
        page.wait_for_load_state("networkidle")
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        browser.close()
        return text, html


def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def detect_off_shelf(text: str) -> bool:
    """检测页面是否包含停售关键词"""
    keywords = ["已停售", "暂不可投保", "已下架", "停止销售", "不在售"]
    return any(kw in text for kw in keywords)
```

- [ ] **Step 3: 创建 backend/app/crawler/llm_extractor.py**

```python
import json
from openai import OpenAI
from backend.app.config import settings

EXTRACT_PROMPT = """你是一个保险产品信息提取器。从以下网页文本中提取保险产品信息，严格按 JSON 格式输出。

{
  "name": "产品全称",
  "company": "保险公司",
  "type": "险种（重疾险/医疗险/意外险/定期寿险/防癌险/年金险）",
  "premium_min": 0,
  "premium_max": 0,
  "sum_insured_min": 0,
  "sum_insured_max": 0,
  "coverage_period": "保障期限",
  "payment_period": "缴费期限",
  "disease_count": 0,
  "mild_disease_count": 0,
  "moderate_disease_count": 0,
  "has_mild_coverage": false,
  "has_moderate_coverage": false,
  "has_multi_claim": false,
  "min_age": 0,
  "max_age": 100,
  "job_class_limit": 6,
  "waiting_period_days": 90,
  "has_insured_waiver": false,
  "has_insurer_waiver": false,
  "health_disclosure_count": 0,
  "health_requirements": [],
  "benefits": [
    {
      "benefit_type": "basic",
      "benefit_name": "责任名称",
      "benefit_amount": "赔付金额描述",
      "payment_limit": "赔付上限"
    }
  ]
}

规则：
- 无法提取的数值字段填 0 或默认值
- type 必须严格匹配枚举值
- benefits 数组从网页保障责任段落提取
- 所有金额单位为"元"
"""


def extract_product(text: str) -> dict | None:
    """使用 LLM 提取结构化产品信息"""
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_read_timeout,
    )

    for attempt in range(settings.llm_max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": EXTRACT_PROMPT},
                    {"role": "user", "content": text[:8000]},
                ],
                response_format={"type": "json_object"},
                timeout=settings.llm_read_timeout,
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            if attempt == settings.llm_max_retries - 1:
                print(f"LLM extraction failed after {settings.llm_max_retries} retries: {e}")
                return None
    return None
```

- [ ] **Step 4: 创建 backend/app/crawler/scheduler.py**

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


def init_scheduler():
    """初始化定时任务：每周一凌晨 2 点巡检"""
    # from backend.app.crawler.scraper import crawl_all_active_products
    # scheduler.add_job(crawl_all_active_products, "cron", day_of_week="mon", hour=2)
    scheduler.start()
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/crawler/
git commit -m "feat: add Playwright scraper, LLM extractor, and APScheduler"
```

---

### Task 15: FastAPI 入口

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: 创建 backend/main.py**

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.database import init_db
from backend.app.api.products import router as products_router
from backend.app.api.recommend import router as recommend_router
from backend.app.api.admin import router as admin_router
from backend.app.middleware.rate_limiter import RateLimiterMiddleware
from backend.app.crawler.scheduler import init_scheduler

app = FastAPI(
    title="智能保险推荐引擎",
    description="Smart Insurance Recommendation System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)

app.include_router(products_router)
app.include_router(recommend_router)
app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    os.makedirs("data", exist_ok=True)
    init_db()
    init_scheduler()


@app.get("/")
def root():
    return {"message": "智能保险推荐引擎已启动", "version": "1.0.0"}
```

- [ ] **Step 2: 启动后端验证**

```bash
cd backend && pip install -r requirements.txt && python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl http://localhost:8000/
curl http://localhost:8000/api/health
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add FastAPI entry point with all routes and middleware"
```

---

### Task 16: 前端基础 — 类型定义 + API 封装 + SSE Hook

**Files:**
- Create: `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/api/recommend.ts`, `frontend/src/api/products.ts`
- Create: `frontend/src/hooks/useSSE.ts`, `frontend/src/main.tsx`

- [ ] **Step 1: 创建 frontend/src/types/index.ts**

```typescript
export interface UserProfile {
  age: number;
  gender: 'male' | 'female';
  annual_income: number;
  job_class: number;
  life_stage: string;
  family_burden: string;
  health_status: string;
  health_issues: string[];
  existing_coverage: string[];
  budget_ratio: number;
  preferred_type?: string;
  enable_llm_engine: boolean;
}

export interface ScoreDetail {
  coverage: number;
  price: number;
  flexibility: number;
  waiting: number;
  adequacy: number;
  waiver: number;
}

export interface ProductItem {
  id: number;
  name: string;
  company: string;
  type: string;
  layer: string;
  premium: number;
  sum_insured: number;
  source_url: string;
  score: number;
  score_detail: ScoreDetail;
  risk_warnings: RiskWarning[];
}

export interface RiskWarning {
  type: string;
  product_name: string;
  message: string;
}

export interface ComboPackage {
  tag: string;
  tag_label: string;
  total_premium: number;
  budget_ratio: number;
  products: ProductItem[];
}

export interface RecommendationResult {
  user_profile: Record<string, unknown>;
  budget_analysis: {
    annual_income: number;
    total_budget: number;
    allocation: { medical: number; accident: number; critical_illness: number; life: number };
  };
  sum_insured_advice: {
    medical: number;
    accident: number;
    critical_illness: number;
    life: number;
  };
  packages: ComboPackage[];
  llm_narrative: string | null;
  engine_mode: string;
  disclaimer: string;
}

export interface ProductInfo {
  id: number;
  name: string;
  company: string;
  type: string;
  status: number;
  premium_min: number;
  premium_max: number;
  sum_insured_max: number;
}
```

- [ ] **Step 2: 创建 frontend/src/api/client.ts**

```typescript
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 35000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 429) {
      console.error('请求过于频繁，请稍后再试');
    }
    return Promise.reject(err);
  }
);

export default apiClient;
```

- [ ] **Step 3: 创建 frontend/src/api/recommend.ts**

```typescript
import apiClient from './client';
import type { UserProfile, RecommendationResult } from '../types';

export async function fetchRecommend(userProfile: UserProfile): Promise<RecommendationResult> {
  const { data } = await apiClient.post<RecommendationResult>('/recommend', userProfile);
  return data;
}

export function fetchRecommendSSE(
  userProfile: UserProfile,
  onData: (result: RecommendationResult) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userProfile),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const content = line.slice(6);
            if (content === '[DONE]') { onDone(); return; }
            try {
              const result = JSON.parse(content) as RecommendationResult;
              onData(result);
            } catch { /* ignore partial chunk */ }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err);
    });
  return controller;
}
```

- [ ] **Step 4: 创建 frontend/src/api/products.ts**

```typescript
import apiClient from './client';
import type { ProductInfo } from '../types';

export async function fetchProducts(type?: string): Promise<ProductInfo[]> {
  const { data } = await apiClient.get<{ products: ProductInfo[] }>('/products', {
    params: type ? { type } : {},
  });
  return data.products;
}

export async function fetchProductDetail(id: number): Promise<unknown> {
  const { data } = await apiClient.get(`/products/${id}`);
  return data;
}
```

- [ ] **Step 5: 创建 frontend/src/hooks/useSSE.ts**

```typescript
import { useRef, useCallback } from 'react';

export function useSSE() {
  const controllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const setController = useCallback((c: AbortController) => {
    controllerRef.current = c;
  }, []);

  return { abort, setController };
}
```

- [ ] **Step 6: 创建 frontend/src/main.tsx**

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/ frontend/src/api/ frontend/src/hooks/ frontend/src/main.tsx
git commit -m "feat: add frontend types, API client, SSE hook, and entry point"
```

---

### Task 17: 前端组件 — 基础组件

**Files:**
- Create: `frontend/src/components/ProgressSteps.tsx`, `frontend/src/components/EngineSwitch.tsx`, `frontend/src/components/RiskBadge.tsx`, `frontend/src/components/Disclaimer.tsx`

- [ ] **Step 1: 创建 frontend/src/components/ProgressSteps.tsx**

```typescript
import { Steps } from 'antd';

const steps = [
  { title: '基本信息' },
  { title: '职业与收入' },
  { title: '健康告知' },
  { title: '偏好确认' },
];

interface Props {
  current: number;
}

export default function ProgressSteps({ current }: Props) {
  return <Steps current={current} items={steps} style={{ marginBottom: 32 }} />;
}
```

- [ ] **Step 2: 创建 frontend/src/components/EngineSwitch.tsx**

```typescript
import { Switch, Space, Typography } from 'antd';
import { ThunderboltOutlined, RobotOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface Props {
  enabled: boolean;
  onChange: (v: boolean) => void;
}

export default function EngineSwitch({ enabled, onChange }: Props) {
  return (
    <Space>
      <ThunderboltOutlined style={{ color: enabled ? '#999' : '#1890ff' }} />
      <Text type={enabled ? 'secondary' : undefined}>极速模式</Text>
      <Switch checked={enabled} onChange={onChange} />
      <Text type={enabled ? undefined : 'secondary'}>AI 专家模式</Text>
      <RobotOutlined style={{ color: enabled ? '#1890ff' : '#999' }} />
    </Space>
  );
}
```

- [ ] **Step 3: 创建 frontend/src/components/RiskBadge.tsx**

```typescript
import { Tag, Tooltip } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import type { RiskWarning } from '../types';

interface Props {
  warnings: RiskWarning[];
}

export default function RiskBadge({ warnings }: Props) {
  if (!warnings.length) return null;
  return (
    <Tooltip title={warnings.map((w) => w.message).join('；')}>
      <Tag color="error" icon={<ExclamationCircleOutlined />}>需关注</Tag>
    </Tooltip>
  );
}
```

- [ ] **Step 4: 创建 frontend/src/components/Disclaimer.tsx**

```typescript
import { Alert } from 'antd';

export default function Disclaimer() {
  return (
    <Alert
      type="info"
      showIcon
      message="免责声明"
      description="本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准。投保前请仔细阅读产品条款和健康告知。"
      style={{ marginTop: 24 }}
    />
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressSteps.tsx frontend/src/components/EngineSwitch.tsx frontend/src/components/RiskBadge.tsx frontend/src/components/Disclaimer.tsx
git commit -m "feat: add base UI components (steps, switch, badge, disclaimer)"
```

---

### Task 18: 前端组件 — 复杂组件

**Files:**
- Create: `frontend/src/components/BudgetPreview.tsx`, `frontend/src/components/ScoreRadar.tsx`, `frontend/src/components/ProductCard.tsx`, `frontend/src/components/CompareTable.tsx`

- [ ] **Step 1: 创建 frontend/src/components/BudgetPreview.tsx**

```typescript
import { Card, Progress, Row, Col, Statistic } from 'antd';

interface Props {
  annualIncome: number;
  totalBudget: number;
  allocation: { medical: number; accident: number; critical_illness: number; life: number };
}

export default function BudgetPreview({ annualIncome, totalBudget, allocation }: Props) {
  const pct = (v: number) => Math.round(v * 100);
  return (
    <Card title="预算分析" size="small">
      <Row gutter={16}>
        <Col span={8}><Statistic title="年收入" value={annualIncome} prefix="¥" /></Col>
        <Col span={8}><Statistic title="推荐预算" value={totalBudget} prefix="¥" precision={0} /></Col>
        <Col span={8}><Statistic title="占比" value={((totalBudget / annualIncome) * 100).toFixed(1)} suffix="%" /></Col>
      </Row>
      <div style={{ marginTop: 16 }}>
        <div>医疗险 <Progress percent={pct(allocation.medical)} size="small" /></div>
        <div>意外险 <Progress percent={pct(allocation.accident)} size="small" /></div>
        <div>重疾险 <Progress percent={pct(allocation.critical_illness)} size="small" /></div>
        <div>寿　险 <Progress percent={pct(allocation.life)} size="small" /></div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: 创建 frontend/src/components/ScoreRadar.tsx**

```typescript
import type { ScoreDetail } from '../types';

interface Props {
  detail: ScoreDetail;
  size?: number;
}

const DIMENSIONS: { key: keyof ScoreDetail; label: string }[] = [
  { key: 'coverage', label: '保障全面性' },
  { key: 'price', label: '保费竞争力' },
  { key: 'flexibility', label: '投保宽松度' },
  { key: 'waiting', label: '等待期' },
  { key: 'waiver', label: '豁免条款' },
  { key: 'adequacy', label: '保额充足度' },
];

export default function ScoreRadar({ detail }: Props) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12 }}>
      {DIMENSIONS.map((d) => (
        <span key={d.key}>
          {d.label}: <strong>{detail[d.key]}</strong>
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 创建 frontend/src/components/ProductCard.tsx**

```typescript
import { Card, Tag, Typography } from 'antd';
import ScoreRadar from './ScoreRadar';
import RiskBadge from './RiskBadge';
import type { ProductItem } from '../types';

const { Text } = Typography;

const LAYER_COLORS: Record<string, string> = {
  basic: 'blue',
  core: 'gold',
  supplement: 'green',
};

const LAYER_LABELS: Record<string, string> = {
  basic: '基础层',
  core: '核心层',
  supplement: '补充层',
};

interface Props {
  product: ProductItem;
}

export default function ProductCard({ product }: Props) {
  return (
    <Card
      size="small"
      title={
        <span>
          {product.source_url ? (
            <a href={product.source_url} target="_blank" rel="noopener noreferrer">
              {product.name}
            </a>
          ) : (
            product.name
          )}
          <Tag color={LAYER_COLORS[product.layer]} style={{ marginLeft: 8 }}>
            {LAYER_LABELS[product.layer]}
          </Tag>
        </span>
      }
      extra={<RiskBadge warnings={product.risk_warnings} />}
    >
      <Text type="secondary">{product.company} · {product.type}</Text>
      <div style={{ marginTop: 8 }}>
        <Text strong>¥{product.premium.toLocaleString()}/年</Text>
        <Text style={{ marginLeft: 16 }}>保额 {product.sum_insured.toLocaleString()}</Text>
        <Tag color="orange" style={{ marginLeft: 8 }}>评分 {product.score}</Tag>
      </div>
      <div style={{ marginTop: 8 }}>
        <ScoreRadar detail={product.score_detail} />
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: 创建 frontend/src/components/CompareTable.tsx**

```typescript
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ProductItem } from '../types';

interface Props {
  products: ProductItem[];
}

export default function CompareTable({ products }: Props) {
  if (!products.length) return null;

  const columns: ColumnsType<ProductItem> = [
    {
      title: '产品名称', dataIndex: 'name', key: 'name', fixed: 'left', width: 200,
      render: (v: string, record: ProductItem) =>
        record.source_url ? (
          <a href={record.source_url} target="_blank" rel="noopener noreferrer">{v}</a>
        ) : v,
    },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 120 },
    {
      title: '险种', dataIndex: 'type', key: 'type', width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '保费(元/年)', dataIndex: 'premium', key: 'premium', width: 120,
      render: (v: number) => `¥${v.toLocaleString()}`,
      sorter: (a: ProductItem, b: ProductItem) => a.premium - b.premium,
    },
    {
      title: '保额', dataIndex: 'sum_insured', key: 'sum_insured', width: 120,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '综合评分', dataIndex: 'score', key: 'score', width: 100,
      render: (v: number) => <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}</Tag>,
      sorter: (a: ProductItem, b: ProductItem) => a.score - b.score,
    },
    { title: '保障全面性', dataIndex: ['score_detail', 'coverage'], key: 'coverage', width: 100 },
    { title: '保费竞争力', dataIndex: ['score_detail', 'price'], key: 'price', width: 100 },
    { title: '投保宽松度', dataIndex: ['score_detail', 'flexibility'], key: 'flexibility', width: 100 },
  ];

  return (
    <Table
      columns={columns}
      dataSource={products}
      rowKey="id"
      scroll={{ x: 1100 }}
      pagination={false}
      size="small"
      bordered
    />
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BudgetPreview.tsx frontend/src/components/ScoreRadar.tsx frontend/src/components/ProductCard.tsx frontend/src/components/CompareTable.tsx
git commit -m "feat: add complex UI components (budget, radar, product card, compare table)"
```

---

### Task 19: 前端页面 — 首页问卷

**Files:**
- Create: `frontend/src/pages/HomePage.tsx`

- [ ] **Step 1: 创建 frontend/src/pages/HomePage.tsx**

```typescript
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, InputNumber, Select, Radio, Checkbox, Slider, Button, Card, Space, Typography, Row, Col } from 'antd';
import ProgressSteps from '../components/ProgressSteps';
import EngineSwitch from '../components/EngineSwitch';
import type { UserProfile } from '../types';

const { Title } = Typography;

export default function HomePage() {
  const [step, setStep] = useState(0);
  const [aiMode, setAiMode] = useState(false);
  const [income, setIncome] = useState(200000);
  const [budgetRatio, setBudgetRatio] = useState(0.08);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const onFinish = (values: Record<string, unknown>) => {
    const profile: UserProfile = {
      age: values.age as number,
      gender: values.gender as 'male' | 'female',
      annual_income: income,
      job_class: values.job_class as number,
      life_stage: values.life_stage as string,
      family_burden: values.family_burden as string,
      health_status: values.health_status as string,
      health_issues: (values.health_issues as string[]) || [],
      existing_coverage: (values.existing_coverage as string[]) || [],
      budget_ratio: budgetRatio,
      enable_llm_engine: aiMode,
    };
    navigate('/result', { state: { profile } });
  };

  return (
    <Card style={{ maxWidth: 720, margin: '40px auto' }}>
      <Title level={3} style={{ textAlign: 'center' }}>智能保险推荐</Title>
      <ProgressSteps current={step} />

      <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{
        gender: 'male', life_stage: 'single', family_burden: 'none',
        health_status: 'standard', job_class: 2,
      }}>
        {step === 0 && (
          <>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="age" label="年龄" rules={[{ required: true }]}>
                  <InputNumber min={0} max={120} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="gender" label="性别" rules={[{ required: true }]}>
                  <Radio.Group>
                    <Radio.Button value="male">男</Radio.Button>
                    <Radio.Button value="female">女</Radio.Button>
                  </Radio.Group>
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="life_stage" label="人生阶段" rules={[{ required: true }]}>
              <Select options={[
                { label: '单身', value: 'single' }, { label: '已婚无孩', value: 'married' },
                { label: '已婚有孩', value: 'married_with_kids' }, { label: '空巢', value: 'empty_nest' },
                { label: '退休', value: 'retired' },
              ]} />
            </Form.Item>
            <Form.Item name="family_burden" label="家庭负担">
              <Select options={[
                { label: '无负担', value: 'none' }, { label: '需赡养父母', value: 'parents' },
                { label: '需抚养子女', value: 'children' }, { label: '双重负担', value: 'dual' },
              ]} />
            </Form.Item>
          </>
        )}

        {step === 1 && (
          <>
            <Form.Item label="年收入（元）">
              <InputNumber value={income} onChange={(v) => setIncome(v || 0)}
                min={10000} max={10000000} step={10000} style={{ width: '100%' }}
                formatter={(v) => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
            </Form.Item>
            <Form.Item name="job_class" label="职业类别" rules={[{ required: true }]}>
              <Select options={[
                { label: '1类（低风险·室内办公）', value: 1 }, { label: '2类（较轻·外勤文职）', value: 2 },
                { label: '3类（一般·轻体力劳动）', value: 3 }, { label: '4类（中等·制造业）', value: 4 },
                { label: '5类（较高·建筑运输）', value: 5 }, { label: '6类（高风险·高空矿下）', value: 6 },
              ]} />
            </Form.Item>
            <Form.Item name="existing_coverage" label="已有保障">
              <Checkbox.Group options={[
                { label: '社保', value: 'social' }, { label: '已有商业保险', value: 'commercial' },
              ]} />
            </Form.Item>
            <Form.Item label={`预算占比：${(budgetRatio * 100).toFixed(0)}%（≈ ¥${(income * budgetRatio).toLocaleString()}/年）`}>
              <Slider min={3} max={10} step={0.5} value={budgetRatio * 100}
                onChange={(v) => setBudgetRatio((v as number) / 100)} />
            </Form.Item>
          </>
        )}

        {step === 2 && (
          <>
            <Form.Item name="health_status" label="健康状态" rules={[{ required: true }]}>
              <Radio.Group>
                <Radio.Button value="standard">标准体（无异常）</Radio.Button>
                <Radio.Button value="substandard">次标准体（结节/三高等）</Radio.Button>
                <Radio.Button value="history">有病史（住院/手术史）</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item name="health_issues" label="具体异常项（可多选）">
              <Checkbox.Group options={[
                { label: '甲状腺/乳腺/肺结节', value: 'nodule' },
                { label: '高血压', value: 'hypertension' },
                { label: '高血糖/糖尿病', value: 'diabetes' },
                { label: '住院史', value: 'hospitalization' },
                { label: '手术史', value: 'surgery' },
              ]} />
            </Form.Item>
          </>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center' }}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <EngineSwitch enabled={aiMode} onChange={setAiMode} />
              <Card size="small">
                <p>您的推荐预算约为 <strong>¥{(income * budgetRatio).toLocaleString()}/年</strong></p>
                <p>将为您匹配医疗险 + 意外险 + 重疾险 + 定期寿险方案</p>
              </Card>
              {aiMode && (
                <Card size="small" style={{ background: '#e6f7ff' }}>
                  AI 模式将为您全网比对产品，生成个性化推荐语
                </Card>
              )}
            </Space>
          </div>
        )}

        <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
          <Button disabled={step === 0} onClick={() => setStep((s) => s - 1)}>上一步</Button>
          {step < 3 ? (
            <Button type="primary" onClick={() => setStep((s) => s + 1)}>下一步</Button>
          ) : (
            <Button type="primary" htmlType="submit">开始推荐</Button>
          )}
        </div>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/HomePage.tsx
git commit -m "feat: add home page with 4-step questionnaire"
```

---

### Task 20: 前端页面 — 结果页 + 管理页 + App 路由

**Files:**
- Create: `frontend/src/pages/ResultPage.tsx`, `frontend/src/pages/AdminPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 创建 frontend/src/pages/ResultPage.tsx**

```typescript
import { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, Tabs, Typography, Spin, Tag, Row, Col, Statistic } from 'antd';
import BudgetPreview from '../components/BudgetPreview';
import ProductCard from '../components/ProductCard';
import CompareTable from '../components/CompareTable';
import Disclaimer from '../components/Disclaimer';
import { fetchRecommend, fetchRecommendSSE } from '../api/recommend';
import type { UserProfile, RecommendationResult, ProductItem } from '../types';

const { Title, Paragraph } = Typography;

export default function ResultPage() {
  const location = useLocation();
  const profile = location.state?.profile as UserProfile;
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    if (profile.enable_llm_engine) {
      fetchRecommendSSE(
        profile,
        (data) => setResult(data),
        () => setLoading(false),
        () => { fetchRecommend(profile).then(setResult).finally(() => setLoading(false)); },
      );
    } else {
      const data = await fetchRecommend(profile);
      setResult(data);
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => { loadData(); }, [loadData]);

  if (!profile) return <div style={{ padding: 40, textAlign: 'center' }}>请先填写问卷信息</div>;
  if (loading && !result) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" tip="正在分析推荐..." /></div>;
  }
  if (!result) return null;

  const allProducts: ProductItem[] = result.packages.flatMap((p) => p.products);

  return (
    <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 16px' }}>
      <Title level={3}>推荐方案</Title>
      <Tag color={result.engine_mode === 'ai' ? 'blue' : result.engine_mode === 'degraded' ? 'orange' : 'green'}>
        {result.engine_mode === 'ai' ? 'AI 专家模式' : result.engine_mode === 'degraded' ? '降级模式' : '极速规则模式'}
      </Tag>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <BudgetPreview
            annualIncome={result.budget_analysis.annual_income}
            totalBudget={result.budget_analysis.total_budget}
            allocation={result.budget_analysis.allocation}
          />
        </Col>
        <Col span={12}>
          <Card title="建议保额" size="small">
            <Statistic title="医疗险" value={result.sum_insured_advice.medical} suffix="元" />
            <Statistic title="意外险" value={result.sum_insured_advice.accident} suffix="元" />
            <Statistic title="重疾险" value={result.sum_insured_advice.critical_illness} suffix="元" />
            <Statistic title="定期寿险" value={result.sum_insured_advice.life} suffix="元" />
          </Card>
        </Col>
      </Row>

      {result.llm_narrative && (
        <Card style={{ marginTop: 16, background: '#e6f7ff' }}>
          <Paragraph>{result.llm_narrative}</Paragraph>
        </Card>
      )}

      <Tabs
        style={{ marginTop: 16 }}
        items={result.packages.map((pkg) => ({
          key: pkg.tag,
          label: `${pkg.tag_label} (¥${pkg.total_premium.toLocaleString()}/年)`,
          children: (
            <div>
              {pkg.products.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          ),
        }))}
      />

      <Card title="横向对比" style={{ marginTop: 16 }}>
        <CompareTable products={allProducts} />
      </Card>

      <Disclaimer />
    </div>
  );
}
```

- [ ] **Step 2: 创建 frontend/src/pages/AdminPage.tsx**

```typescript
import { useState, useEffect } from 'react';
import { Table, Button, Card, Typography, message } from 'antd';
import { fetchProducts } from '../api/products';
import type { ProductInfo } from '../types';
import type { ColumnsType } from 'antd/es/table';

const { Title } = Typography;

export default function AdminPage() {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const data = await fetchProducts();
    setProducts(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const columns: ColumnsType<ProductInfo> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '产品名称', dataIndex: 'name', key: 'name' },
    { title: '公司', dataIndex: 'company', key: 'company', width: 150 },
    { title: '险种', dataIndex: 'type', key: 'type', width: 100 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: number) => v === 1 ? '在售' : '停售',
    },
    { title: '最低保费', dataIndex: 'premium_min', key: 'premium_min', width: 100 },
    { title: '最高保额', dataIndex: 'sum_insured_max', key: 'sum_insured_max', width: 100 },
  ];

  return (
    <Card style={{ maxWidth: 960, margin: '24px auto' }}>
      <Title level={3}>产品管理</Title>
      <Button type="primary" style={{ marginBottom: 16 }}
        onClick={async () => {
          await fetch('/api/admin/crawl', { method: 'POST' });
          message.success('爬虫任务已提交');
        }}>
        手动触发爬虫
      </Button>
      <Table columns={columns} dataSource={products} rowKey="id"
        loading={loading} size="small" pagination={{ pageSize: 20 }} />
    </Card>
  );
}
```

- [ ] **Step 3: 创建 frontend/src/App.tsx**

```typescript
import { Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { HomeOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import HomePage from './pages/HomePage';
import ResultPage from './pages/ResultPage';
import AdminPage from './pages/AdminPage';

const { Header, Content } = Layout;

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header>
        <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['home']}
          items={[
            { key: 'home', icon: <HomeOutlined />, label: <Link to="/">首页问卷</Link> },
            { key: 'result', icon: <SearchOutlined />, label: <Link to="/result">推荐结果</Link> },
            { key: 'admin', icon: <SettingOutlined />, label: <Link to="/admin">管理后台</Link> },
          ]}
        />
      </Header>
      <Content>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/result" element={<ResultPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Content>
    </Layout>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat: add result page, admin page, and App routing"
```

---

### Task 21: 种子数据 + 验证

**Files:**
- Create: `backend/scripts/seed.py`

- [ ] **Step 1: 创建 backend/scripts/seed.py**

```python
"""种子数据脚本：插入示例保险产品供开发测试"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.app.database import init_db, SessionLocal
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit


def seed():
    init_db()
    db = SessionLocal()

    products_data = [
        {
            "name": "平安e生保长期医疗险", "company": "平安健康", "type": "医疗险",
            "premium_min": 300, "premium_max": 800, "sum_insured_min": 200, "sum_insured_max": 400,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://health.pingan.com/yishengbao/index.shtml",
            "disease_count": 120, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 65, "job_class_limit": 4, "waiting_period_days": 30,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 5},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "一般住院医疗", "benefit_amount": "200万", "payment_limit": "年限额200万"},
                {"benefit_type": "basic", "benefit_name": "重疾住院医疗", "benefit_amount": "400万", "payment_limit": "年限额400万"},
                {"benefit_type": "special", "benefit_name": "质子重离子", "benefit_amount": "100万", "payment_limit": "年限额100万"},
            ],
        },
        {
            "name": "众安尊享e生百万医疗险", "company": "众安保险", "type": "医疗险",
            "premium_min": 200, "premium_max": 600, "sum_insured_min": 300, "sum_insured_max": 600,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.zhongan.com/product/zxes/index.html",
            "disease_count": 100, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 70, "job_class_limit": 4, "waiting_period_days": 30,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 4},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "一般住院医疗", "benefit_amount": "300万", "payment_limit": "年限额300万"},
                {"benefit_type": "basic", "benefit_name": "重疾住院医疗", "benefit_amount": "600万", "payment_limit": "年限额600万"},
            ],
        },
        {
            "name": "人保大护甲意外险", "company": "人保财险", "type": "意外险",
            "premium_min": 100, "premium_max": 300, "sum_insured_min": 30, "sum_insured_max": 100,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.picc.com/html/znhl/cpzs/dhj/index.shtml",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 60, "job_class_limit": 3, "waiting_period_days": 0,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 0},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "意外身故/伤残", "benefit_amount": "50万", "payment_limit": "单次事故50万"},
                {"benefit_type": "basic", "benefit_name": "意外医疗", "benefit_amount": "5万", "payment_limit": "年限额5万"},
                {"benefit_type": "special", "benefit_name": "猝死保障", "benefit_amount": "20万", "payment_limit": ""},
            ],
        },
        {
            "name": "太平洋小蜜蜂意外险", "company": "太平洋保险", "type": "意外险",
            "premium_min": 150, "premium_max": 350, "sum_insured_min": 50, "sum_insured_max": 100,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.cpic.com.cn/product/ywx/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 65, "job_class_limit": 3, "waiting_period_days": 0,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 0},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "意外身故/伤残", "benefit_amount": "100万", "payment_limit": ""},
                {"benefit_type": "basic", "benefit_name": "意外医疗", "benefit_amount": "10万", "payment_limit": "年限额10万"},
            ],
        },
        {
            "name": "达尔文10号重疾险", "company": "信泰人寿", "type": "重疾险",
            "premium_min": 4000, "premium_max": 8000, "sum_insured_min": 30, "sum_insured_max": 80,
            "coverage_period": "终身", "payment_period": "30年",
            "source_url": "https://www.xintai.com/product/darwin10/",
            "disease_count": 180, "mild_disease_count": 50, "moderate_disease_count": 25,
            "has_mild_coverage": True, "has_moderate_coverage": True, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 55, "job_class_limit": 4, "waiting_period_days": 90,
                     "has_insured_waiver": True, "has_insurer_waiver": True, "health_disclosure_count": 8},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "重疾保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "中症保险金", "benefit_amount": "60%基本保额", "payment_limit": "最多2次"},
                {"benefit_type": "basic", "benefit_name": "轻症保险金", "benefit_amount": "30%基本保额", "payment_limit": "最多3次"},
                {"benefit_type": "waiver", "benefit_name": "被保人豁免", "benefit_amount": "豁免后续保费", "payment_limit": ""},
            ],
        },
        {
            "name": "超级玛丽12号重疾险", "company": "和泰人寿", "type": "重疾险",
            "premium_min": 3500, "premium_max": 7000, "sum_insured_min": 30, "sum_insured_max": 70,
            "coverage_period": "终身", "payment_period": "30年",
            "source_url": "https://www.htlife.com/product/supermary12/",
            "disease_count": 190, "mild_disease_count": 45, "moderate_disease_count": 20,
            "has_mild_coverage": True, "has_moderate_coverage": True, "has_multi_claim": True,
            "rule": {"min_age": 0, "max_age": 50, "job_class_limit": 4, "waiting_period_days": 180,
                     "has_insured_waiver": True, "has_insurer_waiver": False, "health_disclosure_count": 10},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "重疾保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "第二次重疾保险金", "benefit_amount": "120%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "中症保险金", "benefit_amount": "60%基本保额", "payment_limit": "最多2次"},
                {"benefit_type": "basic", "benefit_name": "轻症保险金", "benefit_amount": "30%基本保额", "payment_limit": "最多3次"},
            ],
        },
        {
            "name": "华贵大麦定寿", "company": "华贵人寿", "type": "定期寿险",
            "premium_min": 800, "premium_max": 2000, "sum_insured_min": 50, "sum_insured_max": 200,
            "coverage_period": "至60岁", "payment_period": "30年",
            "source_url": "https://www.huaguilife.com/product/damai/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 55, "job_class_limit": 3, "waiting_period_days": 90,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 4},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "身故/全残保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
            ],
        },
        {
            "name": "阳光人寿防癌险", "company": "阳光人寿", "type": "防癌险",
            "premium_min": 2000, "premium_max": 5000, "sum_insured_min": 10, "sum_insured_max": 20,
            "coverage_period": "终身", "payment_period": "20年",
            "source_url": "https://www.sunshine-life.com/product/fangaixian/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 45, "max_age": 70, "job_class_limit": 6, "waiting_period_days": 180,
                     "has_insured_waiver": True, "has_insurer_waiver": False, "health_disclosure_count": 6},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "恶性肿瘤保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "原位癌保险金", "benefit_amount": "20%基本保额", "payment_limit": "1次"},
            ],
        },
    ]

    for pdata in products_data:
        rule_data = pdata.pop("rule")
        benefits_data = pdata.pop("benefits")

        product = Product(**pdata)
        db.add(product)
        db.flush()

        rule = Rule(product_id=product.id, **rule_data)
        db.add(rule)

        for bdata in benefits_data:
            benefit = Benefit(product_id=product.id, **bdata)
            db.add(benefit)

        db.flush()

    db.commit()
    db.close()
    print(f"Seeded {len(products_data)} products successfully.")


if __name__ == "__main__":
    seed()
```

- [ ] **Step 2: 运行种子数据脚本验证**

```bash
cd backend && mkdir -p data && python scripts/seed.py && python -c "
from app.database import init_db, SessionLocal
from app.models.product import Product
init_db()
db = SessionLocal()
count = db.query(Product).count()
print(f'Products in DB: {count}')
assert count == 8, f'Expected 8, got {count}'
db.close()
print('OK')
"
```

- [ ] **Step 3: 测试推荐 API**

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"age":32,"gender":"male","annual_income":200000,"job_class":2,"life_stage":"married_with_kids","family_burden":"dual","health_status":"standard","budget_ratio":0.08,"enable_llm_engine":false}'
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/ backend/data/
git commit -m "feat: add seed data script with 8 sample insurance products"
```

---

### Task 22: 前端验证 + nginx 配置

**Files:**
- Create: `frontend/nginx.conf`
- Create: `frontend/src/vite-env.d.ts`

- [ ] **Step 1: 创建 frontend/nginx.conf**

```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 35s;
    }
}
```

- [ ] **Step 2: 创建 frontend/src/vite-env.d.ts**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 3: 验证前端构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/nginx.conf frontend/src/vite-env.d.ts
git commit -m "feat: add nginx config and frontend build verification"
```

---

## 实施顺序

```
Task 1  (脚手架)      ──┐
                        ├──> Task 3  (模型)  ──> Task 4  (引擎模型+配置)
Task 2  (配置+DB)     ──┘                            │
                                                     ├──> Task 5  (规则树)
                                                     ├──> Task 6  (评分)
                                                     ├──> Task 7  (预算)
                                                     ├──> Task 8  (套餐组合)
                                                     └──> Task 9  (AI+降级)
                                                              │
Task 10 (Schema+Service) ────────────────────────────────────┤
                                                              │
Task 11 (API-产品+管理) ──┐                                   │
                          ├──> Task 12 (API-推荐) ────────────┘
Task 13 (限流中间件)     ──┘        │
                                    ├──> Task 15 (FastAPI入口)
Task 14 (爬虫)          ────────────┘        │
                                             │
Task 16 (前端基础)      ─────────────────────┤
        │                                    │
Task 17 (基础组件)      ──┐                   │
                          ├──> Task 19 (首页) │
Task 18 (复杂组件)      ──┘                   │
        │                                    │
        └──> Task 20 (结果页+管理+路由) ──────┤
                                             │
Task 21 (种子数据)      ─────────────────────┤
                                             │
Task 22 (前端验证)      ─────────────────────┘
```
