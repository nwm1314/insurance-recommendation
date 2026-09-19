# 修复交付记录（2026-09-19 三视角评审 → 修复）

> 分支：`codex/three-perspective-remediation`
> 起点 commit：`20f8fd5`（master）
> 终态 commit：`2a1661b`
> 执行方式：按 `2026-09-19-autonomous-loop-prompt.md` 多轮推进（评审 → 拆卡 → 逐卡修复 → 收尾）
> 本文档记录逐条结论、变更文件、验证命令与真实输出摘要、遗留项。

---

## 1. 交付总览

| 项 | 修复前（基线实测） | 修复后（终态实测） |
| -- | ---- | ---- |
| `pytest backend/tests -q` | **10 failed / 270 passed**（Redis 干净时）<br>**38 failed / 242 passed**（Redis 脏时） | **301 passed / 0 failed** |
| `cd frontend; npm run build` | 通过（exit 0） | 通过（exit 0，11.80s） |
| `cd frontend; npx playwright test` | **6 failed / 29 passed** | **37 passed / 0 failed** |

**完成标准核对**

- [x] 评审报告中所有 P0 项闭环（4 项，含修复中新发现的 1 项）
- [x] P1 项闭环或降级为有记录的遗留项（7 项：6 项闭环，PROD-001 已记录为待人类决策）
- [x] `pytest` 全量绿（301 passed；无新增 skip、无断言削弱）
- [x] `npm run build` 通过
- [x] `playwright` 全量绿（37 passed）
- [x] 每个修复都有对应的回归测试或截图证据
- [x] 本文件完整，无未验证结论（未验证项已明确标注）
- [x] `2026-09-19-remediation-cards.md` 状态与实际一致
- [x] 所有产品决策型问题已记录到 `2026-09-19-open-questions.md`（5 项）
- [x] 未引入新依赖 / 新中间件 / 范围外重构

**commit 列表（7 个，每卡一个主题）**

| commit | message |
| ---- | ---- |
| `2ad49d9` | DEV-001/DEV-002/DEV-007/DEV-008: isolate test Redis and fix cross-test DB/shared-state leakage |
| `6ebc75b` | DEV-003/UX-002: fix E2E questionnaire step assertions (6 always-failing tests) |
| `e30963b` | DEV-005/DEV-006: workspace hygiene, test docs, and money-unit consistency guard |
| `006ae1c` | docs: add 2026-09-19 three-perspective review, remediation cards, and open questions |
| `ec712c0` | DEV-004: surface AI cache provenance instead of a bare "AI 精排模式" |
| `14d62bf` | PROD-002: make the plaintext-record risk actionable for production deployment |
| `2a1661b` | PROD-003: prove product freshness labelling actually works (closes a review assumption) |

---

## 2. 逐条结论

