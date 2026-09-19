# 三视角全面评审报告（产品 / 设计 / 开发）

> 评审日期：2026-09-19
> 评审对象：`E:\ai_project\insurance_recommendation` @ commit `20f8fd5`
> 评审方式：只读评审（读代码 / 跑测试 / 起服务 / 实测取证），未修改任何既有代码 / 配置 / 文档。
> 本文档为轮次 1 的唯一写入产物。

---

## 0. 环境与评审前提

| 项 | 值 |
| -- | -- |
| OS | Windows 10 (Microsoft Windows NT 10.0.19045.0) |
| Python | 3.12.10（`backend/venv`） |
| Node | v24.15.0 / npm 11.12.1 |
| Redis | **本地 redis-server 实际在运行**（PID 21320，端口 6379 可连通） |
| 起点 commit | `20f8fd5 OPS-005: joinedload candidate pool, SQLite WAL, scheduler singleton guard` |

**评审前提（重要）**：按提示词 §3.4 要求，`docs/tasks/2026-08-11-audit-task-cards.md` 中全部标记 DONE 的历史结论**一律不采信**，本报告全部结论均来自本次实测。凡引用历史结论处均显式标注。

评审开始时发现上一轮被放弃的会话遗留物（**非本次评审产生，属于既有工作区状态**）：

- 未跟踪文件：`_audit_scratch/`、`_baseline_build.txt`、`_baseline_pytest.txt`、`frontend/_shots.cjs`；
- 遗留进程：孤儿 vite dev server（PID 40728，`--port 3000 --strictPort`）占用 3000 端口，首次 `npx playwright test` 因此直接失败；
- 遗留 Redis 脏数据：`rate_limit:*` 与 `ai_cache:*` 键。

上述遗留状态本身已构成 DEV-001 / DEV-002 的证据（见问题清单）。

---

## 1. 执行摘要

1. **基线并非全绿，且失败原因长期被"环境脏数据"掩盖**：干净 Redis 下 `pytest` 为 **10 failed / 270 passed**；未清理时同一命令为 **38 failed / 242 passed**。差异 28 条全部来自 Redis 限流计数跨测试累积，属于**测试隔离缺陷（P0）**，不是产品缺陷。
2. **测试与开发共用同一个真实 Redis，无任何隔离**：`backend/tests/` 全部 24 个测试文件**没有任何一处**引用 `REDIS_URL` / `flushdb`（grep 实测 0 命中）。唯一正确隔离的是 `test_rate_limiter.py`（自建 `StubRedis` + autouse fixture），说明团队已掌握该模式但未推广。
3. **`playwright` 为 6 failed / 29 passed**，失败集中在两个 spec 的同一断言语义上：`text=健康状态` 匹配到 AntD `<label>`，而该元素**在 1280 与 375 下实测宽高均为 0**。这是**选择器脆弱性**，与移动端适配无关 —— 历史结论若有"窄屏适配已通过"，属**未复现**。
4. **`npm run build` 是三条命令中唯一全绿的**（exit 0，16.14s，最大 chunk 470.47 kB / gzip 153.99 kB）。
5. **产品侧的核心断链仍未闭环**：推荐结果没有真实投保跳转 / 留资能力，`source_url` 仅跳外部聚合站，用户"下一步动作"缺失 —— 属**需人类拍板**的产品决策，按提示词 §7 记入 open-questions，不由评审拍板。

---

## 2. 基线证据（真实命令与输出）

### 2.1 后端全量测试

**命令 A：未清理 Redis（复现"报告称绿"的失败现场）**

```powershell
./backend/venv/Scripts/python.exe -m pytest backend/tests -q
```

真实输出（尾段）：

```
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_unchanged_md5_skips
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_changed_content_creates_new_review
... （共 38 条）
FAILED backend/tests/test_verification_evidence.py::test_recommend_api_carries_verification_fields
38 failed, 242 passed, 1 warning in 76.51s (0:01:16)
```

（该输出同时留存于工作区既有文件 `_baseline_pytest.txt`，为上一轮会话产物，本次复现一致。）

**Redis 键实测（证明计数残留）**：

```
total keys: 9
rate_limit:user:day:1 211 85124
rate_limit:user:day:2 38 85125
...
```

