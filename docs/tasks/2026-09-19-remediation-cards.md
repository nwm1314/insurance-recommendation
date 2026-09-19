# 修复任务卡（2026-09-19 三视角评审 → 修复）

> 来源：`docs/tasks/2026-09-19-three-perspective-review.md`（轮次 1 产出）
> 用法：每轮取**一张**未完成任务卡，按批次与依赖顺序执行。
> 执行流程：复现 → 修复 → 新增回归测试 → 跑全量三命令 → commit → 更新本文件状态。

---

## 0. 全局约束（从提示词继承，不得违反）

1. **顺序执行**，不跳批次；同批次内"数据正确性/契约"先于"体验/视觉"。
2. **先复现再修**，复现命令与输出写入 `2026-09-19-remediation-handoff.md`；无法复现的降级为"观察项"，不凭猜测改代码。
3. **每卡一个 commit**，message 以问题 ID 开头（如 `DEV-001: ...`）。
4. **每卡结束全绿**：`pytest` 全量 + `npm run build` + `playwright` 全量，任一为红则下一轮先修红。
5. **禁止削弱测试**：不得删除测试、跳过用例、放宽断言；正确行为与既有测试冲突时，更新断言语义并在 commit 说明理由。
6. **不引入新依赖/中间件**；模型字段变更必须配 Alembic 迁移。
7. 产品决策型问题一律记入 `2026-09-19-open-questions.md`，不自行拍板。

---

## 1. 基线（轮次 1 实测，作为修复前对照）

| 命令 | 基线结果 | 备注 |
| ---- | ---- | ---- |
| `./backend/venv/Scripts/python.exe -m pytest backend/tests -q` | **10 failed / 270 passed**（Redis 干净时）<br>**38 failed / 242 passed**（Redis 脏时） | 280 collected |
| `cd frontend; npm run build` | **通过**（exit 0，16.14s） | 唯一全绿 |
| `cd frontend; npx playwright test` | **6 failed / 29 passed** | 35 执行 |

**环境**：Windows 10 / Python 3.12.10 / Node v24.15.0 / 本地 redis-server 运行中。

---

## 2. 任务卡

### 批次 A：测试隔离与可信基线（最高优先，其余验证均依赖）

#### DEV-001：后端测试与开发共用真实 Redis，限流键跨测试累积导致集体 429

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-001 |
| 视角 | 开发 |
| 严重度 | **P0** |
| 批次 | A |
| 状态 | 待办 |
| 依赖 | 无（**最高优先**） |

**证据**

- 未清 Redis：`38 failed, 242 passed, 1 warning in 76.51s`；清 Redis 后：`10 failed, 270 passed`。
- Redis 实测残留：`rate_limit:user:day:1 = 211`，TTL 85124s；日限 `config.py:152 = 300`。
- 单文件运行 `test_ingestion_review_workflow.py`：前 9 条通过，第 10 条起 429，响应 `{"detail":"用户请求过于频繁，请稍后再试"}`。
- `grep REDIS_URL|flushdb backend/tests` → **0 命中**（全 24 个测试文件无 Redis 隔离）。
- 对照：`test_rate_limiter.py:32-76` 已正确使用 `StubRedis` + `autouse` fixture。

**根因**

`RateLimiterMiddleware`（`backend/app/middleware/rate_limiter.py:52`）在实例化时对**真实** `settings.redis_url` 建连。测试进程未替换该客户端，故计数器写入开发 Redis，跨测试、跨运行累积。`test_ingestion_review_workflow.py` 用同一 admin（`sub=1`）签发 token，单文件请求数即超 `rate_limit_user_per_minute=30`。

**验收标准**

1. 新增 `backend/tests/conftest.py`，为**全量**后端测试注入隔离 Redis（沿用既有 `StubRedis` 模式，不引入新依赖）。
2. 连续运行 `pytest backend/tests -q` **两次**，第二次结果与第一次一致（不漂移），且均为 **0 failed**。
3. 运行前后开发 Redis 中 `rate_limit:*` 键数量不增加（不污染开发环境）。
4. 现有 280 条用例**不减少**，无新增 skip、无断言放宽。

