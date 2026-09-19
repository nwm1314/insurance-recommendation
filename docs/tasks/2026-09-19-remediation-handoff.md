# 修复交付记录（2026-09-19 三视角评审 → 修复）

> 分支：`codex/three-perspective-remediation`
> 起点 commit：`20f8fd5`（master）
> 修复轮终态 commit：`2a1661b`
> 决策落地轮终态 commit：见 §8（OPEN-001~005 已全部落地）
> 执行方式：按 `2026-09-19-autonomous-loop-prompt.md` 多轮推进（评审 → 拆卡 → 逐卡修复 → 收尾 → 决策落地）
> 本文档记录逐条结论、变更文件、验证命令与真实输出摘要、遗留项。

---

## 1. 交付总览

| 项 | 修复前（基线实测） | 修复轮终态 | 决策落地轮终态 |
| -- | ---- | ---- | ---- |
| `pytest backend/tests -q` | **10 failed / 270 passed**（Redis 干净时）<br>**38 failed / 242 passed**（Redis 脏时） | **301 passed / 0 failed** | **303 passed / 0 failed**（+OPEN-003 命名回归、+OPEN-002 compose 门禁回归） |
| `cd frontend; npm run build` | 通过（exit 0） | 通过（exit 0，11.80s） | 通过（exit 0，21.37s） |
| `cd frontend; npx playwright test` | **6 failed / 29 passed** | **37 passed / 0 failed** | **37 passed / 0 failed**（新增 5 条 OPEN-001 断言，用例数不变） |

**完成标准核对**

- [x] 评审报告中所有 P0 项闭环（4 项，含修复中新发现的 1 项）
- [x] P1 项闭环（7 项全部闭环；PROD-001 已按 OPEN-001 决策落地，见 §8）
- [x] `pytest` 全量绿（303 passed；无新增 skip、无断言削弱）
- [x] `npm run build` 通过
- [x] `playwright` 全量绿（37 passed）
- [x] 每个修复都有对应的回归测试或截图证据
- [x] 本文件完整，无未验证结论（未验证项已明确标注）
- [x] `2026-09-19-remediation-cards.md` 状态与实际一致
- [x] 所有产品决策型问题已记录并落地（`2026-09-19-open-questions.md` 5 项全部"已决策/已落地"）
- [x] 未引入新依赖 / 新中间件 / 范围外重构

**commit 列表（修复轮 7 个 + 决策落地轮 3 个，每卡一个主题）**

| commit | message |
| ---- | ---- |
| `2ad49d9` | DEV-001/DEV-002/DEV-007/DEV-008: isolate test Redis and fix cross-test DB/shared-state leakage |
| `6ebc75b` | DEV-003/UX-002: fix E2E questionnaire step assertions (6 always-failing tests) |
| `e30963b` | DEV-005/DEV-006: workspace hygiene, test docs, and money-unit consistency guard |
| `006ae1c` | docs: add 2026-09-19 three-perspective review, remediation cards, and open questions |
| `ec712c0` | DEV-004: surface AI cache provenance instead of a bare "AI 精排模式" |
| `14d62bf` | PROD-002: make the plaintext-record risk actionable for production deployment |
| `2a1661b` | PROD-003: prove product freshness labelling actually works (closes a review assumption) |
| `2468596` | OPEN-003: 套餐改为中性功能化命名（低保费优先/均衡配置/高保额优先） |
| `59a4e99` | OPEN-001: 结果页补「下一步怎么做」说明，并把「起」口径统一到产品卡与对比表 |
| `5d74866` | OPEN-002: 把推荐记录加密密钥变成部署清单的硬性卡点（补齐 compose 透传缺口） |

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
| **PROD-001** | **已按决策闭环**（修复轮记为"不修（需人类决策）"，人类已于 2026-09-19 拍板 OPEN-001 方案 1 + 局部增强） | `frontend/src/pages/ResultPage.tsx`<br>`frontend/src/components/ProductCard.tsx`<br>`frontend/src/components/CompareTable.tsx`<br>`frontend/tests/e2e/{helpers,mobile-flow,recommend-flow}.spec.ts`<br>`README.md` | 结果页新增「下一步怎么做」卡片（明示辅助决策工具边界 + 三条可行动作），不引入投保跳转/留资；顺带取证并修复「起」口径不一致。详见 §8 OPEN-001 行 | 无（转化链路仍止于外链，属已决策的产品边界，非缺陷） |