`rate_limit:user:day:1` 已达 **211/300**，TTL 仍剩 85124 秒。`settings.rate_limit_user_per_day = 300`（`backend/app/config.py:152`），即**再跑一轮就必然击穿日限**，导致所有 admin 身份用例集体 429。

**命令 B：清理 Redis 限流键后重跑**

```powershell
./backend/venv/Scripts/python.exe -c "import redis; r=redis.from_url('redis://localhost:6379/0',decode_responses=True); r.delete(*r.keys('rate_limit:*'))"
./backend/venv/Scripts/python.exe -m pytest backend/tests -q
```

真实输出：

```
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_unchanged_md5_skips
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_changed_content_creates_new_review
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_off_shelf_keyword_draft_needs_confirmation_keeps_status
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_404_empty_content_marks_off_shelf_with_identity
FAILED backend/tests/test_ingestion_review_workflow.py::test_crawl_fetch_failure_records_failed_run
FAILED backend/tests/test_ingestion_review_workflow.py::test_rollback_restores_published_snapshot
FAILED backend/tests/test_ingestion_review_workflow.py::test_approve_does_not_reactivate_deactivated_product
FAILED backend/tests/test_ingestion_review_workflow.py::test_admin_update_creates_version_and_rollback_restores
FAILED backend/tests/test_ingestion_review_workflow.py::test_approve_is_atomic_single_transaction
FAILED backend/tests/test_stage3_recommendation.py::test_ai_mode_degrades_to_rule_when_llm_unavailable
10 failed, 270 passed, 1 warning in 40.23s
```

**结论：真实基线 = 10 failed / 270 passed**，其中 9 条仍为限流（见 2.2），1 条为 AI 缓存污染（见 2.3）。

### 2.2 剩余 9 条失败：限流在同一次运行内即被击穿

**命令**：`./backend/venv/Scripts/python.exe -m pytest backend/tests/test_ingestion_review_workflow.py -q`

真实输出：

```
.........FFFFFFFFF                                                       [100%]
```

**前 9 条通过，第 10 条起全部 429**。响应体与断言：

```
>       assert platforms.status_code == 200, platforms.text
E       AssertionError: {"detail":"用户请求过于频繁，请稍后再试"}
E       assert 429 == 200
```

`settings.rate_limit_user_per_minute = 30`（`config.py:151`）。该文件用同一 admin 邮箱签发 token（`sub=1`），**单文件内请求数即超过 30/min**，故必然击穿。这证明：**限流键跨测试累积，且无 per-test 重置**。

### 2.3 第 10 条失败：Redis AI 缓存污染

**命令**：`pytest "backend/tests/test_stage3_recommendation.py::test_ai_mode_degrades_to_rule_when_llm_unavailable" -q`

真实输出：

```
>       assert data["engine_mode"] == "degraded"
E       AssertionError: assert 'ai' == 'degraded'
E         - degraded
E         + ai
1 failed in 5.74s
```

**单独运行也失败**，故不是测试间串扰，而是**跨运行残留**。Redis 实测：

```
ai_cache:b434f7dc... -> {"narrative": "结构化摘要\n推荐理由..."} ttl 3554
ai_quota:ip:testclient:20260918 -> 1 ttl 86354
```

缓存命中路径 `backend/app/api/recommend.py:376-385` 直接 `return _build_response(user, result, engine_mode="ai")`，**早于** `ai_rerank_sync` 被调用，因此 monkeypatch 掉的 `ai_rerank_sync` 返回 `None` 也毫无作用，`engine_mode` 被硬编码为 `"ai"`。该缓存键 TTL `ai_cache_ttl_seconds`，跨 pytest 进程存活。

**这暴露一个真实的行为问题（非仅测试问题）**：缓存命中时响应恒为 `engine_mode="ai"`，即便此刻 LLM 实际不可用。用户在缓存有效期内拿到的 `engine_mode` 无法反映真实引擎状态。详见 DEV-004。

### 2.4 前端构建

**命令**：`cd frontend; npm run build`

真实输出（exit code 0）：