**验证命令**

```powershell
# 记录运行前键数
./backend/venv/Scripts/python.exe -c "import redis;print(len(redis.from_url('redis://localhost:6379/0',decode_responses=True).keys('rate_limit:*')))"
./backend/venv/Scripts/python.exe -m pytest backend/tests -q
./backend/venv/Scripts/python.exe -m pytest backend/tests -q     # 第二次须一致
./backend/venv/Scripts/python.exe -c "import redis;print(len(redis.from_url('redis://localhost:6379/0',decode_responses=True).keys('rate_limit:*')))"
```

---

#### DEV-002：`ai_cache:*` 脏键跨运行残留，使 AI 降级用例恒失败

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-002 |
| 视角 | 开发 |
| 严重度 | **P0** |
| 批次 | A |
| 状态 | 待办 |
| 依赖 | 与 DEV-001 同批次（共用 conftest 隔离方案） |

**证据**

- `test_ai_mode_degrades_to_rule_when_llm_unavailable` 单独运行仍失败：`assert 'ai' == 'degraded'`。
- Redis 实测：`ai_cache:b434f7dc...` TTL 3554 存活；`ai_quota:ip:testclient:20260918 = 1`，TTL 86354。
- 缓存命中路径 `backend/app/api/recommend.py:376-385`：命中即 `_build_response(user, result, engine_mode="ai")` 并 return，**早于** `ai_rerank_sync` 调用，故 monkeypatch 无效。

**根因**

AI 短缓存（`ai_cache_ttl_seconds`）写入真实 Redis，键跨 pytest 进程存活；`_ai_cache_key` 仅由请求体派生，不含"LLM 是否可用"维度。

**验收标准**

1. 与 DEV-001 共用 conftest 隔离后，该用例在**单跑与全量两种方式下均通过**。
2. 连续两次全量运行结果一致。
3. 补充回归测试：断言"缓存未命中 + LLM 不可用 → `engine_mode == "degraded"`"这一路径不受残留缓存影响。
4. 不得通过删除/跳过该用例来"变绿"。

**验证命令**

```powershell
./backend/venv/Scripts/python.exe -m pytest "backend/tests/test_stage3_recommendation.py::test_ai_mode_degrades_to_rule_when_llm_unavailable" -q
./backend/venv/Scripts/python.exe -m pytest backend/tests -q
```

---

| ID | 视角 | 严重度 | 批次 | 状态 | 依赖 |
| -- | ---- | ------ | ---- | ---- | ---- |
| DEV-001 | 开发 | P0 | A | ✅ 已修复 | 无 |
| DEV-002 | 开发 | P0 | A | ✅ 已修复 | 无 |
| DEV-007 | 开发 | P0 | A | ✅ 已修复 | 无 |
| DEV-008 | 开发 | P1 | A | ✅ 已修复 | 无 |
| DEV-003 | 开发 | P0 | B | ✅ 已修复 | A |
| UX-002 | 设计 | P1 | B | ✅ 已修复 | A, DEV-003 |
| UX-001 | 设计 | P1 | B | ✅ 已闭环（判定为测试测量时机问题，非 UI 缺陷） | A, DEV-003 |
| DEV-005 | 开发 | P1 | C | ✅ 已修复 | A |
| DEV-006 | 开发 | P2 | C | ✅ 已修复 | A |
| DEV-004 | 开发 | P1 | D | ✅ 已修复 | A, B |
| PROD-002 | 产品 | P1 | D | ✅ 已修复 | A |
| PROD-001 | 产品 | P1 | E | ⛔ 阻塞（待决策） | 无 |
| PROD-003 | 产品 | P2 | E | ✅ 已闭环（实测生效，已补回归） | A |

---

#### DEV-001 / DEV-002：Redis 测试隔离（**已完成**）

