import { test, expect } from '@playwright/test';

test.describe('Login Page', () => {
  test('should load login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=登录账号')).toBeVisible();
  });

  test('should show validation errors', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: /登\s*录/ }).click();
    await expect(page.locator('text=请输入邮箱')).toBeVisible();
  });
});
