import { test, expect, Page } from '@playwright/test';

const VIEWPORTS = [
  { name: '320px', viewport: { width: 320, height: 568 } },
  { name: '375px', viewport: { width: 375, height: 667 } },
  { name: 'desktop', viewport: { width: 1280, height: 720 } },
];

const SCORE_DETAIL = {
  coverage: 18, price: 15, flexibility: 13, waiting: 10,
  adequacy: 8, waiver: 10, brand: 8, service: 6,
};

const P1 = {
  id: 1, name: '平安e生保百万医疗险（保证续保版）', company: '中国平安', type: '医疗险', layer: 'basic',
  premium: 350, premium_max: 780, deductible: 10000, sum_insured: 400,
  source_url: 'https://example.com/1', score: 86, score_detail: SCORE_DETAIL,
  risk_warnings: [], recommendation_reasons: ['医疗险标配', '报销型·百万医疗'],
  not_recommended_reasons: [],
};
const P2 = {
  id: 2, name: '大护甲成人意外险', company: '人保财险', type: '意外险', layer: 'core',
  premium: 299, premium_max: null, deductible: null, sum_insured: 200,
  source_url: '', score: 78, score_detail: SCORE_DETAIL,
  risk_warnings: [], recommendation_reasons: ['职业等级符合'],
  not_recommended_reasons: [],
};
const P3 = {
  id: 3, name: '达尔文7号重疾险', company: '国富人寿', type: '重疾险', layer: 'core',
  premium: 6800, premium_max: 12000, deductible: null, sum_insured: 50,
  source_url: 'https://example.com/3', score: 91, score_detail: SCORE_DETAIL,
  risk_warnings: [], recommendation_reasons: ['重疾保额充足', '等待期短'],
  not_recommended_reasons: [],
};
const P4 = {
  id: 4, name: '大麦2026定期寿险', company: '华贵人寿', type: '定期寿险', layer: 'supplement',
  premium: 2100, premium_max: null, deductible: null, sum_insured: 100,
  source_url: '', score: 82, score_detail: SCORE_DETAIL,
  risk_warnings: [], recommendation_reasons: ['家庭支柱必备'],
  not_recommended_reasons: [],
};

const RECOMMENDATION = {
  user_profile: {},
  budget_analysis: {
    annual_income: 200000, total_budget: 16000,
    allocation: { medical: 0.2, accident: 0.1, critical_illness: 0.4, life: 0.2, cancer: 0.1 },
  },
  sum_insured_advice: {
    medical: 4000000, accident: 2000000, critical_illness: 900000, life: 1300000, cancer: 300000,
  },
  packages: [
    {
      tag: 'balanced', tag_label: '均衡型方案', total_premium: 14800, total_premium_max: 15600,
      budget_ratio: 0.074, budget_utilization: 0.93, completeness_score: 0.92, coverage_gap_notes: [],
      products: [P1, P2, P3],
    },
    {
      tag: 'cheap', tag_label: '极致性价比', total_premium: 9800, total_premium_max: 10400,
      budget_ratio: 0.049, budget_utilization: 0.61, completeness_score: 0.71, coverage_gap_notes: ['定期寿险保障偏弱'],
      products: [P1, P4],
    },
  ],
  llm_narrative: '根据您的画像，医疗+意外+重疾构成核心保障层，建议优先补足定期寿险。',
  ai_explanation: {
    selected_product_ids: [1, 2, 3],
    summary: '均衡型方案覆盖核心风险且保费可控。',
    reasoning: ['保障全面性高', '保费在预算区间内'],
    risk_notes: ['医疗险免赔额 1 万元'],
    comparison_notes: ['A 方案保费更低，B 方案保障更全'],
  },
  engine_mode: 'rule',
  hard_rule_summary: ['硬性规则已先执行：年龄、职业、健康告知均通过'],
  coverage_gap_summary: [],
  not_recommended_summary: [],
  not_recommended_details: [],
  disclaimer: '本推荐仅供参考，最终以保险公司官方条款为准。',
};

