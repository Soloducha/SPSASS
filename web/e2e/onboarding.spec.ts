import { test, expect } from '@playwright/test';

test.describe('Onboarding flow - UI validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/onboarding');
    await expect(page.locator('h2')).toContainText('Registro');
  });

  test('shows progress indicator with 6 steps', async ({ page }) => {
    await expect(page.locator('nav[aria-label="Pasos del onboarding"]')).toBeVisible();
    // Check step labels in the progress indicator (hidden on mobile, visible on desktop)
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=Registro')).toBeVisible();
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=Servidor')).toBeVisible();
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=API Key')).toBeVisible();
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=Instrucciones')).toBeVisible();
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=Verificación')).toBeVisible();
    await expect(page.locator('nav[aria-label="Pasos del onboarding"] >> text=¡Listo!')).toBeVisible();
  });

  test('shows validation error when submitting empty form', async ({ page }) => {
    await page.click('button:has-text("Siguiente →")');
    // Server-side validation will show error - wait for any alert
    await expect(page.locator('[role="alert"]')).toBeVisible({ timeout: 10000 });
  });

  test('shows step labels and descriptions', async ({ page }) => {
    await expect(page.locator('text=Crea tu tenant y usuario admin')).toBeVisible();
    await expect(page.locator('input[name="tenantName"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
  });

  test('password field has min length validation', async ({ page }) => {
    await page.fill('input[name="tenantName"]', 'Test');
    await page.fill('input[name="email"]', 'test@test.com');
    await page.fill('input[name="password"]', '123');
    await page.click('button:has-text("Siguiente →")');
    await expect(page.locator('[role="alert"]')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Invitations flow - UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/invitations');
  });

  test('shows invitations page with create button', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Invitaciones');
    await expect(page.locator('button:has-text("Nueva invitación")')).toBeVisible();
  });

  test('opens create invitation dialog', async ({ page }) => {
    await page.click('button:has-text("Nueva invitación")');
    // Dialog title
    await expect(page.locator('#create-invitation-title')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('select[name="role"]')).toBeVisible();
  });

  test('dialog has role options', async ({ page }) => {
    await page.click('button:has-text("Nueva invitación")');
    const select = page.locator('select[name="role"]');
    await expect(select.locator('option[value="member"]')).toHaveText('Miembro');
    await expect(select.locator('option[value="admin"]')).toHaveText('Administrador');
    await expect(select.locator('option[value="viewer"]')).toHaveText('Visor');
  });

  test('can close dialog with cancel button', async ({ page }) => {
    await page.click('button:has-text("Nueva invitación")');
    await expect(page.locator('#create-invitation-title')).toBeVisible();
    await page.click('button:has-text("Cancelar")');
    await expect(page.locator('#create-invitation-title')).not.toBeVisible({ timeout: 5000 });
  });

  test('can close dialog with X button', async ({ page }) => {
    await page.click('button:has-text("Nueva invitación")');
    await expect(page.locator('#create-invitation-title')).toBeVisible();
    await page.click('button[aria-label="Cerrar"]');
    await expect(page.locator('#create-invitation-title')).not.toBeVisible({ timeout: 5000 });
  });
});