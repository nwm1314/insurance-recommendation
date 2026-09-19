# 评审修复与优化实施提示词（产品 / 设计 / 开发）

> 使用方式：把本文件整体交给一个**新的执行会话**。前置条件是三视角评审报告已产出——即 `docs/tasks/2026-09-19-three-perspective-review.md`（若不存在，请先按 `2026-09-19-three-perspective-review-prompt.md` 完成评审）。
> 本阶段**要改代码**。请严格按批次顺序执行，不得跳批次。

---

## 1. 你的角色与总目标

你是本仓库的资深实施工程师，具备全栈能力。你要按评审报告的问题清单完成修复与优化，使系统达到"可对外内测"标准。

**产品体验、设计一致性、工程正确性三者都要动**——不允许只修 bug 不修体验，也不允许只美化界面不修数据缺陷。

---

## 2. 仓库事实

- 仓库根目录：`E:\ai_project\insurance_recommendation`（Windows 路径）
- 后端：`backend/app/`（`engine`=推荐引擎，`api`=路由，`crawler` + `data_ingestion`=数据生产，`models`=ORM，`schemas`=Pydantic，`middleware`=限流，`services`=业务逻辑）
- 前端：`frontend/src/`（`pages` / `components` / `api` / `types`）
- 配置：`backend/config/scoring_weights.yaml`、`backend/config/budget_rules.yaml`（由 `backend/app/config.py` 的 `_load_yaml` 加载）
- 数据库迁移：Alembic（`backend/alembic/`），容器入口 `backend/entrypoint.sh` 执行 `alembic upgrade head`
- **迁移门禁**：`backend/app/database.py` 的 `verify_schema_integrity()` 在启动时校验模型与迁移一致——**任何模型字段变更必须配套 Alembic 迁移**，否则启动即失败
- 契约真实来源：`frontend/src/types/index.ts` 与后端 `backend/app/api/recommend.py::_build_response`
- 测试：`backend/tests/`（每个文件自带临时 SQLite `DATABASE_URL`）；`frontend/tests/e2e/`（Playwright）

**测试命令（已验证可用，在仓库根目录执行）**：

```powershell
# 后端全量
./backend/venv/Scripts/python.exe -m pytest backend/tests -q

# 前端构建（含 tsc 类型检查）
cd frontend; npm run build

# E2E（自起真实后端 + vite，产物落 frontend/test-results/ 与 frontend/playwright-report/）
cd frontend; npx playwright test
```

---

## 3. 全局工作规则

1. **顺序执行**：按评审报告建议的批次顺序（P0 → P1 → P2），同一批次内先"数据正确性 / 契约"，后"体验 / 视觉"。
2. **先复现再修**：每个问题动手前必须复现一次，把复现命令与输出记进 handoff。**无法复现的**，写明复现尝试过程，降级为"观察项"，不要凭猜测改代码。
3. **每任务一个 commit**：message 以问题 ID 开头（如 `UX-003: 结果页首屏信息层级重排`），正文说明行为变化与需要语义更新的测试。
4. **每批次结束必须全绿**：`pytest` 全量 + `npm run build` + `playwright` 全量，三者任一为红则不得进入下一批次。
5. **测试纪律**：禁止为凑绿删除测试、跳过用例、削弱断言。若某问题的正确行为与既有测试冲突，**更新测试的断言语义并在 commit 中说明理由**。
6. **前端契约**：响应**新增字段**可以；**删除或改名**必须同步 `frontend/src/types/index.ts` 并在 commit 中说明。
7. **禁止事项**：
   - 不引入新中间件 / 服务（消息队列、微服务、向量库、K8s）；
   - 不做问题清单范围外的重构、改名、风格统一；
   - 不新增依赖（确有必要须先说明理由，并单独成一个 commit）；
   - 不绕过 `verify_schema_integrity`——模型改动必须走 Alembic。
8. **注释**：中文，密度与既有文件一致；只写代码本身表达不了的约束。
9. **每批次结束输出**：改了哪些行为、哪些测试被语义更新、遗留风险、下一批次计划。

---

## 4. 产品 / 设计修复的额外要求

- **UI 改动必须附三档截图证据**：320px / 375px / 1280px，落到 `frontend/test-results/screenshots/`，并确认无文档级横向溢出（`document.scrollWidth <= clientWidth`）。
- **文案改动必须全局检查**：`HomePage`、`ResultPage`、`AccountPage`、`AdminPage`、`LoginPage`、`RegisterPage`、`App.tsx` 页脚、`README.md` 相关段落——避免只改一处造成新的不一致。
- **合规文案**（免责声明、隐私提示、AI 能力表述）：
  - 改动必须在 commit 中单独说明依据；
  - **不得夸大 AI 能力**：`ai_engine` 只在候选池白名单内做选择、排序与解释，不新增产品，UI 与文档不得暗示它能做更多；
  - **不得暗示承保保证**或替代保险公司核保结论；
  - 保费 / 保额数值不得被标注为精确报价，未披露上限的产品必须保留"起 / 以核保为准"标注。