---

## 3. 未闭环项与原因

**无未闭环项。** 修复轮记的 3 项在决策落地轮全部关闭：

| 项 | 修复轮状态 | 决策落地轮终态 |
| -- | ---- | ---- |
| **PROD-001** | ⛔ 阻塞于人类决策 | ✅ 已按 OPEN-001（方案 1 + 局部增强）落地，见 §8 |
| OPEN-003（套餐命名） | 待决策 | ✅ 人类拍板方案 2，已落地（`2468596`） |
| OPEN-002（内测加密策略） | 待确认 | ✅ 人类拍板方案 3，部署清单硬性卡点已补齐（`5d74866`） |

评审报告 §4「待验证假设」中的 7 条，两轮累计闭环 3 条，其余 4 条说明如下：

| 待验证假设 | 处理结果 |
| ---- | ---- |
| `data_stale` / `last_verified_at` 生效情况 | ✅ 已闭环（PROD-003，反例实证） |
| 四层单位口径是否真的统一 | ✅ 已闭环（DEV-006，反例实证） |
| 保费区间 / 「起」标注在 UI 是否自相矛盾 | ✅ 已闭环（OPEN-001 取证并修复：结果页口径说明承诺"标注「起」表示未披露上限"，但 `ProductCard`/`CompareTable` 渲染的是裸数字——同一数字在套餐页签带「起」、在产品卡不带。现已统一并加 E2E 断言 `¥299起`） |
| "保费倒挂预警"是否真的触发过 | 未验证 —— 未构造触发用例 |
| 推荐接口 P50 / P95 耗时 | 未验证 —— 未做压测 |
| 对比度是否达标 | 未验证 —— 未跑对比度工具（提示词要求工具实测，未做） |
| `frontend/.npmcache/` 是否入库 | 已确认 `.gitignore` 含该条目；历史成因未考证 |

上述 4 条**不影响 P0/P1 闭环**，属 P2/P3 优化项；如需闭环建议另开专项卡片。

> 另记一条本轮观察（未改代码）：后端在推荐响应里返回固定文案 `premium_basis_note`
> （`backend/app/api/recommend.py:33`），前端**未消费**该字段，结果页顶部用的是
> `ResultPage.tsx:199` 的硬编码同类说明。两处文案语义一致、不互相矛盾，故不构成缺陷；
> 若要收敛为单一来源，建议另开卡片（涉及历史记录缺该字段时的兼容口径）。

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
./backend/venv/Scripts/python.exe -m pytest backend/tests -q      # 303 passed
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

汇总见 `docs/tasks/2026-09-19-open-questions.md`，共 5 项。**人类已于 2026-09-19 全部拍板，
本轮逐项落地完毕**（落地细节见 §8）：

| ID | 问题 | 阻塞任务 | 决策 | 落地 |
| -- | ---- | ---- | ---- | ---- |
| **OPEN-001** | 是否引入真实投保跳转 / 留资能力 | PROD-001 | 方案 1 + 局部增强 | ✅ `59a4e99` |
| OPEN-002 | 健康信息明文落库能否进入对外内测 | PROD-002 | 方案 3（分环境门禁） | ✅ `14d62bf` + `5d74866` |
| OPEN-003 | 三套套餐命名是否调整 | 无 | 方案 2（中性功能化命名） | ✅ `2468596` |
| OPEN-004 | `data_stale` 是否本期闭环 | PROD-003 | 方案 1（本期补实测） | ✅ `2a1661b` |
| OPEN-005 | 是否新增 `backend/tests/conftest.py` | DEV-001/002 | 方案 1（共享 conftest） | ✅ `2ad49d9` |

**本文件不再存在待人类决策的阻塞项。**

---

## 6. 遗留风险

1. ~~**PROD-001 未闭环**~~ —— 已按 OPEN-001 决策落地：本期**不做**投保跳转与留资，结果页
   改以「下一步怎么做」卡片承担引导。因此"用户拿到方案后无站内下一步动作"这一条**已由
   文案闭环**；但**转化链路仍止于外链**，这是已拍板的产品边界而非工程缺陷。若后续改判为
   方案 2/3/4（留资、跳转、合作方对接），需另立评审与卡片。
