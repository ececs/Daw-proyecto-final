import { test, expect } from '@playwright/test';

test.describe('Interacción Social (Comentarios y Adjuntos)', () => {

  test.beforeEach(async ({ page }) => {
    // Iniciamos sesión con el usuario demo antes de cada test
    await page.goto('/login');
    const codeInput = page.locator('#demo-code');
    await codeInput.fill('Orbidi@2026Xdesafio');
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    await page.waitForURL(/\/board/);
  });

  test('Añadir y visualizar un comentario en el detalle del ticket', async ({ page }) => {
    // Esperamos a que la tabla de tickets sea visible
    const table = page.locator('table');
    await expect(table).toBeVisible({ timeout: 10000 });

    // Hacemos clic en el primer ticket disponible de la tabla para abrir su detalle
    const firstTicketLink = page.locator('table tbody tr td a').first();
    await expect(firstTicketLink).toBeVisible();
    await firstTicketLink.click();

    // Verificamos que se haya cargado la página de detalle del ticket (/tickets/[id])
    await page.waitForURL(/\/tickets\//);
    const detailHeader = page.locator('h1');
    await expect(detailHeader).toBeVisible();

    // Buscamos el área de texto para escribir el comentario
    const commentTextarea = page.locator('textarea[aria-label="Escribir un comentario"]');
    await expect(commentTextarea).toBeVisible();

    // Generamos un mensaje único para evitar colisiones
    const uniqueComment = `Test comentario automático Playwright - ${Date.now()}`;
    await commentTextarea.fill(uniqueComment);

    // Enviamos el comentario
    const sendButton = page.locator('button[aria-label="Enviar comentario"]');
    await sendButton.click();

    // Comprobamos que el comentario recién añadido aparece en la interfaz
    const commentElement = page.locator(`p:has-text("${uniqueComment}")`);
    await expect(commentElement).toBeVisible({ timeout: 5000 });
  });
});