| ID | 结论 | 变更文件 | 验证命令与输出摘要 | 遗留项 |
| -- | ---- | ---- | ---- | ---- |
| **DEV-001** | **已修复** | `backend/tests/conftest.py`（新增）<br>`backend/tests/test_redis_test_isolation.py`（新增） | 修复前 `pytest -q` → `38 failed, 242 passed`（未清 Redis）/ `10 failed, 270 passed`（清后）。根因：`rate_limit:user:day:1 = 211/300` 跨运行累积。修复后连续两次 → `301 passed`、`301 passed`；真实 Redis 键数运行前后均为 0 | 无 |
| **DEV-002** | **已修复** | 同上 | `ai_cache:*` 脏键（TTL 3554）使 AI 降级用例恒失败（`assert 'ai' == 'degraded'`）。conftest 隔离后单跑与全量均通过；新增缓存语义回归 2 条 | 无 |
| **DEV-007** | **已修复**（修复中新发现） | `backend/tests/test_product_pool_pipeline.py` | `UNIQUE constraint failed: source_platforms.name`；根因是 `_clean_db` 漏清 `SourcePlatform`，同文件内第二次插入"中民保险网"冲突。已将 `SourcePlatform` 加入清理列表 | 无 |
| **DEV-008** | **已修复**（修复中新发现） | `backend/tests/test_product_draft_schema.py`<br>`backend/tests/conftest.py` | `verify_schema_integrity` 导入期报错（9 个文件 collection error）。根因两层：测试文件缺残留库删除 + conftest 导入期 import backend 使 DB engine 绑到开发库。修复后 `data/insurance.db` 全量 pytest 前后 products 均为 0（不再污染） | 无 |
| **DEV-003** | **已修复** | `frontend/tests/e2e/helpers.ts`<br>`frontend/tests/e2e/mobile-flow.spec.ts`<br>`frontend/tests/e2e/home.spec.ts` | 修复前 `npx playwright test` → `6 failed, 29 passed`。根因：第 2 步职业字段未填导致校验失败、步骤不前进（实测报错"请手动选择职业类别，或填写职业名称"），而 `text=健康状态` 命中的 label 处于 `display:none` 容器（实测宽高 0）。修复后 `playwright` → `37 passed` | 无 |
| **UX-002** | **已修复** | 同 DEV-003 | 修复后 `expectNoHorizontalOverflow` 首次真正执行：320/375/1280 三档实测 `docOverflow=0px bodyOverflow=0px`；产出 9 张截图（`frontend/test-results/screenshots/{result,account,admin}-{320px,375px,desktop}.png`）。断言敏感性验证：注入 1200px 元素后 `before=0px → after=880px` | 无 |
| **UX-001** | **已闭环（判定为非 UI 缺陷）** | 无需改 UI | 评审时实测 label 宽高为 0，本轮定位为**在步骤隐藏时测量**所致（`HomePage.tsx:450` 的 `display:none`）。步骤可见时 label 与单选项正常渲染（实测 144×32 / 200×32 / 211×32）。故不另开 UI 修复卡 | 无 |
| **DEV-005** | **已修复** | `.gitignore`<br>`README.md`<br>（删除遗留文件） | 清理 `_audit_scratch/`、`_baseline_*.txt`、`frontend/_shots.cjs`；`.gitignore` 补入临时产物模式；README 新增「运行测试」章节（含端口占用处置与迁移门禁排障）。验证：`git status --short` 仅剩预期文档 | 无 |
| **DEV-006** | **已修复** | `frontend/src/types/index.ts`<br>`backend/tests/test_money_unit_consistency.py`（新增） | 补齐三个同族金额字段的单位注释（`ProductItem.sum_insured`=万、`ExistingPolicy.sum_insured`=元、`sum_insured_advice.*`=元）。新增 4 条回归把评审的"四层单位是否统一"从待验证假设变为已证结论；变异验证：保额改为 0.04 后立即 `assert 0.04 == 400` 失败 | 无 |
| **DEV-004** | **已修复** | `frontend/src/types/index.ts`<br>`frontend/src/pages/ResultPage.tsx`<br>`backend/tests/test_stage3_recommendation.py`<br>`frontend/tests/e2e/mobile-flow.spec.ts` | 缓存命中时标签改为"AI 精排模式（缓存结果）"+ Tooltip 说明；补声明 `ai_from_cache`（此前后端返回但前端未声明未消费）。新增后端回归 2 条 + E2E 2 条；变异验证：还原旧标签后缓存用例立即失败。**未改变降级语义**（LLM 失败仍降级） | 无 |
| **PROD-002** | **已修复** | `backend/main.py`<br>`backend/tests/test_ops002_security.py`<br>`docs/docker-deployment.md`<br>`README.md` | 部署文档此前**完全没有** `RECORD_ENCRYPTION_KEY` 章节；现新增「推荐记录加密」章节（生成命令 + 启动校验 + 换钥风险）。`APP_ENV=production` 未配置时升级为 `logger.error`；非生产保持 warning。新增回归 3 条；变异验证有效。**未改变 fail-open**（不拒绝启动） | 无 |
| **PROD-003** | **已闭环** | `backend/tests/test_product_freshness.py`（新增） | 评审列为待验证假设；本轮反例实证 `data_stale` 真实生效（从未复核 → True；超阈值 → True；刚复核 → False；恰好 90 天 → False）。变异验证：强制 `stale=False` 后用例立即失败 | 无 |
| **PROD-001** | **不修（需人类决策）** | 无 | 结果页缺少投保跳转/留资入口，核心价值链路止于展示。属提示词 §7 明令"不自己拍板"的产品决策，已记入 `open-questions.md` **OPEN-001**，含 4 个可选方案与各自代价 | 待产品负责人决策 |

---

## 3. 未闭环项与原因

| 项 | 状态 | 原因 |
| -- | ---- | ---- |
| **PROD-001** | ⛔ 阻塞于人类决策 | "是否引入真实投保跳转 / 留资能力"属产品决策，提示词 §7 明确不得自行拍板。已记入 `open-questions.md` OPEN-001，含建议方案与代价分析。**此为唯一未闭环项，且不是技术阻塞。** |
| OPEN-003（套餐命名） | 待决策 | 是否调整"极致性价比 / 全面保障 / 尊享无忧"命名，需产品判断；评审未取证用户影响，故不擅自改文案 |
| OPEN-002（内测加密策略） | 待确认 | 已按建议实现（PROD-002），仅需产品/运维确认"内测即强制配置"的策略 |

**无技术性未闭环项。** 评审报告 §4「待验证假设」中的 7 条，本轮已闭环 2 条（产品新鲜度、四层单位一致性），其余 5 条说明如下：

| 待验证假设 | 本轮处理 |
| ---- | ---- |
| `data_stale` / `last_verified_at` 生效情况 | ✅ 已闭环（PROD-003，反例实证） |
| 四层单位口径是否真的统一 | ✅ 已闭环（DEV-006，反例实证） |
| 保费区间 / `premium_basis_note` 在 UI 是否自相矛盾 | 未验证 —— 未逐字段比对展示层，无证据，**不编造结论** |
| "保费倒挂预警"是否真的触发过 | 未验证 —— 未构造触发用例 |
| 推荐接口 P50 / P95 耗时 | 未验证 —— 未做压测 |
| 对比度是否达标 | 未验证 —— 未跑对比度工具（提示词要求工具实测，未做） |
| `frontend/.npmcache/` 是否入库 | 已确认 `.gitignore` 含该条目；历史成因未考证 |