```
dist/index.html                         0.49 kB │ gzip:   0.33 kB
dist/assets/ResultPage-Cb_dsAck.js     37.22 kB │ gzip:  13.05 kB
dist/assets/HomePage-DbcsNl24.js       79.12 kB │ gzip:  26.11 kB
dist/assets/Table-CUr2araI.js         160.60 kB │ gzip:  52.16 kB
dist/assets/react-vendor-C1kAzNxa.js  207.92 kB │ gzip:  70.30 kB
dist/assets/index-DrsuKXGj.js         470.47 kB │ gzip: 153.99 kB
✓ built in 16.14s
```

**这是三条命令中唯一全绿的一条。** 注意：最大 chunk 470.47 kB 已超过 Vite 默认 500 kB 告警线附近，但**无构建失败**；分包（ResultPage / HomePage / Table / react-vendor 独立）实际生效。

### 2.5 E2E

**命令**：`cd frontend; npx playwright test`

**首次运行（失败，非产品问题）**：

```
Error: http://localhost:3000 is already used, make sure that nothing is running on the port/url or set reuseExistingServer:true in config.webServer.
```

原因：上一轮遗留孤儿 vite（PID 40728）。终止该进程后重跑。

**重跑真实输出**：

```
  6 failed
    [chromium] › tests\e2e\mobile-flow.spec.ts:132:7 › 关键流程窄屏适配（mock API，无需后端） › viewport 320px › 问卷全流程提交后结果页完整布局无横向溢出
    [chromium] › tests\e2e\mobile-flow.spec.ts:132:7 › ... viewport 375px › 问卷全流程提交后结果页完整布局无横向溢出
    [chromium] › tests\e2e\mobile-flow.spec.ts:132:7 › ... viewport desktop › 问卷全流程提交后结果页完整布局无横向溢出
    [chromium] › tests\e2e\recommend-flow.spec.ts:22:3 › 推荐关键旅程（真实后端） › 注册→问卷→推荐→保存画像→历史恢复→画像回填→删除
    [chromium] › tests\e2e\recommend-flow.spec.ts:100:5 › 移动视口 320px（真实后端） › 问卷→推荐→结果页完整渲染且无横向溢出
    [chromium] › tests\e2e\recommend-flow.spec.ts:100:5 › 移动视口 375px（真实后端） › 问卷→推荐→结果页完整渲染且无横向溢出
  29 passed (1.6m)
```

断言失败详情：

```
Locator:  locator('text=健康状态')
Expected: visible
Received: hidden
  - waiting for locator('text=健康状态')
    13 × locator resolved to <label title="健康状态" for="health_status" class="ant-form-item-required">健康状态</label>
      - unexpected value "hidden"
   at helpers.ts:50
```

### 2.6 断言脆弱性实证（关键取证）

为判定"是否为移动端适配缺陷"，直接测量该 label 的真实盒模型（临时探测脚本，用后即删）：

```
--- viewport 1280 ---
[{ "cls": "ant-form-item-required", "w": 0, "h": 0, "display": "inline-flex", "visibility": "visible" }]
--- viewport 375 ---
[{ "cls": "ant-form-item-required", "w": 0, "h": 0, "display": "inline-flex", "visibility": "visible" }]
```

**1280 与 375 下宽高均为 0**。即该断言**在桌面视口同样失败**，`mobile-flow.spec.ts` 的 desktop 分支也一并失败（见 2.5 第 3 条），**与窄屏无关**。`visibility` 为 `visible` 而宽高为 0，说明是 AntD 表单 label 的布局塌陷，`text=` 选择器命中了一个不可见元素。

同页可见元素实测（可作稳定断言锚点）：

```
radioTexts: [{"无社保",74,32},{"职工社保",88,32},{"居民医保",88,32},{"新农合",74,32}]
labelsVisible: []        ← 所有 label.ant-form-item-required 均宽高为 0
```

**结论**：应改用 `Radio.Button` 文本或表单控件等**真实可见**元素作为步骤断言。属测试有效性问题（P0，因为它让 6 条 E2E 恒红），不是 UI 缺陷。

### 2.7 环境警示（真实输出，需记录）

```
WARNING backend.main:main.py:35 RECORD_ENCRYPTION_KEY is not set: recommendation records
(profile/result, including health disclosures) will be stored in PLAINTEXT.
Set the key in .env before exposing the system to real users.
```

本地与 E2E 环境下推荐记录（含健康告知）为**明文落库**。属既定 fail-open 设计，但对外内测前必须配置。

---

## 3. 三视角问题清单

