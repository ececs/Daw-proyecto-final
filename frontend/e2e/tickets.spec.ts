import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers/auth';

test.describe('Ticket Lifecycle (CRUD & Kanban)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsDemo(page);
  });

  test('Successful ticket creation in the system', async ({ page }) => {
    const newTicketButton = page.locator('button:has-text("New ticket")');
    await expect(newTicketButton).toBeVisible();
    await newTicketButton.click();

    const modalTitle = page.locator('h2:has-text("New ticket")');
    await expect(modalTitle).toBeVisible();

    const uniqueTitle = `Playwright E2E - ${Date.now()}`;
    await page.locator('#tf-title').fill(uniqueTitle);
    await page.locator('#tf-description').fill('Detailed description automatically created by Playwright E2E tests.');
    await page.locator('#tf-client-url').fill('https://example.com');
    await page.locator('#tf-client-summary').fill('Financial sector client with cloud-native infrastructure.');
    await page.locator('#tf-priority').selectOption('high');

    await page.locator('button[type="submit"]:has-text("Create ticket")').click();
    await expect(modalTitle).not.toBeVisible();

    const ticketRow = page.locator(`tr:has-text("${uniqueTitle}")`);
    await expect(ticketRow).toBeVisible({ timeout: 10000 });
    await expect(ticketRow.locator('span:has-text("High")')).toBeVisible();
  });
});
