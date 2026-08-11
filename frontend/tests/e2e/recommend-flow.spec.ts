import { test, expect, type Page } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  fillQuestionnaire,
  registerUser,
  submitRecommendation,
  uniqueEmail,
} from './helpers';

async function saveProfileFromResult(page: Page, name: string): Promise<void> {
  await page.locator('button:has-text("保存画像")').click();
  const modal = page.locator('.ant-modal-content');
  await expect(modal).toBeVisible();
  await expect(modal.getByText('隐私提示')).toBeVisible();
  await modal.locator('input[placeholder^="如："]').fill(name);
  await modal.getByRole('button', { name: /保\s*存/ }).click();
  await expect(page.locator('text=画像已保存，可在“我的账户”中管理')).toBeVisible({ timeout: 10000 });
  await expect(modal).toBeHidden();
}

test.describe('推荐关键旅程（真实后端）', () => {
  test('注册→问卷→推荐→保存画像→历史恢复→画像回填→删除', async ({ page }) => {
    test.setTimeout(180000);
    const email = uniqueEmail('journey');
    const profileName = `旅程画像-${Date.now()}`;

    // 1. 注册并登录
    await registerUser(page, email);

    // 2. 问卷四步 → 提交推荐（真实 rule engine）
    await fillQuestionnaire(page);
    await submitRecommendation(page);
    await expect(page.getByText('极速规则模式')).toBeVisible();
    await expect(page.locator('.ant-tabs-tab').first()).toBeVisible();
    await expect(page.locator('.ant-table').first()).toBeVisible();

    // 3. 结果页保存画像（隐私提示 → 命名 → 保存）
    await saveProfileFromResult(page, profileName);

    // 4. 账户页：推荐历史与画像均由后端持久化
    // （StrictMode 双挂载可能产生重复记录，取首条即可）
    await page.goto('/account');
    await expect(page.locator('.ant-card-head-title', { hasText: '推荐历史' })).toBeVisible();
    await expect(page.locator('a:has-text("查看结果")').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.ant-list-item').filter({ hasText: profileName })).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();

    // 5. 历史恢复：recordId 经后端加载
    let historyDetailRequests = 0;
    page.on('request', (request) => {
      const pathname = new URL(request.url()).pathname;
      if (request.method() === 'GET' && /^\/api\/my\/recommendations\/\d+$/.test(pathname)) {
        historyDetailRequests += 1;
      }
    });
    await page.locator('a:has-text("查看结果")').first().click();
    await expect(page).toHaveURL(/\/result\?recordId=\d+/);
    await expect(page.locator('text=推荐方案').first()).toBeVisible({ timeout: 60000 });
    await expect(page.locator('text=横向对比')).toBeVisible();
    await expect.poll(() => historyDetailRequests, { timeout: 10000 }).toBe(1);

    // 6. 画像回填：加载到表单 → 首页预填年龄 30
    await page.goto('/account');
    const profileItem = page.locator('.ant-list-item').filter({ hasText: profileName });
    await profileItem.getByRole('button', { name: /加载到表单/ }).click();
    await expect(page).toHaveURL(/\?profileId=\d+/);
    await expect(page.locator('text=已加载保存的画像').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('input#age')).toHaveValue('30');

    // 7. 删除画像（账户页删除为直接调用，无 Popconfirm）
    await page.goto('/account');
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    const item = page.locator('.ant-list-item').filter({ hasText: profileName });
    await item.getByRole('button', { name: /删\s*除/ }).click();
    await expect(page.locator('text=画像已删除')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.ant-list-item').filter({ hasText: profileName })).toHaveCount(0);
  });
});

const MOBILE_VIEWPORTS = [
  { name: '320px', width: 320, height: 568 },
  { name: '375px', width: 375, height: 667 },
];

for (const vp of MOBILE_VIEWPORTS) {
  test.describe(`移动视口 ${vp.name}（真实后端）`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test('问卷→推荐→结果页完整渲染且无横向溢出', async ({ page }) => {
      test.setTimeout(120000);
      const email = uniqueEmail(`mobile-${vp.width}`);
      await registerUser(page, email);
      await fillQuestionnaire(page);
      await submitRecommendation(page);
      await expectNoHorizontalOverflow(page);

      await page.locator('button:has-text("保存画像")').click();
      await expect(page.locator('.ant-modal-content')).toBeVisible();
      await expect(page.locator('text=隐私提示')).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.locator('.ant-modal-close').click();

      await page.goto('/account');
      await expect(page.locator('text=我的账户')).toBeVisible({ timeout: 20000 });
      await expect(page.locator('a:has-text("查看结果")').first()).toBeVisible({ timeout: 10000 });
      await expect(page.locator('text=保存的画像')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  });
}