**修复方式**：新增 `backend/tests/conftest.py`，在**模块导入时**（早于任何被测模块与
`TestClient` 构建）把三处 Redis 入口统一替换为进程内 `FakeRedis`：

- `rate_limiter_module.redis.from_url` + `RateLimiterMiddleware.__init__` 兜底改写；
- `recommend_module._get_redis`；
- `auth_module._get_redis_client`。

并配合会话级 autouse 兜底安装 + 函数级 autouse 清空键空间。

**为什么必须在导入期安装**：`app.add_middleware(RateLimiterMiddleware)` 只登记类，
实例在 `TestClient.__enter__`（即会话级 `client` fixture）时才构建。只在函数级
autouse 里替换入口已经太晚——第一份 TestClient 已抓取真实客户端。初版实现正是
踩了这个坑，实测仍写真实 Redis（`rate_limit:user:day:1 = 132`）。

**验证证据（真实输出）**：

```
# 修复前
$ pytest backend/tests -q
38 failed, 242 passed, 1 warning in 76.51s        # 未清 Redis
10 failed, 270 passed, 1 warning in 40.23s        # 清 Redis 限流键后

# 修复后（连续两次，结果一致且不污染 Redis）
$ pytest backend/tests -q
286 passed, 1 warning in 76.35s
$ pytest backend/tests -q
280 passed, 1 warning in 50.11s                   # 一次为加入新用例前

$ python -c "...keys('*')..."
BEFORE run2 -> rate_limit keys: 0  ai_cache keys: 0  total: 0
AFTER  run2 -> rate_limit keys: 0  ai_cache keys: 0  total: 0
```

**新增回归测试**：`backend/tests/test_redis_test_isolation.py`（6 条），断言三个
入口均为假客户端、假客户端写入不落到真实 Redis、限流键不跨用例泄漏。

**变异验证**：临时注释掉 conftest 的安装逻辑后，该文件立即 3 failed 并打印出泄漏
的真实 `redis.client.Redis(...)`，证明用例真的能抓住回归（非空转通过）。

---

#### DEV-007：`_clean_db` 未清理 `SourcePlatform`，同文件内 UNIQUE 冲突（**评审后新发现**）

| 字段 | 内容 |
| ---- | ---- |
| 严重度 | **P0**（导致全量运行恒有 1 条红） |
| 批次 | A |
| 依赖 | 无 |

**证据**

```
$ pytest backend/tests -q            # 单跑通过，全量失败
FAILED backend/tests/test_product_pool_pipeline.py::test_seed_sources_deactivates_zhongmin_and_adds_shenlanbao
E  sqlite3.IntegrityError: UNIQUE constraint failed: source_platforms.name
E  [parameters: ('中民保险网', 'third_party', 'https://www.zhongmin.cn', None, 5, 1)]

$ pytest "backend/tests/test_product_pool_pipeline.py::test_seed_sources_..." -q
1 passed          # 单独运行通过 → 证明是同文件内跨用例残留
```

**根因**：`test_product_pool_pipeline.py` 的 autouse `_clean_db` 清理了 12 个模型，
**唯独漏掉 `SourcePlatform`**；而 `test_seed_sources_deactivates_zhongmin_and_adds_shenlanbao`
会显式插入"中民保险网"，第二个用例再插入时触发 UNIQUE。

**修复**：把 `SourcePlatform` 加入 `_clean_db` 的清理列表（各用例均自行或经
`ensure_seed_sources` 重建所需来源）。

---

#### DEV-008：3 个测试文件缺 DB 清理，陈旧库触发 `verify_schema_integrity` 导入期报错（**评审后新发现**）

| 字段 | 内容 |
| ---- | ---- |
| 严重度 | P1 |
| 批次 | A |
| 依赖 | 无 |

**证据**

```
E  RuntimeError: Database schema is at migration '20260816_0001' but the current
   Alembic head is '20260914_0002'. Run 'alembic upgrade head' ...
ERROR backend/tests/test_ai_pick.py - RuntimeError: Database schema is at mig...
（共 9 个文件 collection error）
```

