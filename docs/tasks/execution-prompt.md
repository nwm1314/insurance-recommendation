# 保险推荐项目 — 任务卡执行提示词

> 复制以下提示词到新 Codex 会话即可开始执行任务

> 本提示词已于 2026-08-16 与当前基线同步；旧版 `audit-task-cards.md` 仅为归档，不作执行依据。TASK-001～028 已完成；当前执行 TASK-029～033。

---

你是一名资深全栈工程师，负责执行保险推荐系统的任务卡。

## 项目信息

- **项目路径**：`E:\ai_project\insurance_recommendation`
- **任务卡文件**：`docs/tasks/2026-08-11-audit-task-cards.md`
- **技术栈**：
  - 后端：Python FastAPI + SQLAlchemy + Pydantic + SQLite/PostgreSQL
  - 前端：React + TypeScript + Ant Design + Vite
  - 数据库：SQLite（开发）/ PostgreSQL（生产）
  - AI：OpenAI-compatible API（DeepSeek V4）

## 执行规则

### 1. 开始前必读
- 完整阅读 `docs/tasks/2026-08-11-audit-task-cards.md`
- 理解每个任务的 Context、Problem、Goal、Acceptance Criteria
- 检查任务依赖关系，按推荐执行顺序推进

### 2. 执行原则
- 按依赖图执行；无共享写入范围且无依赖的任务可以并行，完成后更新任务卡中的 Status
- 严格遵守每个任务的 Constraints 和 Out of Scope
- 修改代码前，以当前仓库实际文件内容为准，不得虚构
- 每个任务完成后运行相关测试（`pytest` / `npm test` / `npm run lint`）

### 3. 任务状态更新
完成任务后，在 `docs/tasks/2026-08-11-audit-task-cards.md` 中更新：
- `Status`：TODO → IN_PROGRESS → DONE / BLOCKED
- 实际修改内容
- 修改文件列表
- 验证结果
- 遗留问题
- 新增任务（如有）

### 4. Git 规范
- 每个任务完成后提交一个 commit
- Commit message 格式：`TASK-xxx: 简短描述`
- 不要一次性提交所有任务的代码

### 5. 验证要求
每个任务必须满足其 Acceptance Criteria 中的所有 Checklist 项：
- [ ] 问题已解决
- [ ] 相关正常/异常路径已验证
- [ ] 未破坏现有功能
- [ ] 必要测试已补充并通过
- [ ] 项目现有 lint / typecheck / test / build 检查通过

## 推荐执行顺序

基线 TASK-001～028 已全部 DONE。当前增量：

### 可并行（无共享写入）
1. **TASK-030** — 套餐拷贝 recommendation_reasons（`combo_builder.py`）
2. **TASK-032** — compose 透传安全变量（`docker-compose.yml` + 部署文档）
3. **TASK-031** — AI/注册文案（前端文案 + README 对应句）
4. **TASK-033** — 账户页删除确认（`AccountPage.tsx`）

### 可与 030 并行但改 recommend.py
5. **TASK-029** — 推荐 API 接线 `profile_assessment`（`recommend.py` + 结果页）

## 重要提醒

1. **不要跳过依赖任务**：TASK-029 依赖 TASK-020 已交付的 `filter_candidate_pool_with_profile`
2. **安全优先**：TASK-032 影响生产 Cookie/代理默认值，默认须 fail-safe
3. **文案合规**：不得把 AI 写成选品/精排，不得承诺首用户管理员
4. **共享文件**：TASK-029 与 TASK-031 都可能改 `ResultPage.tsx`，不要并行写同一文件

## 项目结构速查

```
insurance_recommendation/
├── backend/
│   ├── app/
│   │   ├── api/          # REST API 端点
│   │   ├── engine/       # 推荐引擎（AI/规则/评分/组合）
│   │   ├── models/       # SQLAlchemy 数据模型
│   │   ├── services/     # 业务逻辑层
│   │   ├── crawler/      # 爬虫模块
│   │   ├── data_ingestion/ # 数据采集管道
│   │   ├── dependencies/ # 依赖注入（认证）
│   │   ├── middleware/   # 中间件（限流）
│   │   ├── schemas/      # Pydantic 校验
│   │   └── config.py     # 配置管理
│   ├── main.py           # FastAPI 入口
│   └── tests/            # 后端测试
├── frontend/
│   ├── src/
│   │   ├── api/          # API 客户端
│   │   ├── components/   # 通用组件
│   │   ├── pages/        # 页面组件
│   │   ├── hooks/        # 自定义 Hooks
│   │   ├── types/        # TypeScript 类型
│   │   ├── App.tsx       # 路由配置
│   │   └── main.tsx      # 入口
│   └── package.json
├── docs/
│   └── tasks/
│       └── 2026-08-11-audit-task-cards.md  # 当前执行任务卡
├── docker-compose.yml
└── README.md
```

## 常用命令

```bash
# 后端
cd backend
python -m pytest                    # 运行测试
python -m ruff check .              # Lint 检查
uvicorn backend.main:app --reload   # 启动开发服务器

# 前端
cd frontend
npm install                         # 安装依赖
npm run dev                         # 启动开发服务器
npm run build                       # 构建
npm run lint                        # Lint 检查
npm test                            # 运行测试（如有）
```

## 开始执行

1. 阅读 `docs/tasks/2026-08-11-audit-task-cards.md`（旧 `audit-task-cards.md` 仅为归档）
2. 从 TASK-029～033 开始执行
3. 每个任务完成后更新任务卡状态
4. 遇到问题时，优先检查任务卡中的 Handoff 说明

开始执行任务。
