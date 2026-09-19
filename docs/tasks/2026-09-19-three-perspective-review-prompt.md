# 三视角全面评审提示词（产品 / 设计 / 开发）

> 使用方式：把本文件整体交给一个**新的执行会话**。该会话本轮**只读**——可以读代码、跑测试、起服务、截图，但不得修改任何既有文件，只产出评审报告。
> 评审完成后，由执行会话或另一个会话按评审报告执行修复；修复阶段请使用同目录的 `2026-09-19-remediation-prompt.md`。

---

## 1. 你的角色

你是本次评审的负责人，同时具备三个专业身份：

- **资深保险科技产品经理**——关心产品是否真的解决问题、用户能否走完并执行下一步；
- **B 端 / C 端体验设计师**——关心信息层级、一致性、可及性、信任设计；
- **全栈技术负责人**——关心数据正确性、契约一致性、安全、性能、测试有效性。

三个视角都要产出可执行的修复清单，不允许只做其中一个。

---

## 2. 任务

对 `E:\ai_project\insurance_recommendation` 做一次全面的产品 / 设计 / 开发三视角评审，产出可执行的修复清单。

**本轮只读**：可以读代码、跑测试、启动服务、截图取证，但**不得修改任何既有文件**，唯一允许的写入是最终产出的评审报告。

---

## 3. 项目事实（先读这些，再下结论）

### 3.1 技术栈与规模

- 前端：React 18 + TypeScript + Ant Design 5 + Vite
- 后端：FastAPI + SQLAlchemy + Pydantic + APScheduler
- 存储：SQLite（开发期）+ Redis（限流 / AI 配额 / 缓存）
- 采集：Playwright + BeautifulSoup4 + OpenAI 兼容 LLM 结构化提取 + Pydantic 校验
- 规模：`backend/app` 约 6.4k 行 Python；`frontend/src` 约 3k 行 TS/TSX；`backend/tests` 208+ 用例；`frontend/tests/e2e` 13 个 spec

### 3.2 必读文档

- `README.md`
- `develop_guidence.md`
- `docs/tasks/2026-08-11-audit-task-cards.md`
- `docs/tasks/2026-08-11-comprehensive-project-review.md`
- `docs/2026-09-14-review-remediation-implementation-prompt.md`
- `docs/superpowers/specs/2026-05-24-insurance-recommendation-design.md`
- `docs/superpowers/plans/2026-05-24-insurance-recommendation-plan.md`

### 3.3 关键代码入口

- 推荐引擎：`backend/app/engine/{rule_engine,scoring,budget,combo_builder,ai_engine,health,occupation,fallback,llm_safety}.py`
- API：`backend/app/api/{recommend,products,auth,admin,ingestion}.py`
- 配置：`backend/config/scoring_weights.yaml`、`backend/config/budget_rules.yaml`
- 采集与发布：`backend/app/crawler/`、`backend/app/data_ingestion/`
- 前端页面：`frontend/src/pages/{HomePage,ResultPage,AccountPage,AdminPage,LoginPage,RegisterPage}.tsx`
- 前端基础：`frontend/src/App.tsx`、`frontend/src/api/client.ts`、`frontend/src/mobile-responsive.css`
- 契约真实来源：`frontend/src/types/index.ts` 与 `backend/app/api/recommend.py` 的 `_build_response`

### 3.4 重要前提

- **历史结论不采信**：既有任务卡（`docs/tasks/2026-08-11-audit-task-cards.md`）全部标记 DONE，其中多条写"已验证通过"。你必须自己复现。凡引用既有结论，必须标注"未复现"。
- **代码是唯一事实**：文档与注释可能过期；行号可能漂移。任何结论以当前代码与实测输出为准。

---

## 4. 必须先建立的可验证基线（不得跳过）

在仓库根目录执行并记录**真实输出**：

```powershell
# 后端全量测试
./backend/venv/Scripts/python.exe -m pytest backend/tests -q

# 前端构建（含 tsc 类型检查）
cd frontend; npm run build

# E2E（会自起真实后端 + vite dev server，产物落 frontend/test-results/、frontend/playwright-report/）
cd frontend; npx playwright test
```

