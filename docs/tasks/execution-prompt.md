# 保险推荐项目 — 任务卡执行提示词

> 复制以下提示词到新 Codex 会话即可开始执行任务

> 本提示词已于 2026-08-12 与当前基线同步；旧版 `audit-task-cards.md` 仅为归档，不作执行依据。

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

### 第一波（立即执行，无依赖）
1. **TASK-008** — SSRF 防护（安全优先，P1）
2. **TASK-009** — CORS 校验（低风险快速修复）
3. **TASK-002** — 空壳端点清理

### 第二波（核心体验修复）
4. **TASK-001** — 推荐结果持久化
5. **TASK-016** — 定价准确性优化（P1，产品信任度）
6. **TASK-007** — Token 迁移（高风险，需充分测试）
7. **TASK-012** — SSE 死代码清理

### 第三波（功能完善）
8. **TASK-003** — 历史详情 + 画像回填（依赖 TASK-001）
9. **TASK-015** — 移动端适配
10. **TASK-005** — 产品管理 CRUD
11. **TASK-006** — 平台管理 + 手动录入
12. **TASK-010** — Schema 白名单
13. **TASK-011** — page_type 枚举

### 第四波（质量与性能）
14. **TASK-004** — 画像/历史管理（依赖 TASK-003）
15. **TASK-013** — 产品列表分页
16. **TASK-014** — 前端 E2E 测试

## 重要提醒

1. **不要跳过依赖任务**：TASK-003 依赖 TASK-001，TASK-004 依赖 TASK-003
2. **安全优先**：SECURITY 类型任务优先处理
3. **高风险任务谨慎**：TASK-007（Token 迁移）需充分测试所有认证流程
4. **移动端适配**：TASK-015 需在多种屏幕尺寸下验证
5. **定价准确性**：TASK-016 涉及产品模型和多个前端组件，需全面测试

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
│       └── audit-task-cards.md  # 任务卡文件
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

1. 阅读 `docs/tasks/audit-task-cards.md`
2. 从第一波任务开始执行
3. 每个任务完成后更新任务卡状态
4. 遇到问题时，优先检查任务卡中的 Handoff 说明

开始执行任务。
