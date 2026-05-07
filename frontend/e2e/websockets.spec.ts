import { test, expect } from '@playwright/test';

test.describe('Sincronización en Tiempo Real (WebSockets)', () => {

  test('Dos contextos en paralelo: Crear ticket en Ventana A y verificar aparición inmediata en Ventana B', async ({ browser }) => {
    // 1. Crear y configurar la Ventana A (Contexto A)
    const contextA = await browser.newContext();
    const pageA = await contextA.newPage();
    
    await pageA.goto('/login');
    await pageA.locator('#demo-code').fill('Orbidi@2026Xdesafio');
    await pageA.locator('button[type="submit"]').click();
    await pageA.waitForURL(/\/board/);
    await expect(pageA.locator('table')).toBeVisible();

    // 2. Crear y configurar la Ventana B (Contexto B)
    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    
    await pageB.goto('/login');
    await pageB.locator('#demo-code').fill('Orbidi@2026Xdesafio');
    await pageB.locator('button[type="submit"]').click();
    await pageB.waitForURL(/\/board/);
    await expect(pageB.locator('table')).toBeVisible();

    // Generamos un título de ticket único
    const uniqueTitle = `WS Sync Test - ${Date.now()}`;

    // 3. Crear el ticket en la Ventana A
    const newTicketButton = pageA.locator('button:has-text("New ticket")');
    await newTicketButton.click();
    await pageA.locator('#tf-title').fill(uniqueTitle);
    await pageA.locator('#tf-description').fill('Ticket para verificar la sincronización por WebSockets.');
    await pageA.locator('button[type="submit"]:has-text("Create ticket")').click();

    // Verificamos que aparece en la Ventana A
    await expect(pageA.locator(`tr:has-text("${uniqueTitle}")`)).toBeVisible({ timeout: 10000 });

    // 4. Verificamos que aparece AUTOMÁTICAMENTE en la Ventana B (sin recargar la página)
    await expect(pageB.locator(`tr:has-text("${uniqueTitle}")`)).toBeVisible({ timeout: 10000 });

    // Cerramos ambos contextos
    await contextA.close();
    await contextB.close();
  });
});