const ADMIN_USER = {
  id: 1, email: 'admin@example.com', full_name: '管理员',
  roles: ['admin'], permissions: ['crawl:read', 'crawl:trigger', 'product:write'],
};

const NORMAL_USER = {
  id: 2, email: 'user@example.com', full_name: '普通用户',
  roles: ['user'], permissions: ['product:read'],
};

async function expectNoHorizontalOverflow(page: Page) {
  const result = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    return {
      doc: doc.scrollWidth - doc.clientWidth,
      body: body ? body.scrollWidth - body.clientWidth : 0,
    };
  });
  expect(result.doc, `document 横向溢出 ${result.doc}px`).toBeLessThanOrEqual(2);
  expect(result.body, `body 横向溢出 ${result.body}px`).toBeLessThanOrEqual(2);
}

async function fillQuestionnaire(page: Page) {
  await page.goto('/');
  await expect(page.locator('text=智能保险推荐').first()).toBeVisible();
  await page.locator('input#age').fill('30');
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('text=职业类别')).toBeVisible();
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('text=健康状态')).toBeVisible();
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('button:has-text("开始推荐")')).toBeVisible();
}

test.describe('关键流程窄屏适配（mock API，无需后端）', () => {
  for (const vp of VIEWPORTS) {
    test.describe(`viewport ${vp.name}`, () => {
      test.use({ viewport: vp.viewport });

      test('问卷全流程提交后结果页完整布局无横向溢出', async ({ page }) => {
        await page.route('**/api/recommend', (route) => route.fulfill({
          status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION),
        }));
        await fillQuestionnaire(page);
        await expectNoHorizontalOverflow(page);

        await page.locator('button:has-text("开始推荐")').click();
        await expect(page.locator('text=推荐方案')).toBeVisible({ timeout: 15000 });
        await expect(page.locator('text=预算与报价分析')).toBeVisible();
        await expect(page.locator('text=建议保额')).toBeVisible();
        await expect(page.getByText('医疗险', { exact: true }).first()).toBeVisible();
        await expect(page.locator('.ant-tabs-tab', { hasText: '均衡型方案' })).toBeVisible();
        await expect(page.locator('text=横向对比')).toBeVisible();
        await expect(page.locator('.ant-table').first()).toBeVisible();
        await page.waitForTimeout(300);
        await expectNoHorizontalOverflow(page);

        const btn = page.locator('button:has-text("保存画像")');
        await expect(btn).toBeVisible();
        await btn.click();
        await expect(page.locator('.ant-modal-content')).toBeVisible();
        await expect(page.locator('text=隐私提示')).toBeVisible();
        await expectNoHorizontalOverflow(page);
        await page.locator('.ant-modal-close').click();

        await page.screenshot({ path: `test-results/screenshots/result-${vp.name}.png`, fullPage: true });
      });

      test('账户页列表与操作按钮可操作且无横向溢出', async ({ page }) => {
        await page.addInitScript((user) => {
          window.localStorage.setItem('auth_user', JSON.stringify(user));
        }, NORMAL_USER);
        await page.route('**/api/auth/me', (route) => route.fulfill({
          status: 200, contentType: 'application/json', body: JSON.stringify(NORMAL_USER),
        }));
        await page.route('**/api/my/recommendations', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ records: [{ id: 1, profile: {}, result: RECOMMENDATION, created_at: '2026-08-11T10:00:00' }] }),
        }));
        await page.route('**/api/my/profiles', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ profiles: [{ id: 1, name: '2026年家庭保障方案', profile: {}, note: null, created_at: '2026-08-11T10:00:00' }] }),
        }));

        await page.goto('/account');
        await expect(page.locator('text=我的账户')).toBeVisible({ timeout: 15000 });
        await expect(page.getByText('推荐历史', { exact: true })).toBeVisible();
        await expect(page.locator('text=保存的画像')).toBeVisible();
        await expect(page.locator('button:has-text("加载到表单")')).toBeVisible();
        await expect(page.locator('button:has-text("编辑")')).toBeVisible();
        await expect(page.locator('button:has-text("删除")').last()).toBeVisible();
        await page.waitForTimeout(300);
        await expectNoHorizontalOverflow(page);
        await page.screenshot({ path: `test-results/screenshots/account-${vp.name}.png`, fullPage: true });
      });

      test('后台产品管理页面与抽屉适配视口宽度', async ({ page }) => {
        await page.addInitScript((user) => {
          window.localStorage.setItem('auth_user', JSON.stringify(user));
        }, ADMIN_USER);
        await page.route(/\/api\/products(\?.*)?$/, (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({
            total: 1, page: 1, page_size: 20,
            products: [{ id: 1, name: '平安福终身寿险', company: '中国平安', type: '重疾险', status: 1, premium_min: 5000, premium_max: 20000, sum_insured_max: 100 }],
          }),
        }));
        await page.route('**/api/admin/ingestion/status', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ source_platforms: 2, source_pages: 3, crawl_jobs: 1, crawl_runs: 2, raw_documents: 5, product_drafts: 4, review_tasks: 2 }),
        }));
        await page.route('**/api/admin/ingestion/platforms', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ platforms: [{ id: 1, name: '中国保险行业协会', platform_type: 'official', base_url: 'https://example.com', robots_url: null, rate_limit_seconds: 1, is_active: true }] }),
        }));
        await page.route('**/api/admin/ingestion/source-pages', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ pages: [{ id: 1, platform_id: 1, url: 'https://example.com/p1', page_type: 'product', is_active: true, last_crawled_at: null }] }),
        }));
        await page.route('**/api/admin/ingestion/jobs', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ jobs: [{ id: 1, name: '每日抓取', source_page_id: 1, status: 'idle' }] }),
        }));
        await page.route('**/api/admin/ingestion/runs', (route) => route.fulfill({
          status: 200, contentType: 'application/json', body: JSON.stringify({ runs: [] }),
        }));
        await page.route('**/api/admin/ingestion/review-tasks', (route) => route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ tasks: [{ id: 1, product_draft_id: 1, status: 'pending', reviewer_id: null, draft_name: '测试产品', draft_type: '医疗险', confidence: 0.92, created_at: '2026-08-11T00:00:00' }] }),
        }));

        await page.goto('/admin');
        await expect(page.locator('text=产品管理').first()).toBeVisible({ timeout: 15000 });
        await expect(page.locator('button:has-text("新增产品")')).toBeVisible();
        await page.waitForTimeout(300);
        await expectNoHorizontalOverflow(page);

        const openDrawerAndCheck = async (buttonText: string) => {
          await page.locator(`button:has-text("${buttonText}")`).first().click();
          const drawer = page.locator('.ant-drawer-content').last();
          await expect(drawer).toBeVisible();
          const box = await drawer.boundingBox();
          expect(box).not.toBeNull();
          expect(box!.width, '抽屉宽度不得超过视口').toBeLessThanOrEqual(vp.viewport.width + 1);
          await page.waitForTimeout(200);
          await expectNoHorizontalOverflow(page);
          await page.keyboard.press('Escape');
          await expect(drawer).toBeHidden();
        };

        await openDrawerAndCheck('新增产品');
        await page.locator('.ant-tabs-tab', { hasText: '数据采集' }).click();
        await expect(page.locator('button:has-text("新增平台")')).toBeVisible();
        await page.locator('button:has-text("新增平台")').click();
        const platformDrawer = page.locator('.ant-drawer-content').last();
        await expect(platformDrawer).toBeVisible();
        const pbox = await platformDrawer.boundingBox();
        expect(pbox).not.toBeNull();
        expect(pbox!.width, '平台抽屉宽度不得超过视口').toBeLessThanOrEqual(vp.viewport.width + 1);
        await page.waitForTimeout(200);
        await expectNoHorizontalOverflow(page);
        await page.keyboard.press('Escape');

        await page.screenshot({ path: `test-results/screenshots/admin-${vp.name}.png`, fullPage: true });
      });
    });
  }
});