> 每条均有实测证据。无证据的判断一律归入 §4「待验证假设」。

### 3.1 开发视角（DEV）

| ID | 视角 | 标题 | 严重度 | 证据 | 影响 | 建议修复方向 | 预估工作量 |
| -- | ---- | ---- | ------ | ---- | ---- | ------------ | ---------- |
| DEV-001 | 开发 | 后端测试与开发共用真实 Redis，限流键跨测试/跨运行累积，导致测试集体 429 | **P0** | `pytest backend/tests -q` 未清 Redis = 38 failed；清后 = 10 failed。Redis 实测 `rate_limit:user:day:1 = 211/300`（limit 见 `config.py:152`）。`grep REDIS_URL\|flushdb backend/tests` **0 命中** | 测试结果不可重现、随运行次数漂移；掩盖真实缺陷；CI/本地结论互斥 | 仿照 `test_rate_limiter.py` 的 `StubRedis` 模式，在 `backend/tests/conftest.py` 统一注入隔离 Redis；或让测试使用独立 DB index 并在 session 级清理 | 小-中 |
| DEV-002 | 开发 | `ai_cache:*` 脏键跨运行残留，使 AI 降级用例恒失败 | **P0** | Redis 实测 `ai_cache:b434f7dc...` TTL 3554 存活；`test_ai_mode_degrades_to_rule_when_llm_unavailable` 单独运行仍 `assert 'ai' == 'degraded'` | 同 DEV-001；且掩盖 DEV-004 的真实语义问题 | 同 DEV-001（隔离 Redis 后自动消解）；补充"缓存键应含引擎可用性维度"的语义讨论 | 小 |
| DEV-003 | 开发 | E2E 步骤断言 `text=健康状态` 命中零尺寸 label，2 个 spec × 3 视口共 6 条恒红 | **P0** | `helpers.ts:50` 与 `mobile-flow.spec.ts:122`；实测该 label 在 **1280 与 375 下 w=0 h=0**；desktop 分支同样失败 | E2E 失去回归价值，掩盖真实移动端问题 | 改为断言可见的 `Radio.Button` 文本（实测 74~88×32）或表单控件；两处 spec 同步修正 | 小 |
| DEV-004 | 开发 | AI 缓存命中时 `engine_mode` 恒为 `"ai"`，不反映实时 LLM 可用性 | P1 | `recommend.py:376-385`：命中即 `_build_response(..., engine_mode="ai")` 并 return，**早于** `ai_rerank_sync` 调用；§2.3 实测复现 | 用户/前端在缓存 TTL 内无法得知引擎实际降级，`EngineSwitch` 提示可能失真 | 明确语义：缓存代表"上次成功 AI 结果"应保留 `ai_from_cache=true` 并在 UI 说明；或在降级时给出区别于实时降级的文案 | 小-中 |
| DEV-005 | 开发 | 上一轮遗留的孤儿 dev server 与未跟踪临时文件污染工作区，并使 E2E 首次直接失败 | P1 | `E:\...\frontend\_shots.cjs`、`_audit_scratch/`、`_baseline_*.txt` 未跟踪；PID 40728 孤儿 vite 占用 3000；`npx playwright test` 首次报 `http://localhost:3000 is already used` | 可重现性受损；新人/CI 首次运行即失败 | 清理遗留文件与进程；`playwright.config` 明确 `reuseExistingServer` 策略；把临时脚本纳入 `.gitignore` | 小 |
| DEV-006 | 开发 | 单位口径注释不完整，`ProductItem.sum_insured` 未标注单位 | P2 | `frontend/src/types/index.ts:27` `ExistingPolicy.sum_insured` 注释"保额（元）"，而 `:51` `ProductItem.sum_insured` **无单位注释**，二者语义相反（存储=万 vs 元） | 与提示词 §5.1 强调的"四层一致"高风险区直接相关，易二次踩坑 | 补注释明确 `ProductItem.sum_insured` 单位与展示层换算点 | 小 |

### 3.2 设计视角（UX）

