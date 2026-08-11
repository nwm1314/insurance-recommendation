import { test, expect } from '@playwright/test';

test.describe('Account Page', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/account');
    await expect(page).toHaveURL(/.*login/);
  });
});