另外：

- 启动后端（`python -m uvicorn main:app --reload`，工作目录 `backend/`）与前端（`npm run dev`），确认可访问；
- 用 curl / Playwright 抓取关键页面截图与接口响应；
- 记录环境（Python 版本、Node 版本、OS）与任何失败/跳过的用例。

**判定标准**：任何"我判断""应该没问题""按设计应该"的结论都不算证据。没有真实输出的条目一律归入"待验证假设"。

---

## 5. 视角一：产品经理

对每一项给出 **现状 → 证据（文件:行 / 接口响应 / 截图路径）→ 影响 → 建议**：

1. **核心价值主张是否闭环**：用户填完问卷，是否真的拿到"可以拿去买"的方案？用户的下一步动作是什么（跳转投保页 / 咨询 / 留资）——目前是否断链？推荐结果里的 `source_url` 跳转体验如何？
2. **决策可信度**：8 维评分的权重来源与可解释性（`backend/config/scoring_weights.yaml`）；用户能否看懂"为什么推荐它"；保费区间、保额单位（万 / 元）、`premium_basis_note` 等口径在 UI 上是否自相矛盾；"保费倒挂预警"是否真的触发过。
3. **输入负担与完成率**：`HomePage` 问卷 4 步、多字段（含 70+ 健康编码）。风险集中在哪一步？是否存在"我不知道填什么"的死角（社保身份、职业等级、已有保单保额）？必填项是否真的必要？
4. **兜底与失败体验**：候选池为空、全部被一票否决、预算过低、AI 降级、LLM 超时——用户看到什么？是否给出可行动的出路而不是空白页或技术错误？
5. **商业与合规**：免责声明的位置与措辞；数据来源可信度标注（`official` / `aggregator` / `third_party`）是否被用户理解；健康信息采集的告知—同意链路是否完整（对照《个人信息保护法》敏感个人信息要求，只做产品级判断，不提供法律意见）。
6. **产品池真实性与新鲜度**：`data_stale`、`last_verified_at` 的实际生效情况；当前库里真实产品占比（是否仍以种子演示数据为主，`SEED_DEMO_PRODUCTS` 的行为）。

---

## 6. 视角二：设计师（UX / UI）

1. **关键旅程走查**：实际走完五条旅程并逐步截图，覆盖桌面 1280、平板 768、移动 375 / 320：
   1) 首次填问卷 → 2) 查看结果 → 3) 横向对比 → 4) 保存 / 复用画像 → 5) 登录后查看历史。
   标出每一步的认知负担、返工点、信息缺失点。
2. **信息层级**：结果页（`frontend/src/pages/ResultPage.tsx`）中"预算分析 / 建议保额 / 三套方案 / 横向对比 / 画像评估 / 免责声明"的优先级是否合理；首屏是否被次要信息占据。
3. **一致性**：AntD 默认视觉与项目自定义（`frontend/src/mobile-responsive.css`）是否冲突；三套套餐命名（"极致性价比 / 全面保障 / 尊享无忧"）是否会让普通人误以为"贵的更好"。
4. **可及性**：对比度（**用工具实测，不要目测**）、字号、键盘可达性、focus 管理、antd locale、加载态 / 空状态 / 错误态、错误提示措辞（是否暴露技术术语或英文残留）。
5. **信任设计**：AI / 极速模式开关（`EngineSwitch`）是否让用户明白差异；AI 降级提示是否让用户困惑"我拿到的到底是不是 AI 结果"。
6. **移动端**：320px 下宽表滚动、抽屉宽度、按钮换行是否真的可用——**用实际截图判断，不要只看 CSS**。

建议使用 Playwright 批量截图，统一落到 `frontend/test-results/screenshots/review/` 并在报告中引用相对路径。

---

## 7. 视角三：开发