2. **`npm run build` 主 chunk 470.47 kB（gzip 153.99 kB）** —— 已接近 Vite 默认告警线。分包实际生效（ResultPage/HomePage/Table/react-vendor 独立），本轮**未做**进一步拆包（属范围外优化）。
3. **测试仍共用同一个 Redis 概念** —— conftest 用进程内 `FakeRedis` 解决；若未来新增第四个 Redis 入口，需同步加入 `_install_fake_redis()`，`test_redis_test_isolation.py` 会给出失败信号，但仍需人工补充替换点。
4. **各测试文件的 `DATABASE_URL` 仍靠 `setdefault` 竞逐** —— 全量运行时会共用一个库。本轮已让新增测试自给自足（自建 Rule/Benefit），但这是既有的架构性脆弱点，未在本期范围内重构。
5. **评审报告 §4 的 4 条待验证假设未闭环** —— 已在第 3 节逐条列明，不影响 P0/P1 判定。
6. **加密门禁是"清单 + 回归"级，不是"运行时拒绝启动"级** —— 方案 3 明确保留本地明文
   fail-open，因此若有人跳过部署清单、或绕过 compose 直接起 uvicorn，仍可能明文落库。
   现有约束力来自：生产 error 日志、两份清单的 `exit 1` 卡点、
   `test_backend_forwards_record_encryption_key` 对 compose/文档的锁定。

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
| OPEN-002（compose 透传） | 删除 `RECORD_ENCRYPTION_KEY: ${...}` 那行 → `test_backend_forwards_record_encryption_key` 立即 `1 failed, 3 passed`；还原后 4 passed（真实输出见 §8） |
| OPEN-003（中性命名） | 把 budget/premium 标签改回"极致性价比/尊享无忧" → 命名回归立即 `1 failed`，报 `assert '🛡 极致性价比' == '🛡 低保费优先'` |
| OPEN-001（下一步说明） | 删除「下一步怎么做」卡片 → `mobile-flow` 320px 用例立即 `1 failed`（`getByText('下一步怎么做')` 超时），另 2 条通过；还原后全绿 |

凡未取得真实输出的条目（第 3 节表格中的 4 条），一律标注"未验证"，未混入已证结论。
所有变异均在验证后**逐字节还原**（`git status` 确认工作区仅剩预期文档改动）。

---

## 8. 决策落地轮记录（OPEN-001~005，2026-09-19）

人类对 `2026-09-19-open-questions.md` 5 项的拍板已逐项落地。每轮一个 commit、结束时三命令全绿。

