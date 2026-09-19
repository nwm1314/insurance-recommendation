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
  // 第 2 步：职业。STEP_FIELDS[1] 要求 job_class 或 occupation_name 二者其一，
  // 不填则 handleNext 校验失败、步骤不会前进（后续断言会误判为"元素不可见"）。
  await expect(page.locator('input#occupation_name')).toBeVisible();
  await page.locator('input#occupation_name').fill('软件工程师');
  if (opts.commercialCoverage) {
    await page.locator('.ant-checkbox-wrapper', { hasText: '已有商业保险' }).click();
  }
  await page.locator('button:has-text("下一步")').click();
  // 第 3 步：健康。以**真实可见**的单选项作为锚点——AntD 的 label 元素在本页
  // 布局下盒模型为 0×0，用 text= 断言 label 会命中不可见元素而恒失败（DEV-003）。
  await expect(page.locator('.ant-radio-button-wrapper', { hasText: '标准体（无异常）' })).toBeVisible();
  await page.locator('button:has-text("下一步")').click();
  await expect(page.locator('button:has-text("开始推荐")')).toBeVisible();
}

export async function submitRecommendation(page: Page): Promise<void> {
  await page.locator('button:has-text("开始推荐")').click();
  await expect(page.locator('text=推荐方案').first()).toBeVisible({ timeout: 60000 });
  // 精确匹配"横向对比"卡片标题：结果页的"下一步怎么做"文案正文会提到该卡片，
  // 用宽松的 text= 选择器会命中多个元素而触发 strict mode violation。
  await expect(page.getByText('横向对比', { exact: true })).toBeVisible();
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
