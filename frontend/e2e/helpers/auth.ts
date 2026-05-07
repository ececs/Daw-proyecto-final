import { expect, type Page } from '@playwright/test';

const DEMO_CODE = process.env.PLAYWRIGHT_DEMO_CODE;

export async function loginAsDemo(page: Page) {
  if (!DEMO_CODE) {
    throw new Error('PLAYWRIGHT_DEMO_CODE is not set. Export it before running the E2E suite.');
  }

  await page.goto('/login');

  const codeInput = page.locator('#demo-code');
  await expect(codeInput).toBeVisible();
  await codeInput.fill(DEMO_CODE);

  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/board/);
  await expect(page).toHaveURL(/\/board/);
}
