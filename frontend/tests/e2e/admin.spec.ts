import { test, expect } from '@playwright/test';

test.describe('Admin Page', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/admin');
    await expect(page).toHaveURL(/.*login/);
  });
});
