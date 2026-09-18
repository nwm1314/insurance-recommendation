import { test, expect } from '@playwright/test';

test.describe('Home Page', () => {
  test('should load home page with form', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=智能保险推荐').first()).toBeVisible();
    await expect(page.locator('text=填写问卷')).toBeVisible();
  });

  test('should navigate through form steps', async ({ page }) => {
    await page.goto('/');

    // Step 0: Basic info
    await expect(page.locator('text=基本信息')).toBeVisible();

    // Fill age
    await page.locator('input#age').fill('30');

    // Go to next step
    await page.locator('button:has-text("下一步")').click();

    // Step 1: Income & Occupation
    // 以真实可见的输入控件作为锚点：AntD 的 Form.Item label 在本页布局下盒模型为
    // 0×0，用 text= 断言 label 会命中不可见元素（DEV-003）。
    await expect(page.locator('input#occupation_name')).toBeVisible();
  });
});