| ID | 视角 | 标题 | 严重度 | 证据 | 影响 | 建议修复方向 | 预估工作量 |
| -- | ---- | ---- | ------ | ---- | ---- | ------------ | ---------- |
| UX-001 | 设计 | AntD 表单 label 在实测中宽高塌陷为 0，存在可及性/可读性风险 | P1 | §2.6 实测：**所有** `label.ant-form-item-required` w=0 h=0（1280 与 375 均如此）；`mobile-responsive.css:11` 仅有 `text-align: left !important` | 屏幕阅读器与视觉用户均可能丢失字段名，影响表单可理解性 | 定位 label 塌陷根因（疑似 `Form layout` 与自定义 CSS 冲突），确保 label 正常渲染 | 中 |
| UX-002 | 设计 | 步骤断言依赖不可见文本，掩盖了真实的窄屏可用性验证 | P1 | `helpers.ts:50`、`mobile-flow.spec.ts:122` 断言的元素实测不可见；窄屏无横向溢出的断言语义因此**未被真正执行到** | 移动端"真的可用"缺少可信证据 | 修正断言后再重跑三档视口，重新取得溢出证据 | 小（依赖 DEV-003） |

### 3.3 产品视角（PROD）

| ID | 视角 | 标题 | 严重度 | 证据 | 影响 | 建议修复方向 | 预估工作量 |
| -- | ---- | ---- | ------ | ---- | ---- | ------------ | ---------- |
| PROD-001 | 产品 | 推荐结果缺少"下一步动作"，核心价值链路止于展示 | P1（需人类拍板） | `frontend/_shots.cjs:48` 探测项 `hasNextAction: /立即投保\|去投保\|购买\|咨询/` 为上一轮会话显式验证点；`README.md:278` 明确"系统不提供实时核保或保险公司报价 API"，产品链接仅指向真实来源页 | 用户拿到方案后无处可去，转化断链 | **不自行拍板**——是否引入投保跳转/留资记入 `open-questions.md` | 需决策 |
| PROD-002 | 产品 | 本地/E2E 环境健康告知类推荐记录明文落库 | P1 | `main.py:35` 启动 WARNING 原文见 §2.7 | 涉敏感个人信息，对外内测前有合规风险 | 内测部署强制配置 `RECORD_ENCRYPTION_KEY`；在部署文档中升为硬性前置检查 | 小 |
| PROD-003 | 产品 | 产品池真实性与 `data_stale` 的实际生效情况未在本次复现 | P2 | `SEED_DEMO_PRODUCTS` 默认 false（`config.py:174`、`.env.example:65`、`docker-compose.yml:47`），E2E 专用后台显式置 true（`start-backend.mjs:43`）；门控逻辑 `pipeline.py:117` | 演示数据与真实数据边界清晰，但"新鲜度"未复现 | 转 §4 待验证假设，下轮补实测 | 小 |

---

## 4. 待验证假设（无充分证据，不计入问题清单）

按提示词 §8.3 要求单列，避免与已证实问题混淆：

1. **`data_stale` / `last_verified_at` 的实际生效情况**：未构造超 90 天未复核产品做实测，无法确认标注是否真的触发。仅确认门控 `SEED_DEMO_PRODUCTS` 默认 false。
2. **保费区间 / `premium_basis_note` 口径在 UI 上是否自相矛盾**：未逐字段比对展示层，未取证。
3. **"保费倒挂预警"是否真的触发过**：未构造触发用例，**未复现**。
4. **推荐接口 P50 / P95 耗时（极速 vs AI）**：本次未做压测，无数据。
5. **对比度是否达标**：提示词要求"用工具实测"，本次未跑对比度工具，**不下结论**。
6. **`frontend/.npmcache/` 是否入库**：`.gitignore` 已含该条目（实测），但未核对其历史成因，不下结论。
7. **`remediation-prompt.md` §5.1 所述四层单位一致性是否真的统一**：仅发现类型注释缺口（DEV-006），**未**构造反例实证，不下结论。

---

## 5. 与既有文档的差异