**根因（两层）**：

1. 全部测试文件用 `os.environ.setdefault("DATABASE_URL", ...)`，**首个被导入的文件
   胜出**，其余文件的 `setdefault` 变成空操作 → 全量运行时所有文件共用一个库；
   且该库可能停留在过期 Alembic 版本。
2. 仓库根 `data/insurance.db`（`config.py:110` 的默认相对路径，gitignore 内）
   实测停留在 `20260816_0001`；任何在 `DATABASE_URL` 生效前到达
   `verify_schema_integrity()` 的导入链都会直接崩。
3. `test_product_draft_schema.py` 等文件缺少其它文件都有的 `os.remove(...)` 清理。

**修复**：

- 为 `test_product_draft_schema.py` 补上残留库删除（与其余 19 个文件一致）；
- 对本机陈旧 `data/insurance.db` 执行 `alembic upgrade head`（`20260816_0001 →
  20260914_0001 → 20260914_0002`），恢复其与模型一致。

> 说明：`test_llm_safety.py`（纯单元测试，不触碰 DB）与 `test_schema_migration.py`
> （使用 pytest `tmp_path` 隔离库）**不需要**清理逻辑，属正确写法，未改动。

---

### 批次 B：E2E 断言有效性（**已完成**）

#### DEV-003 + UX-002：E2E 步骤断言修复（**已完成，含 UX-001 闭环**）

**根因（实测确认，两层叠加）**：

1. **步骤未前进**：第 2 步 `STEP_FIELDS[1]`（`HomePage.tsx:182`）要求 `job_class` 或
   `occupation_name` 二者其一；测试只填 `age` 就点"下一步"。`handleNext`
   （`HomePage.tsx:304-311`）**先 `validateFields` 再 `setStep`**，校验失败则步骤停在
   原地。实测报错：`请手动选择职业类别，或填写职业名称`，而第 3 步的健康选项始终位于
   `display:none` 容器内（`HomePage.tsx:450`）。
2. **断言锚点选错**：`text=健康状态` 命中的是 AntD `<label>`，其实测宽高为 0，故
   `toBeVisible()` 恒失败。这也解释了 `viewport desktop` 分支同样失败 —— **与窄屏无关**。

**修复**：三处同步（`helpers.ts`、`mobile-flow.spec.ts`、`home.spec.ts`）
- 第 2 步补填 `input#occupation_name`，确保校验通过、步骤真正前进；
- 断言改用真实可见锚点（`input#occupation_name`、`.ant-radio-button-wrapper`）。

**验证证据（真实输出）**：

```
# 修复前
  6 failed
  29 passed (1.6m)

# 修复后
  35 passed (1.3m)
```

**UX-002 溢出证据（修复后首次真正执行）**：`expectNoHorizontalOverflow` 在
320/375/1280 三档真实后端下跑通，产出 9 张截图
（`frontend/test-results/screenshots/{result,account,admin}-{320px,375px,desktop}.png`）。

独立取证（三档视口实测）：

```
home   320px: vw=320 docOverflow=0px bodyOverflow=0px
home   375px: vw=375 docOverflow=0px bodyOverflow=0px
home   desktop: vw=1280 docOverflow=0px bodyOverflow=0px
```

**断言非空转验证**：注入 1200px 宽元素后 `before=0px -> after=880px`，证明判据敏感。

**UX-001 闭环结论**：评审中"label 宽高塌陷"的现象，根因是**在步骤隐藏时测量**。
步骤可见时 label 正常渲染（健康单选项实测 144×32 / 200×32 / 211×32），故判定为
**测试测量时机问题，而非真实 UI 可及性缺陷**，不另开 UI 修复卡。此结论已由
"步骤前进前后对比测量"直接证实。


