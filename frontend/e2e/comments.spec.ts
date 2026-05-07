import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers/auth';

test.describe('Social Interaction (Comments & Attachments)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsDemo(page);
  });

  test('Add and view a comment in the ticket detail view', async ({ page }) => {
    const firstTicketRow = page.locator('table tbody tr').first();
    const hasTicket = await firstTicketRow.isVisible();

    if (!hasTicket) {
      const newTicketButton = page.locator('button:has-text("New ticket")');
      await expect(newTicketButton).toBeVisible();
      await newTicketButton.click();

      const uniqueTitle = `Comments Test Ticket - ${Date.now()}`;
      await page.locator('#tf-title').fill(uniqueTitle);
      await page.locator('#tf-description').fill('Automatically created comments test ticket.');
      await page.locator('button[type="submit"]:has-text("Create ticket")').click();

      const modalTitle = page.locator('h2:has-text("New ticket")');
      await expect(modalTitle).not.toBeVisible({ timeout: 10000 });

      const ticketRow = page.locator(`tr:has-text("${uniqueTitle}")`);
      await expect(ticketRow).toBeVisible({ timeout: 10000 });
      await ticketRow.locator('span.font-medium').first().click();
    } else {
      await firstTicketRow.locator('span.font-medium').first().click();
    }

    await page.waitForURL(/\/tickets\//);
    await expect(page.locator('h1')).toBeVisible();

    const commentTextarea = page.locator('textarea[aria-label="Escribir un comentario"]');
    await expect(commentTextarea).toBeVisible();

    const uniqueComment = `Playwright automated test comment - ${Date.now()}`;
    await commentTextarea.fill(uniqueComment);

    await page.locator('button[aria-label="Enviar comentario"]').click();
    await expect(page.locator(`p:has-text("${uniqueComment}")`)).toBeVisible({ timeout: 5000 });
  });
});
