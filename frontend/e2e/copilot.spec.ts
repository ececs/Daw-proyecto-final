import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers/auth';

test.describe('AI Assistant (Copilot)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsDemo(page);
  });

  test('Basic interaction with the Copilot AI assistant', async ({ page }) => {
    await page.locator('button[aria-label="Toggle AI assistant"]').click();
    await expect(page.locator('p:has-text("AI Assistant")')).toBeVisible();

    const chatInput = page.locator('textarea[aria-label="Mensaje para el asistente"]');
    await expect(chatInput).toBeVisible();

    const assistantMessages = page.locator('div.bg-slate-100');
    const previousCount = await assistantMessages.count();

    await chatInput.fill('Hello assistant, how can you help me today?');
    await page.locator('button[aria-label="Enviar mensaje"]').click();

    await expect(assistantMessages).toHaveCount(previousCount + 1, { timeout: 15000 });
    await expect(assistantMessages.nth(previousCount)).toBeVisible();
  });
});