#### DEV-003：E2E 步骤断言命中零尺寸 label，6 条用例恒红

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-003 |
| 视角 | 开发 |
| 严重度 | **P0** |
| 批次 | B |
| 状态 | 待办 |
| 依赖 | 批次 A（基线可信后判定） |

**证据**

- 失败断言：`helpers.ts:50` `await expect(page.locator('text=健康状态')).toBeVisible();`
- 同样写法：`mobile-flow.spec.ts:122`。
- 实测该 label 盒模型：**viewport 1280 → w=0 h=0；viewport 375 → w=0 h=0**（`display: inline-flex`，`visibility: visible`）。
- 因此 `desktop` 分支同样失败（6 条失败中含 `viewport desktop`），证明**与窄屏无关**。
- 同页可见锚点实测：`Radio.Button` 文本 "无社保"(74×32)、"职工社保"(88×32)、"居民医保"(88×32)、"新农合"(74×32)。

**根因**

AntD 表单 label 在该布局下塌陷为 0 尺寸，`text=` 选择器命中不可见元素；断言锚点选择不当。

**验收标准**

1. 将 `helpers.ts` 与 `mobile-flow.spec.ts` 中基于不可见 label 的步骤断言，改为基于**真实可见/可交互**元素（表单控件或 `Radio.Button` 文本）。
2. `npx playwright test` 全量通过（0 failed）。
3. 断言**不得放宽**为"存在即可"——须保持"可见/可交互"语义强度。
4. 修改后重新取得三档视口（320/375/1280）无横向溢出证据。

**验证命令**

```powershell
cd frontend; npx playwright test
```

---

#### UX-002：窄屏可用性验证因断言缺陷而未真正执行

| 字段 | 内容 |
| ---- | ---- |
| ID | UX-002 |
| 视角 | 设计 |
| 严重度 | P1 |
| 批次 | B |
| 状态 | 待办 |
| 依赖 | DEV-003（同批次，紧随其后） |

**证据**

`mobile-flow.spec.ts:132` 用例在 `fillQuestionnaire` 阶段即失败，`expectNoHorizontalOverflow`（`:137`、`:153`）**从未被执行到**，故"窄屏无溢出"目前**无有效证据**。

**验收标准**

1. DEV-003 修复后，`expectNoHorizontalOverflow` 在 320/375/1280 三档均实际执行并通过（`doc` 与 `body` 溢出 ≤ 2px）。
2. 产出三档视口截图证据，落 `frontend/test-results/screenshots/`。
3. 若此时暴露真实溢出，则登记为新问题卡，不在本卡内顺手改 UI。

**验证命令**

```powershell
cd frontend; npx playwright test mobile-flow.spec.ts
```

---

### 批次 C：工程卫生

#### DEV-005：遗留孤儿 dev server 与未跟踪临时文件污染工作区

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-005 |
| 视角 | 开发 |
| 严重度 | P1 |
| 批次 | C |
| 状态 | 待办 |
| 依赖 | 批次 A |

**证据**

- 未跟踪文件：`frontend/_shots.cjs`、`_audit_scratch/`（含 `be.log`/`fe.log`/`start_servers.py`）、`_baseline_build.txt`、`_baseline_pytest.txt`。
- 孤儿进程：PID 40728 `node node_modules/vite/bin/vite.js --port 3000 --strictPort`，父进程已死。
- 后果实测：首次 `npx playwright test` 直接失败 —— `Error: http://localhost:3000 is already used, make sure that nothing is running on the port/url or set reuseExistingServer:true in config.webServer.`

**验收标准**

1. 清理遗留临时文件与孤儿进程，`git status` 仅剩预期的四个流程文档 + 本次修复变更。
2. 确认 `playwright.config` 的 `webServer.reuseExistingServer` 策略明确（本地 true / CI false 或等价），并在文档中说明"端口被占用时的预期行为"。
3. 不删除任何被 git 跟踪的既有文件。

**验证命令**

```powershell
git status --short
cd frontend; npx playwright test
```

---