上述 5 条**不影响 P0/P1 闭环**，属 P2/P3 优化项；如需闭环建议另开专项卡片。

---

## 4. 环境与可复现性

| 项 | 值 |
| -- | -- |
| OS | Windows 10 (NT 10.0.19045.0) |
| Python | 3.12.10（`backend/venv`） |
| Node / npm | v24.15.0 / 11.12.1 |
| Redis | 本机 6379（**pytest 已完全隔离，不再读写真实 Redis**） |

**复现三条命令**（仓库根目录）：

```powershell
./backend/venv/Scripts/python.exe -m pytest backend/tests -q      # 301 passed
cd frontend; npm run build                                        # exit 0
cd frontend; npx playwright test                                  # 37 passed
```

**执行期遇到的两个环境陷阱（已在 README「运行测试」章节记录）**：

1. E2E 端口 3000/8000 被残留 dev server 占用时，Playwright 因 `reuseExistingServer: false`
   直接失败。处置命令已写入 README。
2. 本地库停留在旧 Alembic 版本时，启动期 `verify_schema_integrity()` 会报
   `Database schema is at migration ... but the current Alembic head is ...`。
   处置命令（`alembic upgrade head`）已写入 README。本轮已将本机陈旧
   `data/insurance.db` 从 `20260816_0001` 升级到 `20260914_0002`。

---

## 5. 需要人类拍板的产品决策

汇总见 `docs/tasks/2026-09-19-open-questions.md`，共 5 项：

| ID | 问题 | 阻塞任务 | 状态 |
| -- | ---- | ---- | ---- |
| **OPEN-001** | 是否引入真实投保跳转 / 留资能力 | PROD-001 | **待决策（唯一阻塞项）** |
| OPEN-002 | 健康信息明文落库能否进入对外内测 | PROD-002 | 待确认（已按建议实现） |
| OPEN-003 | 三套套餐命名是否调整 | 无 | 待决策 |
| OPEN-004 | `data_stale` 是否本期闭环 | PROD-003 | 已按建议完成，待确认优先级 |
| OPEN-005 | 是否新增 `backend/tests/conftest.py` | DEV-001/002 | 已按建议完成，待确认 |

---

## 6. 遗留风险

1. **PROD-001 未闭环** —— 用户拿到方案后无站内下一步动作，转化链路仍断。这是产品决策项，非工程缺陷；在决策前，建议至少确认结果页外链（`source_url`）跳转体验与"投保需以保险公司核保结论为准"的提示是否足够清晰。
2. **`npm run build` 主 chunk 470.47 kB（gzip 153.99 kB）** —— 已接近 Vite 默认告警线。分包实际生效（ResultPage/HomePage/Table/react-vendor 独立），本轮**未做**进一步拆包（属范围外优化）。
3. **测试仍共用同一个 Redis 概念** —— conftest 用进程内 `FakeRedis` 解决；若未来新增第四个 Redis 入口，需同步加入 `_install_fake_redis()`，`test_redis_test_isolation.py` 会给出失败信号，但仍需人工补充替换点。
4. **各测试文件的 `DATABASE_URL` 仍靠 `setdefault` 竞逐** —— 全量运行时会共用一个库。本轮已让新增测试自给自足（自建 Rule/Benefit），但这是既有的架构性脆弱点，未在本期范围内重构。
5. **评审报告 §4 的 5 条待验证假设未闭环** —— 已在第 3 节逐条列明，不影响 P0/P1 判定。

---

## 7. 无未验证结论声明

本文件所有"已修复 / 已闭环"结论均附**真实命令输出**（见第 2 节各行与各 commit message）。
所有关键修复均做了**变异验证**（人为破坏修复点后确认回归测试确实失败），以证明测试非空转：

| 修复 | 变异验证结果 |
| ---- | ---- |
| DEV-001/002（Redis 隔离） | 注释掉安装逻辑 → 3 failed，并打印泄漏的真实 `redis.client.Redis(...)` |
| DEV-003（E2E 断言） | 修复前 6 failed（真实基线，无需变异） |
| DEV-006（单位口径） | 保额改为 0.04 → `assert 0.04 == 400` 失败 |
| DEV-008（conftest 导入） | 加入顶层 backend import → 守卫用例报 `['backend.app.database']` |
| DEV-004（缓存标注） | 还原旧标签 → E2E `toContainText failed` |
| PROD-002（生产升级） | 移除生产分支 → 打印未升级的 warning 并失败 |
| PROD-003（新鲜度） | 强制 `stale=False` → `assert False is True` 失败 |
| UX-002（溢出断言） | 注入 1200px 元素 → `0px → 880px`，证明判据敏感 |

凡未取得真实输出的条目（第 3 节表格中的 5 条），一律标注"未验证"，未混入已证结论。
