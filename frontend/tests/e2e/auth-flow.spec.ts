import { test, expect } from '@playwright/test';
import { loginUser, logout, registerUser, uniqueEmail } from './helpers';

test.describe('认证与权限边界（真实后端）', () => {
  test('注册成为普通用户：角色为 user 且无管理后台入口', async ({ page }) => {
    test.setTimeout(60000);
    const email = uniqueEmail('reg');
    await registerUser(page, email);

    await expect(page.locator('text=我的账户')).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
    // TASK-022: 公开注册恒为普通用户，不再首用户提权
    await expect(page.locator('.ant-tag').getByText('user', { exact: true })).toBeVisible();
    await expect(page.locator('a:has-text("管理后台")')).toHaveCount(0);
  });

  test('错误密码登录被拒绝：错误提示可见、不建立会话、不整页刷新', async ({ page }) => {
    test.setTimeout(60000);
    const email = uniqueEmail('badpwd');
    await registerUser(page, email);
    await logout(page);

    await page.locator('input#email').fill(email);
    await page.locator('input#password').fill('WrongPass#999');
    await page.getByRole('button', { name: /登\s*录/ }).click();
    // TASK-028: 401 拦截器已排除 /auth/login，错误提示不再被整页刷新清空
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText('邮箱或密码错误')).toBeVisible();
    await expect(page.locator('input#email')).toHaveValue(email);
    await expect(page.locator('a:has-text("我的账号")')).toHaveCount(0);
  });

  test('会话过期仍跳转登录页（其他接口 401 行为不变）', async ({ page }) => {
    test.setTimeout(60000);
    const email = uniqueEmail('expiry');
    await registerUser(page, email);
    await logout(page);
    // 清除 Cookie 模拟会话过期，访问受保护页应被 401 拦截并跳转 /login
    await page.context().clearCookies();
    await page.goto('/account');
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('text=登录账号')).toBeVisible();
  });

  test('正确登录回到账户页；普通用户访问 /admin 被重定向', async ({ page }) => {
    test.setTimeout(60000);
    const email = uniqueEmail('rbac');
    await registerUser(page, email);
    await logout(page);
    await loginUser(page, email);

    await page.goto('/admin');
    // ProtectedRoute 无 crawl:read 权限 → 重定向 /account
    await expect(page).toHaveURL(/\/account/);
    await expect(page.locator('text=我的账户')).toBeVisible();
  });
});