| 既有结论（来源） | 本次实测 | 判定 |
| ---- | ---- | ---- |
| `docs/tasks/2026-08-11-audit-task-cards.md` 全部标记 DONE，多条称"已验证通过" | `pytest` 实际 10~38 failed；`playwright` 6 failed | **被推翻**：历史"已验证通过"不成立（至少在当前环境与当前代码下） |
| `audit-task-cards.md:947` "seed 门控下架（SEED_DEMO_PRODUCTS 默认 false）" | `config.py:174` 默认 false，`.env.example:65`、`docker-compose.yml:47` 一致 | **确认成立** |
| `README.md:278` "生产环境不注入演示目录（`SEED_DEMO_PRODUCTS=false`）" | 同上，且 E2E 显式覆盖为 true（`start-backend.mjs:43`） | **确认成立** |
| `README.md` 称 `RECORD_RETENTION_DAYS` 本期不实现 | 未复核该结论 | **未复现** |
| 提示词 §3.1 称 `backend/tests` 208+ 用例 | 实测 **280** 条（270 passed + 10 failed） | 确认规模量级，数字已增长 |
| 提示词 §3.1 称 `frontend/src` 约 3k 行 | 实测 2993 行 | **确认成立** |
| 提示词 §3.1 称 `backend/app` 约 6.4k 行 | 实测 6366 行 | **确认成立** |
| 提示词 §3.1 称 `frontend/tests/e2e` 13 个 spec | 实测 **10** 个 spec 文件（`account/admin-flow/admin/auth-flow/home/login/mobile-flow/mobile/navigation/recommend-flow`），声明 24 条 `test()`，参数化后实际执行 **35** 条（29 passed + 6 failed） | **需修正**：文件数为 10，非 13 |

---

## 6. 架构级建议

**值得做：**

1. **测试隔离基线（对应 DEV-001/002）**：新增 `backend/tests/conftest.py`，统一以 `StubRedis`（或独立 Redis DB index）替换 `rate_limiter` 与 `recommend._get_redis`。这是**前置任务**——不做它，任何"全绿"结论都不可信，后续所有修复的验证都会失真。
2. **E2E 断言锚点规范化（对应 DEV-003/UX-002）**：把 `helpers.ts` / `mobile-flow.spec.ts` 中基于"文本可见性"的步骤断言改为基于**真实可交互控件**的断言，并在修正后重取三档视口溢出证据。

**明确不做及原因：**

- **不拆分** `recommend.py`(470 行) 与 `combo_builder.py`(471 行)：规模未达必须拆分程度，且提示词 §9 明令"不做超出评审范围的代码重构"。仅登记为观察项。
- **不引入**新依赖 / 中间件解决 Redis 隔离：既有 `StubRedis` 模式已足够，符合"不新增依赖"约束。
- **不动** AI 降级语义（LLM 异常切极速是设计行为，提示词 §5.3 明确不得"修"成抛错）。
- **不改** 套餐命名 / 免责声明措辞 / 是否引入投保跳转：均属人类拍板项。

---

## 7. 修复顺序建议（批次）

| 批次 | 主题 | 含卡 | 依赖 |
| ---- | ---- | ---- | ---- |
| **批次 A** | 测试隔离与可信基线（先把"能验证"这件事修好） | DEV-001, DEV-002 | 无（**最高优先**，其余验证均依赖它） |
| **批次 B** | E2E 断言有效性（让 6 条恒红恢复为真实验证） | DEV-003, UX-002 | 依赖 A（基线可信后判定） |
| **批次 C** | 工程卫生与工作区清理 | DEV-005, DEV-006 | 依赖 A |
| **批次 D** | 语义与合规收口 | DEV-004, PROD-002 | 依赖 A、B |
| **批次 E（需人类决策）** | 产品链路与待验证项实测 | PROD-001, PROD-003, §4 各条 | 依赖 A |

**批次间依赖说明**：A 是其余一切的前提——在 Redis 未隔离前，"修完变绿"与"恰好没击穿限流"无法区分，故 A 必须先做且单独成一个 commit。

---

## 8. 评审结论

- **P0 项 3 条**：DEV-001、DEV-002、DEV-003 —— 全部为**可验证性缺陷**（测试隔离 2 条 + E2E 断言 1 条），均有命令级证据，修复路径明确。
- **P1 项 5 条**：DEV-004、DEV-005、UX-001、UX-002、PROD-001（其中 PROD-001 需人类拍板）、PROD-002。
- **P2 项 2 条**：DEV-006、PROD-003。
- 本次评审**未修改任何既有代码 / 配置 / 文档**，唯一写入为本报告，符合提示词 §2 只读要求。

**给下一轮（拆卡）的关键提示**：批次 A 未闭环前，不得采信任何"修复后全绿"的结论。