1. **架构与边界**：规则引擎 / 评分 / 组包 / AI 的职责是否清晰；`backend/app/api/recommend.py`（约 470 行）与 `backend/app/engine/combo_builder.py`（约 471 行）的复杂度是否已到必须拆分的程度。
2. **数据正确性**：单位规范（`sum_insured_*` 存储=万，`premium_*` / `deductible`=元）在提取层 / 存储层 / 引擎层 / 展示层四层是否真的统一；LLM 提取默认值、`health_requirements` 结构化、自动发布门禁是否仍有漏洞——**请构造反例实证，不要读 prompt 就下结论**。
3. **契约一致性**：`frontend/src/types/index.ts` 与后端 `_build_response` 的字典形状逐字段对齐（含可选字段与历史兼容字段）；是否存在后端返回但前端未消费、或前端期待但后端不返回的字段。
4. **安全**：认证 / Cookie / CORS / 限流 / SSRF / RBAC / 审计的当前实现复核（对照 `backend/tests/test_ops002_security.py`、`test_ssrf_protection.py`、`test_cors_validation.py`）；推荐记录加密（`RECORD_ENCRYPTION_KEY`）与保留策略（`RECORD_RETENTION_DAYS`，README 称本期不实现）的实际状态。
5. **性能与成本**：推荐接口 P50 / P95 耗时（极速模式 vs AI 模式）；AI 每日配额与短缓存的实际行为；候选池 `joinedload`；前端 bundle 体积与懒加载效果（跑 `npm run build` 看真实产物，不要只看警告）。
6. **可靠性**：Redis 故障、LLM 超时、数据库不可用路径的实际行为（是否真的 fail-open / 降级）；APScheduler 单副本约束是否有运行时校验（`SCHEDULER_DISABLED`）。
7. **测试有效性**：区分"真实验证"与"mock 自证"。
   - 重点检查 `frontend/tests/e2e/mobile-flow.spec.ts` 这类用 `page.route` 拦截 `/api/recommend` 的用例——它们证明的是"给定响应能渲染"，**不是**"流程可用"。
   - 列出**看起来绿但没验证真实行为**的用例、断言过弱的用例、以及缺失的用例（如评分权重回归、空候选池、并发配额、单位口径回归）。
8. **工程卫生与交付**：`frontend/.npmcache/` 是否入库、`.gitignore` 中 `*.png` 与 E2E 截图产物的关系、后端无 lint / 无静态类型检查、CI 覆盖范围（当前仅 `.github/workflows/e2e.yml`）、`docker-compose.yml` 与 `Dockerfile` 的配置正确性。

---

## 8. 输出要求

产出报告：`docs/tasks/2026-09-19-three-perspective-review.md`，包含以下章节：

1. **执行摘要**：5 条以内最重要结论。
2. **基线证据**：测试 / 构建 / E2E 的真实命令与输出摘要（含失败项与跳过项），以及环境信息。
3. **三视角问题清单**：每条格式为

   | ID | 视角 | 标题 | 严重度 | 证据 | 影响 | 建议修复方向 | 预估工作量 |
   | -- | ---- | ---- | ------ | ---- | ---- | ------------ | ---------- |

   - ID 前缀：`PROD-` / `UX-` / `DEV-`
   - 严重度：P0（数据错误 / 安全 / 阻断主流程）、P1（功能或体验明显受损）、P2（体验瑕疵 / 工程债）、P3（优化项）
   - **每条必须有证据**（文件:行 / 命令输出片段 / 截图相对路径）；无证据的写进"待验证假设"单独成节，不要混进问题清单。
4. **与既有文档的差异**：哪些历史结论被推翻、哪些仍未复现、哪些确认成立。
5. **架构级建议**：只列真正值得做的（模块拆分、契约单一来源、CI 补齐等），并说明**不做什么以及为什么**。
6. **修复顺序建议**：按依赖关系排出批次（如批次 A = 数据正确性，批次 B = 契约与测试有效性，批次 C = 体验与视觉），标注批次间的依赖。

---

## 9. 禁止事项

- 不修改任何既有代码 / 配置 / 文档（唯一例外：新建上述评审报告）。
- 不为了让测试变绿而改动测试、跳过用例或削弱断言。
- 不引入新依赖、新中间件、新框架。
- 不给出无证据的结论；不确定就明确写"待验证"。
- 不做超出评审范围的代码重构——发现的问题写进报告，不现场改。
