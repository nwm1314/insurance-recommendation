# 保险推荐项目全面审查报告

> 历史审查快照（2026-08-11）。本报告记录任务执行前的证据，不代表当前工作区状态；当前能力与验收以 `docs/tasks/2026-08-11-audit-task-cards.md` 及代码/测试为准。

**审查日期：** 2026-08-11
**审查范围：** 产品设计、数据采集与新鲜度、推荐引擎、账号与安全、后台产品管理、前端与移动端、测试、文档、Git 与部署一致性。
**审查方式：** 仓库代码走读、Git 状态与历史核验、SQLite 数据检查、后端测试、前端生产构建，以及针对数据库模式和 SSRF 校验的只读复现。

## 执行结论

当前工作区不应作为生产级保险推荐或数据采集服务发布。后端测试与前端构建通过，但这些检查未覆盖现有数据库升级、产品 CRUD、真实抓取发布闭环、历史结果恢复和端到端用户流程。

## 已执行验证

- `cd backend && python -m pytest -q`：**49 passed**。
- `cd frontend && npm run build`：通过；Vite 提示单一压缩后 chunk 为 **1,314.50 kB**（gzip **414.81 kB**）。
- `cd frontend && npm run test:e2e`：本机两次在 120 秒内未完成；自动启动的 Vite 未在预期端口就绪，因此不能以本次审查证明 E2E 可复现通过。
- SQLite `data/insurance.db`：产品数 **165**；`created_at` / `updated_at` 均为 **2026-05-24**；`source_pages`、`raw_documents`、`product_review_tasks` 均为 **0**。
- 以当前模型查询该 SQLite 数据库：可复现 `sqlite3.OperationalError: no such column: products.deductible`。
- SSRF 校验实测接受 `100.64.0.1`、`198.18.0.1`、`192.0.0.1` 与 `[::ffff:127.0.0.1]`。

## 主要发现

### P0：数据库模式与代码不兼容

`backend/app/models/product.py` 已定义 `deductible`，但 `backend/alembic/versions/` 中没有创建或新增该列的迁移。`Base.metadata.create_all()` 不会修改已存在的表。现有数据库的任何 ORM 产品查询均会失败。相关任务：**TASK-017**。

### P0：后台产品 CRUD 不可用且不完整

`backend/app/api/products.py` 中 `ProductCreate.type` 和 `ProductUpdate.type` 的枚举值为 `"???"`，而 `AdminPage.tsx` 提交中文险种，导致请求校验失败。后台表单没有 Rule 或 Benefit 编辑项；服务层允许创建无 Rule 的产品，但推荐引擎强制 join Rule，因此此类产品不会进入候选池。相关任务：**TASK-005**。

### P1：产品数据没有新鲜度或发布闭环

调度器只启动 APScheduler，未注册任何任务。抓取执行每次都归档并创建审核任务，未使用 MD5 作增量比较，也未调用停售检测。审核通过只写 `ProductVersion`，不会更新 `Product`、`Rule` 或 `Benefit`。抓取数据尚未产生，现有推荐目录实际为 2026-05-24 种子数据。相关任务：**TASK-018**、**TASK-019**。

### P1：SSRF 防护覆盖不足

现有网络黑名单不覆盖多个非公网地址段，也未对 Playwright 重定向目标进行逐跳校验。`robots_url` 可由管理端配置，并使用 `urlopen()` 抓取，完全绕开 URL 校验。相关任务：**TASK-008**。

### P1：权限与边界安全设计存在高风险缺口

空用户库的第一个公开注册用户自动得到 admin 角色。限流与审计无条件相信 `X-Forwarded-For`；Cookie 登录的请求没有被解析出用户 ID，故用户级限流未生效。Cookie 默认非 Secure，环境模板没有对应生产配置；CORS 仍允许 `*`。相关任务：**TASK-009**、**TASK-022**、**TASK-023**。

### P1：推荐不能证明契合度或真实性价比

`existing_coverage` 和 `preferred_type` 被接收但未用于规则引擎；前端列出大量健康项，后端只识别少量宽泛别名，未识别项会被静默忽略。候选准入和套餐预算以最低保费计算，最高保费可使实际方案超预算。AI 路径仅解释规则套餐，系统提示明确禁止其选品或替换。相关任务：**TASK-016**、**TASK-020**。

### P1：账户旅程与任务卡不一致

账户页的历史链接只写入 `recordId` 查询参数，但结果页未读取该参数；画像加载仅传路由 state，问卷未回填；没有保存画像的前端入口。相关任务：**TASK-001**、**TASK-003**。

### P2：移动端、测试和性能仍不达标

响应式样式仅覆盖基础布局，关键结果页仍存在固定三列布局，后台产品抽屉固定 600px。E2E 仅覆盖静态文案与未登录跳转，且本次无法复现完成。前端生产包超出建议阈值。相关任务：**TASK-014**、**TASK-015**、**TASK-026**。

### P2：文档、任务卡和 Git 基线失真

README、设计与开发文档仍宣称 SSE、Instructor、周度 MD5 巡检、停售自动下架和抓取更新主数据；当前实现不具备这些能力或已删除对应代码。旧任务卡不是 UTF-8，且将多项未实现能力写为 DONE。工作区有大范围已修改和未跟踪文件，任务卡涉及的改动多数不在提交历史中。相关任务：**TASK-024**、**TASK-025**。

## 任务映射

完整、可独立接手的任务与依赖关系见 [2026-08-11-audit-task-cards.md](2026-08-11-audit-task-cards.md)。该文件为本报告的执行基线；执行前仍必须以实际 Git 状态与代码为准。
