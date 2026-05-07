import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers/auth';

test.describe('Authentication and Route Protection (Auth)', () => {
  test('Route protection: Automatically redirects to /login if unauthenticated', async ({ page }) => {
    await page.goto('/board');
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('h1')).toContainText('D4-Ticket AI');
  });

  test('Successful Login: Access with demo code and session persistence', async ({ page }) => {
    await loginAsDemo(page);

    const header = page.locator('header');
    await expect(header).toBeVisible();

    await page.reload();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/board/);
  });
});
