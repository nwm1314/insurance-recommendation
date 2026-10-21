import { test, expect } from '@playwright/test';

/**
 * 界面语言切换（i18n）的回归用例。
 *
 * 关键约束：默认语言由浏览器语言决定，Playwright 固定 locale=zh-CN，所以
 * 不带参数访问必须是中文界面——既有的中文断言都依赖这一点。
 */
test.describe('界面语言切换', () => {
  test('?lang=en 直接进入英文界面，切换按钮回到中文', async ({ page }) => {
    await page.goto('/?lang=en');

    await expect(page.getByRole('heading', { name: 'Insurance Advisor' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Questionnaire' })).toBeVisible();
    // 产品/险种等目录数据保持中文（这里是问卷的年龄标签，属于界面文案，应为英文）
    await expect(page.getByText('One minute', { exact: false })).toBeVisible();

    await page.getByRole('button', { name: /Switch language/ }).click();

    await expect(page.getByRole('heading', { name: '智能保险推荐' })).toBeVisible();
    await expect(page.getByRole('link', { name: '填写问卷' })).toBeVisible();
  });

  test('默认（zh-CN 浏览器）为中文界面，切换后英文登录页可用', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: '智能保险推荐' })).toBeVisible();

    await page.getByRole('button', { name: /Switch language/ }).click();
    await page.getByRole('link', { name: 'Sign in' }).click();

    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Sign in/ })).toBeVisible();
  });
});