#### DEV-006：`ProductItem.sum_insured` 缺单位注释，与 `ExistingPolicy.sum_insured` 语义相反

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-006 |
| 视角 | 开发 |
| 严重度 | P2 |
| 批次 | C |
| 状态 | 待办 |
| 依赖 | 批次 A |

**证据**

- `frontend/src/types/index.ts:26-27`：`ExistingPolicy.sum_insured` 注释为"保额（元）；未披露时为 null"。
- `frontend/src/types/index.ts:51`：`ProductItem.sum_insured` **无单位注释**，而其存储单位为**万**。
- 提示词 §5.1 明确"`sum_insured_*` 存储=万，`premium_*`/`deductible`=元"，且要求四层一致。

**验收标准**

1. 为 `ProductItem.sum_insured` 补充单位注释，明确其单位与展示层换算位置。
2. **仅补注释/类型说明，不改变任何运行时行为**（若确需改数值口径，须另开卡并配回归测试）。
3. `npm run build` 仍通过。

**验证命令**

```powershell
cd frontend; npm run build
```

---

### 批次 D：语义与合规收口

#### DEV-004：AI 缓存命中时 `engine_mode` 恒为 `"ai"`

| 字段 | 内容 |
| ---- | ---- |
| ID | DEV-004 |
| 视角 | 开发 |
| 严重度 | P1 |
| 批次 | D |
| 状态 | 待办 |
| 依赖 | 批次 A、B |

**证据**

`backend/app/api/recommend.py:376-385`：缓存命中即 `_build_response(user, result, engine_mode="ai")` + `ai_from_cache=True` 后 return，不经过 `ai_rerank_sync`，故 `engine_mode` 不反映当前 LLM 可用性。§2.3 已实测复现。

**验收标准**

1. 明确并实现语义：缓存结果应保留 `ai_from_cache=true`（其代表"上次成功的 AI 结果"），且**前端提示不得让用户误以为当前 LLM 可用**。
2. 补充回归测试覆盖"缓存命中 + LLM 当前不可用"的响应语义。
3. **不得**把 AI 降级改成抛错（提示词 §5.3：降级是设计行为）。
4. 前端若需文案调整，按 §4 要求附三档截图证据。

**验证命令**

```powershell
./backend/venv/Scripts/python.exe -m pytest backend/tests -q
cd frontend; npm run build; npx playwright test
```

---

#### PROD-002：本地/E2E 环境健康告知类推荐记录明文落库

| 字段 | 内容 |
| ---- | ---- |
| ID | PROD-002 |
| 视角 | 产品 |
| 严重度 | P1 |
| 批次 | D |
| 状态 | 待办 |
| 依赖 | 批次 A |

**证据**

启动 WARNING（真实输出）：

```
WARNING backend.main:main.py:35 RECORD_ENCRYPTION_KEY is not set: recommendation records
(profile/result, including health disclosures) will be stored in PLAINTEXT.
Set the key in .env before exposing the system to real users.
```

**验收标准**

1. **内测/生产部署**将 `RECORD_ENCRYPTION_KEY` 升为硬性前置配置，并在部署文档中显著标注（涉敏感个人信息）。
2. **不得**把 fail-open 语义改成启动即崩（会破坏本地开发与既有测试，且与 `test_ops002_security.py` 既有约定冲突）。
3. 本地开发保留可用性，但启动告警保持可见。

**验证命令**

```powershell
./backend/venv/Scripts/python.exe -m pytest backend/tests/test_ops002_security.py -q
```

---

### 批次 E：需人类决策 / 待补充实测

#### PROD-001：推荐结果缺少"下一步动作"，核心价值链路断链

| 字段 | 内容 |
| ---- | ---- |
| ID | PROD-001 |
| 视角 | 产品 |
| 严重度 | P1（**需人类拍板**） |
| 批次 | E |
| 状态 | **阻塞于人类决策** — 已记入 `2026-09-19-open-questions.md` OPEN-001 |

