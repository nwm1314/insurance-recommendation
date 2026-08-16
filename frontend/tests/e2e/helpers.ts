import { expect, type Page } from '@playwright/test';

export const E2E_ADMIN_EMAIL = 'e2e-admin@e2e-test.com';
export const E2E_ADMIN_PASSWORD = 'E2eAdmin!2026';
export const E2E_USER_PASSWORD = 'Passw0rd!123';

export function uniqueEmail(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now()}-${rand}@e2e-test.com`;
}

export async function registerUser(page: Page, email: string): Promise<void> {
  await page.goto('/register');
  await page.locator('input#full_name').fill('E2E 用户');
  await page.locator('input#email').fill(email);
  await page.locator('input#password').fill(E2E_USER_PASSWORD);
  await page.getByRole('button', { name: /注\s*册/ }).click();
  await expect(page).toHaveURL(/\/account/);
  await expect(page.locator('text=我的账户')).toBeVisible({ timeout: 20000 });
}

export async function loginUser(page: Page, email: string, password = E2E_USER_PASSWORD): Promise<void> {
  await page.goto('/login');
  await page.locator('input#email').fill(email);
  await page.locator('input#password').fill(password);
  await page.getByRole('button', { name: /登\s*录/ }).click();
  await expect(page).toHaveURL(/\/account/);
  await expect(page.locator('text=我的账户')).toBeVisible({ timeout: 20000 });
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: /退出登录/ }).click();
  await expect(page).toHaveURL(/\/login/);
}

export async function fillQuestionnaire(
  page: Page,
  age = '30',
  opts: { commercialCoverage?: boolean } = {},
): Promise<void> {
  await page.goto('/');
  await expect(page.locator('text=智能保险推荐').first()).toBeVisible();
  await page.locator('input#age').fill(age);
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('text=职业类别')).toBeVisible();
  if (opts.commercialCoverage) {
    await page.locator('.ant-checkbox-wrapper', { hasText: '已有商业保险' }).click();
  }
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('text=健康状态')).toBeVisible();
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('button:has-text("开始推荐")')).toBeVisible();
}

export async function submitRecommendation(page: Page): Promise<void> {
  await page.locator('button:has-text("开始推荐")').click();
  await expect(page.locator('text=推荐方案').first()).toBeVisible({ timeout: 60000 });
  await expect(page.locator('text=横向对比')).toBeVisible();
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
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
