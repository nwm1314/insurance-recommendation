import { test, expect, devices } from '@playwright/test';

const MOBILE_VIEWPORTS = [
  { name: 'iPhone SE (320px)', viewport: { width: 320, height: 568 } },
  { name: 'iPhone 14 (375px)', viewport: { width: 375, height: 667 } },
];

for (const vp of MOBILE_VIEWPORTS) {
  test.describe(`Mobile key paths @ ${vp.name}`, () => {
    test.use({ viewport: vp.viewport });

    test('问卷首页在窄屏可填写', async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('text=智能保险推荐').first()).toBeVisible();
      const ageInput = page.locator('input#age, .ant-input-number-input').first();
      await expect(ageInput).toBeVisible();
      await ageInput.fill('30');
      await expect(ageInput).toHaveValue('30');
      const next = page.locator('button:has-text("下一步")');
      await expect(next).toBeVisible();
    });

    test('汉堡菜单在窄屏可见且可打开', async ({ page }) => {
      await page.goto('/');
      const burger = page.locator('.mobile-menu-button');
      await expect(burger).toBeVisible();
      await burger.click();
      await expect(page.locator('.mobile-drawer')).toBeVisible();
      await expect(page.locator('.mobile-drawer').getByText('填写问卷')).toBeVisible();
    });

    test('结果页空态在窄屏不溢出', async ({ page }) => {
      await page.goto('/result');
      await expect(page.locator('text=请先填写问卷信息').or(page.locator('text=推荐记录'))).toBeVisible({ timeout: 10000 });
      const body = page.locator('body');
      await body.waitFor({ state: 'attached' });
      await page.waitForTimeout(300);
      const overflow = await body.evaluate((el) => el.scrollWidth > el.clientWidth + 2);
      expect(overflow).toBe(false);
    });

    test('账户页在窄屏可访问（未登录跳转或页面渲染）', async ({ page }) => {
      await page.goto('/account');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('body')).toBeVisible();
    });
  });
}

test.describe('Desktop key path', () => {
  test.use({ viewport: { width: 1280, height: 720 } });

  test('桌面问卷首步正常', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=基本信息')).toBeVisible();
    await expect(page.locator('.mobile-menu-button')).toBeHidden();
  });
});
