import { test, expect } from '@playwright/test';

test.describe('Asistente de IA (Copilot)', () => {

  test.beforeEach(async ({ page }) => {
    // Iniciamos sesión con el usuario demo antes de cada test
    await page.goto('/login');
    const codeInput = page.locator('#demo-code');
    await codeInput.fill('Orbidi@2026Xdesafio');
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    await page.waitForURL(/\/board/);
  });

  test('Interacción básica con el asistente de IA Copilot', async ({ page }) => {
    // Buscamos y hacemos clic en el botón de alternancia del chat de IA
    const chatToggle = page.locator('button[aria-label="Toggle AI assistant"]');
    await expect(chatToggle).toBeVisible();
    await chatToggle.click();

    // Verificamos que el panel del chat flutuante de la IA se haya abierto
    const assistantHeader = page.locator('p:has-text("AI Assistant")');
    await expect(assistantHeader).toBeVisible();

    // Buscamos la caja de entrada para el mensaje del asistente
    const chatInput = page.locator('textarea[aria-label="Mensaje para el asistente"]');
    await expect(chatInput).toBeVisible();

    // Escribimos una consulta simple al asistente
    await chatInput.fill('Hola asistente, ¿en qué me puedes ayudar?');

    // Hacemos clic en el botón para enviar el mensaje
    const sendButton = page.locator('button[aria-label="Enviar mensaje"]');
    await sendButton.click();

    // El asistente debería comenzar a pensar ("Thinking...") y luego mostrar el contenido de respuesta
    // Esperamos a que aparezca un mensaje de respuesta del asistente diferente de vacío
    const responseBubble = page.locator('div.bg-slate-100:has-text("Hi")');
    await expect(responseBubble).toBeVisible({ timeout: 15000 });
  });
});
