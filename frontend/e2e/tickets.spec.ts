import { test, expect } from '@playwright/test';

test.describe('Ciclo de Vida del Ticket (CRUD & Kanban)', () => {

  test.beforeEach(async ({ page }) => {
    // Iniciamos sesión con el usuario demo antes de cada test
    await page.goto('/login');
    const codeInput = page.locator('#demo-code');
    await codeInput.fill('Orbidi@2026Xdesafio');
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    await page.waitForURL(/\/board/);
  });

  test('Creación de ticket exitosa en el sistema', async ({ page }) => {
    // Buscamos y hacemos clic en el botón "New ticket"
    const newTicketButton = page.locator('button:has-text("New ticket")');
    await expect(newTicketButton).toBeVisible();
    await newTicketButton.click();

    // Verificamos que el modal del formulario se haya abierto
    const modalTitle = page.locator('h2:has-text("New ticket")');
    await expect(modalTitle).toBeVisible();

    // Rellenamos el título del ticket (ID: #tf-title)
    const titleInput = page.locator('#tf-title');
    const uniqueTitle = `Playwright E2E - ${Date.now()}`;
    await titleInput.fill(uniqueTitle);

    // Rellenamos la descripción (ID: #tf-description)
    const descInput = page.locator('#tf-description');
    await descInput.fill('Descripción detallada creada automáticamente por los tests de Playwright.');

    // Rellenamos el sitio web del cliente (ID: #tf-client-url)
    const urlInput = page.locator('#tf-client-url');
    await urlInput.fill('https://example.com');

    // Rellenamos el contexto del negocio (ID: #tf-client-summary)
    const summaryInput = page.locator('#tf-client-summary');
    await summaryInput.fill('Cliente del sector financiero con infraestructura en la nube.');

    // Seleccionamos prioridad Alta (ID: #tf-priority)
    const prioritySelect = page.locator('#tf-priority');
    await prioritySelect.selectOption('high');

    // Enviamos el formulario
    const submitFormButton = page.locator('button[type="submit"]:has-text("Create ticket")');
    await submitFormButton.click();

    // Verificamos que el modal se cierre correctamente
    await expect(modalTitle).not.toBeVisible();

    // Verificamos que el ticket recién creado aparezca en la lista
    const ticketRow = page.locator(`tr:has-text("${uniqueTitle}")`);
    await expect(ticketRow).toBeVisible({ timeout: 10000 });
    
    // Verificamos que tenga la prioridad "High" reflejada correctamente en la fila
    await expect(ticketRow.locator('span:has-text("High")')).toBeVisible();
  });
});