**证据**：`README.md:278` 明确系统不提供实时核保/报价 API；产品链接仅指向真实来源页；上一轮会话探测脚本 `_shots.cjs:48` 曾显式检查"是否存在投保/咨询类下一步动作"。

**处理**：按提示词 §7 **不自行拍板**，记入 open-questions，本卡在得到决策前保持阻塞。

---

#### PROD-003：产品池真实性与新鲜度实测

| 字段 | 内容 |
| ---- | ---- |
| ID | PROD-003 |
| 视角 | 产品 |
| 严重度 | P2 |
| 批次 | E |
| 状态 | ✅ 已闭环（实测生效并已补回归） |
| 依赖 | 批次 A |

**证据**：`SEED_DEMO_PRODUCTS` 默认 false 已确认（`config.py:174`、`.env.example:65`、`docker-compose.yml:47`）；E2E 显式置 true（`start-backend.mjs:43`）。`data_stale` / `last_verified_at` 是否真的触发**未复现**（评审阶段）。

**闭环结果（本轮实测，不再是假设）**：新增 `backend/tests/test_product_freshness.py`（4 条），
用反例实证标注链路真实生效：

| 场景 | `last_verified_at` | 期望 `data_stale` | 实测 |
| ---- | ---- | ---- | ---- |
| 从未复核 | `None` | `True` | ✅ |
| 早于阈值（阈值+10 天） | 有值 | `True` | ✅ |
| 刚复核（1 天前） | 有值 | `False` | ✅ |
| 恰好等于阈值（90 天） | 有值 | `False`（严格大于） | ✅ |

链路核对：`recommend._product_freshness`（`recommend.py:53-67`）→ `_build_response`
（`:95`、`:113-114`）→ 前端 `ProductItem.data_stale` / `last_verified_at`
（`types/index.ts:60-62`）展示，全链路完整。

变异验证：将 stale 判定强制为 `False` 后，`test_product_verified_long_ago_is_marked_stale`
立即失败（`assert False is True`），证明断言非空转。

---

## 3. 批次依赖图

```
批次 A (DEV-001, DEV-002, DEV-007, DEV-008)  ← 前置，一切验证的可信度基础
   │
   ├─→ 批次 B (DEV-003 → UX-002, UX-001)          ✅ 已完成
   ├─→ 批次 C (DEV-005, DEV-006)                  ✅ 已完成
   ├─→ 批次 D (DEV-004, PROD-002)                 ✅ 已完成
   └─→ 批次 E (PROD-003 ✅ 已完成 / PROD-001 ⛔ 阻塞于人类决策)
```

**关键约束**：批次 A 闭环前，不得采信任何"修复后全绿"的结论。

---

## 4. 状态统计（逐轮更新）

| 状态 | 数量 | 卡 |
| ---- | ---- | -- |
| 已完成 | 11 | DEV-001, DEV-002, DEV-003, DEV-004, DEV-005, DEV-006, DEV-007, DEV-008, UX-001, UX-002, PROD-002, PROD-003 |
| 进行中 | 0 | — |
| 待办 | 0 | — |
| 阻塞（待人类决策） | 1 | PROD-001（已记入 open-questions OPEN-001） |
| **合计** | **12** | — |

**P0 总数 4**（DEV-001/002/003/007）—— **全部闭环**。
**P1 总数 7**（DEV-004/005/008、UX-001/002、PROD-001/002）—— 6 项闭环，PROD-001 阻塞于人类决策。
**P2 总数 2**（DEV-006、PROD-003）—— **全部闭环**。

> 注 1：UX-001（AntD label 宽高塌陷）经 DEV-003 修复后确认根因是**在步骤隐藏时测量**，
> 并非真实 UI 可及性缺陷（步骤可见时 label 与单选项均正常渲染，实测 144×32 等），
> 故判定为闭环、不另开 UI 修复卡。
> 注 2：DEV-007 / DEV-008 为评审报告产出后、修复过程中**新发现**的缺陷（均属测试隔离类），
> 已一并闭环并登记在本文件批次 A 章节。