| ID | 决策 | 落地结论 | 变更文件 | 验证（真实输出摘要） | 遗留项 |
| -- | ---- | ---- | ---- | ---- | ---- |
| **OPEN-003** | 方案 2 | **已落地**（`2468596`）。`PACKAGE_DEFS` 三套标签改为 `🛡 低保费优先 / ⭐ 均衡配置 / 👑 高保额优先`；旧名"尊享""全面"隐含"越贵越好"，而三套差异只是预算档位（0.5/0.8/1.0）与保障完整度。README 同步；E2E mock 的 `tag_label` 与断言同步 | `backend/app/engine/combo_builder.py`<br>`backend/tests/test_stage3_recommendation.py`<br>`frontend/tests/e2e/mobile-flow.spec.ts`<br>`README.md`<br>`docs/tasks/2026-09-19-open-questions.md` | 接手时三命令复跑：`302 passed` / `build exit 0` / `37 passed`。新回归 `test_package_labels_are_neutral_not_quality_tiered` 锁定命名 + 禁用优劣词 + 断言预算档位严格递增；变异验证见 §7。1280px 截图实测页签为 `低保费优先(¥970~¥3,500/年) / 均衡配置 / 高保额优先` | 无 |
| **OPEN-001** | 方案 1 + 局部增强 | **已落地**（`59a4e99`）。**不**引入投保跳转与留资；结果页在「横向对比」之后新增「下一步怎么做」卡片：先声明边界（辅助决策工具、不提供实时核保、不出具有效报价、评分排序仅代表匹配度不代表承保），再给三条可行动作（核对产品来源页 → 逐项核对健康告知 → 投保前咨询官方客服，并声明不代收保费/不代办投保）。顺带取证并修复「起」口径不一致 | `frontend/src/pages/ResultPage.tsx`<br>`frontend/src/components/ProductCard.tsx`<br>`frontend/src/components/CompareTable.tsx`<br>`frontend/tests/e2e/helpers.ts`<br>`frontend/tests/e2e/mobile-flow.spec.ts`<br>`frontend/tests/e2e/recommend-flow.spec.ts`<br>`README.md` | 全量：`302 passed` / `build exit 0` / `37 passed`。E2E 新增断言 5 条（mock 三档 + 真实后端 2 处）：卡片标题、"辅助决策工具"、"逐项核对健康告知"、`¥299起`（未披露上限）。UI 证据：`frontend/test-results/screenshots/` 的 `result-{320px,375px,desktop}.png` 与新增 `next-steps-real-backend-{320,375,1280}px.png`，每档均过 `expectNoHorizontalOverflow`（doc/body `scrollWidth-clientWidth <= 2px`） | 无。转化链路仍止于外链 —— 这是已拍板的产品边界（见 §6 第 1 条） |
| **OPEN-002** | 方案 3 | **已落地**（`14d62bf` 运行时告警分级 + 文档章节；`5d74866` 本轮补齐门禁）。核查发现门禁**实际漏了三处**：① `docker-compose.yml` 的 backend `environment:` 段没有透传该变量（compose 只注入显式列出的变量，`.env` 写了容器也读不到 → 照文档配置仍会明文落库）；② `.env.example` 无该条目，而两份清单第一步就是 `cp .env.example .env`；③ 「首次部署测试环境」「生产部署」两份清单未含检查步骤，加密提示只存在于独立章节。现三处补齐，检查命令由"grep 成功才 echo OK"（永不失败）改为 `exit 1` 卡点，并加 `docker compose config` 一步确认变量真进了容器。**未改为拒绝启动**（本地明文 fail-open 是既定语义） | `docker-compose.yml`<br>`.env.example`<br>`docs/docker-deployment.md`<br>`backend/tests/test_compose_policy.py`<br>`README.md`<br>`docs/tasks/2026-09-19-open-questions.md` | 全量：`303 passed` / `build exit 0（21.37s）` / `37 passed`。YAML 解析确认 `services.backend.environment.RECORD_ENCRYPTION_KEY == '${RECORD_ENCRYPTION_KEY:-}'`（backend 共 35 个注入变量）。变异验证见 §7。E2E 真实后端日志中确实出现 warning 原文，证明 grep 判据指向真实存在的字符串 | 无。约束力属"清单 + 回归"级，非运行时强制（见 §6 第 6 条） |
| **OPEN-004** | 方案 1 | **已在修复轮落地**（`2a1661b`），本轮归档确认在库且绿 | `backend/tests/test_product_freshness.py` | `pytest test_product_freshness.py test_redis_test_isolation.py test_compose_policy.py -q` → `16 passed`。4 条反例：`test_never_verified_product_is_marked_stale` / `..._verified_long_ago_...` / `..._recently_verified_..._is_not_stale` / `test_threshold_boundary_is_strictly_greater_than`（恰好 90 天 → False） | 无 |
| **OPEN-005** | 方案 1 | **已在修复轮落地**（`2ad49d9`），本轮归档确认在库且绿 | `backend/tests/conftest.py`<br>`backend/tests/test_redis_test_isolation.py` | conftest 在导入期把 `redis.from_url` 换成进程内 `FakeRedis`，且**不 import 任何 backend 模块**（守卫用例 `test_conftest_does_not_import_backend_at_load_time` 以 AST 检查顶层 import）。本轮未触碰其隔离逻辑 | 无 |

**决策落地轮 commit**：`2468596`（OPEN-003）→ `59a4e99`（OPEN-001）→ `5d74866`（OPEN-002）→ 本文档 commit。

**执行中改动的既有测试断言（按硬性约束 5 说明）**：`frontend/tests/e2e/helpers.ts:63`、
`mobile-flow.spec.ts:149`、`recommend-flow.spec.ts:66` 三处 `page.locator('text=横向对比')`
改为 `page.getByText('横向对比', { exact: true })`。原因：新增的「下一步怎么做」文案正文
合法包含"横向对比表"，宽松子串选择器命中 2 个元素触发 strict mode violation（首轮实测
6 failed）。改为精确匹配卡片标题后断言目标更明确、强度不降，未删除或跳过任何用例。
