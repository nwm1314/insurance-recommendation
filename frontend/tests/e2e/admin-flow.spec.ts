import { test, expect } from '@playwright/test';
import { E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD, loginUser } from './helpers';

test.describe('管理员产品管理（真实后端）', () => {
  test('管理员登录后创建→检索→编辑→删除产品（Rule/Benefit 闭环）', async ({ page }) => {
    test.setTimeout(120000);
    await loginUser(page, E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD);

    // 管理员角色与后台入口可见
    await expect(page.locator('.ant-tag').getByText('admin', { exact: true })).toBeVisible();
    await page.locator('a:has-text("管理后台")').click();
    await expect(page.locator('text=产品管理').first()).toBeVisible({ timeout: 20000 });
    await expect(page.locator('text=权限保护已启用')).toBeVisible();

    // 真实目录种子数据已加载
    const firstRow = page.locator('.ant-table-tbody .ant-table-row').first();
    await expect(firstRow).toBeVisible({ timeout: 20000 });

    // 新增产品（含 Rule + Benefit）
    const name = `E2E产品-${Date.now()}`;
    await page.locator('button:has-text("新增产品")').click();
    const drawer = page.locator('.ant-drawer-content').last();
    await expect(drawer).toBeVisible();
    await drawer.locator('input#name').fill(name);
    await drawer.locator('input#company').fill('E2E测试公司');
    await drawer.locator('#type').click();
    await page.locator('.ant-select-item-option[title="医疗险"]').click();
    await drawer.locator('input#premium_min').fill('100');
    await drawer.locator('input#premium_max').fill('500');
    await drawer.locator('input#sum_insured_max').fill('200');
    // Rule 默认值已预填（min_age=0/max_age=100/job_class_limit=6/waiting=90）
    await expect(drawer.locator('input#rule_min_age')).toHaveValue('0');
    await expect(drawer.locator('input#rule_waiting_period_days')).toHaveValue('90');
    // Benefit 动态行
    await drawer.locator('button:has-text("添加责任")').click();
    const benefitRow = page.locator('.benefit-row').last();
    await benefitRow.locator('input[placeholder="责任名称"]').fill('住院医疗费用');
    await drawer.getByRole('button', { name: /保\s*存/ }).click();
    await expect(page.locator('text=产品已创建')).toBeVisible({ timeout: 10000 });

    // 检索新产品
    await page.locator('.admin-search input').fill(name);
    await page.locator('.admin-search input').press('Enter');
    const row = page.locator('.ant-table-row').filter({ hasText: name });
    await expect(row).toBeVisible({ timeout: 10000 });
    await expect(row.getByText('医疗险', { exact: true })).toBeVisible();
    await expect(row.getByText('在售', { exact: true })).toBeVisible();

    // 编辑：抽屉回填并保存
    await row.getByRole('button', { name: /编\s*辑/ }).click();
    const editDrawer = page.locator('.ant-drawer-content').last();
    await expect(editDrawer).toBeVisible();
    await expect(editDrawer.locator('text=编辑产品')).toBeVisible();
    await expect(editDrawer.locator('input#name')).toHaveValue(name);
    await editDrawer.locator('input#premium_min').fill('150');
    await editDrawer.getByRole('button', { name: /保\s*存/ }).click();
    await expect(page.locator('text=产品已更新')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.ant-table-row').filter({ hasText: name }).getByText('150')).toBeVisible({ timeout: 10000 });

    // 删除（Popconfirm 确认；先等搜索触发的 load() 重渲染完成，
    // 确认后列表重渲染卸载 Popconfirm，用 dispatchEvent 规避点击 detach）
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    await page.locator('.ant-table-row').filter({ hasText: name }).getByRole('button', { name: /删\s*除/ }).click();
    const confirmBtn = page.locator('.ant-popconfirm .ant-btn-primary');
    await expect(confirmBtn).toBeVisible({ timeout: 5000 });
    await confirmBtn.dispatchEvent('click');
    await expect(page.locator('text=产品已删除')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.ant-table-row').filter({ hasText: name })).toHaveCount(0);
  });

  test('数据采集页签在后端数据下正常渲染', async ({ page }) => {
    test.setTimeout(60000);
    await loginUser(page, E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD);
    await page.goto('/admin');
    await page.locator('.ant-tabs-tab', { hasText: '数据采集' }).click();
    await expect(page.locator('text=数据源平台')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('text=新增平台')).toBeVisible();
    await expect(page.locator('text=审核队列')).toBeVisible();
    // 仅在当前激活页签内断言表格（产品页签表格处于隐藏状态）
    await expect(page.locator('.ant-tabs-tabpane-active .ant-table').first()).toBeVisible();
  });
});
