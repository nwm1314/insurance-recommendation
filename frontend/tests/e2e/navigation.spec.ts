import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('should navigate to login from home', async ({ page }) => {
    await page.goto('/');
    await page.locator('text=登录/注册').click();
    await expect(page).toHaveURL(/.*login/);
  });

  test('should navigate to result page', async ({ page }) => {
    await page.goto('/result');
    await expect(page.locator('text=请先填写问卷信息')).toBeVisible();
  });
});
