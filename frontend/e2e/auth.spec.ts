import { test, expect } from '@playwright/test';

test.describe('Flujo de Acceso y Seguridad (Auth)', () => {
  
  test('Protección de rutas: Redirige automáticamente a /login si no está autenticado', async ({ page }) => {
    // Intentamos ir directamente al tablero sin iniciar sesión
    await page.goto('/board');
    
    // Debería redirigir automáticamente a /login
    await expect(page).toHaveURL(/\/login/);
    
    // Verificamos que el título principal de login sea visible
    await expect(page.locator('h1')).toContainText('D4-Ticket AI');
  });

  test('Login exitoso: Acceso correcto con código demo y persistencia de sesión', async ({ page }) => {
    // Vamos a la página de inicio de sesión
    await page.goto('/login');
    
    // Buscamos el campo del código de acceso demo
    const codeInput = page.locator('#demo-code');
    await expect(codeInput).toBeVisible();
    
    // Rellenamos el código de acceso demo correcto
    await codeInput.fill('Orbidi@2026Xdesafio');
    
    // Enviamos el formulario haciendo clic en "Access System"
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    
    // Debería redirigir al tablero (/board) tras un login exitoso
    await page.waitForURL(/\/board/, { timeout: 10000 });
    await expect(page).toHaveURL(/\/board/);
    
    // Verificamos que la interfaz del tablero se haya cargado (por ejemplo, el Kanban Board o contenedor de columnas)
    // Buscamos algún texto o elemento característico del tablero
    const header = page.locator('header');
    await expect(header).toBeVisible();
    
    // Recargamos la página para comprobar la persistencia de la sesión
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Comprobamos que seguimos en el tablero y no nos ha devuelto a login
    await expect(page).toHaveURL(/\/board/);
  });
});
