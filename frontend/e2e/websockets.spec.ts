import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers/auth';

test.describe('Real-Time Synchronization (WebSockets)', () => {
  test('Two parallel contexts: Create ticket in Window A and verify immediate appearance in Window B', async ({ browser }) => {
    const contextA = await browser.newContext();
    const pageA = await contextA.newPage();
    await loginAsDemo(pageA);
    await expect(pageA.locator('table')).toBeVisible();

    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    await loginAsDemo(pageB);
    await expect(pageB.locator('table')).toBeVisible();

    const uniqueTitle = `WS Sync Test - ${Date.now()}`;

    await pageA.locator('button:has-text("New ticket")').click();
    await pageA.locator('#tf-title').fill(uniqueTitle);
    await pageA.locator('#tf-description').fill('Ticket to verify real-time WebSocket synchronization.');
    await pageA.locator('button[type="submit"]:has-text("Create ticket")').click();

    await expect(pageA.locator(`tr:has-text("${uniqueTitle}")`)).toBeVisible({ timeout: 10000 });
    await expect(pageB.locator(`tr:has-text("${uniqueTitle}")`)).toBeVisible({ timeout: 10000 });

    await contextA.close();
    await contextB.close();
  });
});