- **优先做"减少认知负担"而不是"增加信息量"**：能删的区块先删，能合并的步骤先合并，能用默认值代替的必填项先给默认值。
- **健康信息属敏感个人信息**：任何触碰健康编码、保存画像、推荐记录落库的改动，都要顺带检查告知—同意链路与最小化采集，不要只从功能角度改。

---

## 5. 技术修复的高频陷阱（本项目特别容易反复）

1. **单位口径三层一致**：`sum_insured_*` 存储单位 = **万**；`premium_*` / `deductible` 单位 = **元**。每次触碰金额字段，都要核对 **提取层 → 存储层 → 引擎层 → 展示层** 四层一致（`llm_extractor.py` / `product_schema.py` / `scoring.py` / `ProductCard.tsx`）。
2. **别信 mock 型 E2E**：`frontend/tests/e2e/mobile-flow.spec.ts` 用 `page.route` 拦截 `/api/recommend`，它证明的是"给定响应能渲染"，不是"流程可用"。修复涉及关键路径时，必须补真实后端的链路覆盖（参照 `recommend-flow.spec.ts` 的写法）。
3. **AI 降级语义**：LLM 异常时切换极速模式是设计行为，不要"修"成抛错。但要确认前端提示清晰、不误导。
4. **Redis 故障 fail-open**：限流与 AI 配额在 Redis 不可用时放行是既定策略。改这块要保证降级路径不引入新的单点。
5. **迁移门禁**：改了 `backend/app/models/` 就必须新增 Alembic 迁移，否则应用启动即 `verify_schema_integrity` 失败——本地跑测试时旧库需先 `alembic upgrade head`。
6. **历史兼容字段**：`frontend/src/types/index.ts` 中带注释的"历史记录可能缺省"字段是真实兼容需求，不要顺手改成必填导致旧记录渲染崩溃。

---

## 6. 执行流程

### 阶段 0：准备工作

1. 读 `docs/tasks/2026-09-19-three-perspective-review.md`，确认问题清单；
2. `git status` 确认工作区干净，从 `master` 新建分支 `codex/three-perspective-remediation`；
3. 复现基线：跑一次三命令，把当前绿/红状态记录进 handoff（作为对照基线）；
4. 把问题清单拆成任务卡写入 `docs/tasks/2026-09-19-remediation-cards.md`，格式：

   | ID | 标题 | 视角 | 严重度 | 批次 | 状态 | 验收标准 | 验证命令 |
   | -- | ---- | ---- | ------ | ---- | ---- | -------- | -------- |

5. 按批次顺序排列，标注相互依赖。

### 阶段 1..N：逐批次修复

每张任务卡的执行流程：

1. 读相关代码确认现状（报告行号可能漂移，以实际代码为准）；
2. 复现问题，记录命令与输出；
3. 实现修复；
4. **新增回归测试**（能覆盖该问题的自动化用例；UI 问题至少补 E2E 或截图证据）；
5. 跑全量：`pytest` + `npm run build` + `playwright`；
6. 一个 commit（message 以问题 ID 开头）；
7. 更新任务卡状态与 handoff 条目。

### 收尾阶段

1. 全量三命令最后一次跑，贴真实输出；
2. 产出 `docs/tasks/2026-09-19-remediation-handoff.md`，逐条记录：

   | ID | 结论 | 变更文件 | 验证命令与输出摘要 | 遗留项 |
   | -- | ---- | -------- | ------------------ | ------ |

   结论只能取三种值：**已修复** / **部分修复（说明剩余）** / **不修（说明原因）**。不允许出现"应该没问题"这类表述。
3. 列出所有**未闭环**的问题与原因；
4. 汇总需要人类拍板的产品决策（见下节）。

---

## 7. 遇到需要产品决策的问题怎么办

以下类型的问题**不要自己拍板**，记录到 `docs/tasks/2026-09-19-open-questions.md` 并继续做其他任务：

- 是否去掉某个问卷字段 / 某个结果页区块；
- 三套套餐命名、AI / 极速模式开关的取舍；
- 免责声明与隐私提示的具体措辞；
- 产品池数据来源策略（新增 / 停用某数据源）；
- 是否引入真实投保跳转或留资能力。

格式：

```markdown
## OPEN-001：<问题>
- 背景与证据：
- 可选方案（含各自代价）：
- 我的建议与理由：
- 需要谁决定：
```

---

## 8. 完成标准

全部满足才算完成：

- [ ] 评审报告中所有 P0 项闭环（已修复或明确论证不需要修）；
- [ ] P1 项闭环或降级为有记录的遗留项并说明原因；
- [ ] `pytest` 全量绿（无 skip 新增、无断言削弱）；
- [ ] `npm run build` 通过；
- [ ] `playwright` 全量绿；
- [ ] 每个修复都有对应的回归测试或截图证据；
- [ ] `docs/tasks/2026-09-19-remediation-handoff.md` 完整，无未验证结论；
- [ ] `docs/tasks/2026-09-19-remediation-cards.md` 状态与实际一致；
- [ ] 所有产品决策型问题已记录到 open-questions；
- [ ] 未引入新依赖 / 新中间件 / 范围外重构。
