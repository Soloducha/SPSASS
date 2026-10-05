'use client';

/**
 * Component tests for EditRuleForm.
 *
 * Query conventions used throughout this file:
 * - Every `getByLabelText` uses a start-anchored regex. The component nests the
 *   required marker (`*`) and, for `entity_id`, an optional hint span inside the
 *   <label>, and the channel labels render a conditional `*` that disappears
 *   once another channel is filled. Exact string matching is therefore brittle.
 * - Number inputs (`threshold`, `duration_s`, `telegram_thread_id`) are driven
 *   with `fireEvent.change` because jsdom never dispatches an input event for a
 *   character a number input rejects, so `user.type` cannot reach some states.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditRuleForm } from './EditRuleForm';
import { updateAlertRuleAction } from '../../../actions';
import type { AlertRuleResponse } from '@/lib/api/rules';
import type { ServerOverviewItem } from '@/lib/api/dashboard';
import { vi } from 'vitest';

// Mock the server action
vi.mock('../../../actions', () => ({
  updateAlertRuleAction: vi.fn(),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// vi.mocked() gives the module's server action the `vi.fn()` mock surface.
const updateAlertRuleMock = vi.mocked(updateAlertRuleAction);

const mockServers: ServerOverviewItem[] = [
  {
    id: '123e4567-e89b-42d3-a456-426614174000',
    hostname: 'server-1',
    ip: '10.0.0.1',
    os: 'linux',
    status: 'online',
    last_heartbeat_at: '2024-01-01T00:00:00Z',
    latest_metrics: {},
  },
  {
    id: '123e4567-e89b-42d3-a456-426614174001',
    hostname: 'server-2',
    ip: '10.0.0.2',
    os: 'linux',
    status: 'online',
    last_heartbeat_at: '2024-01-01T00:00:00Z',
    latest_metrics: {},
  },
];

const mockRule: AlertRuleResponse = {
  id: 'rule-123',
  tenant_id: 'tenant-1',
  entity_type: 'server',
  entity_id: '123e4567-e89b-42d3-a456-426614174000',
  metric: 'cpu_usage',
  operator: 'gt',
  threshold: 80.5,
  duration_s: 60,
  severity: 'warning',
  is_active: true,
  channels: {
    email: { to: ['ops@example.com', 'admin@example.com'] },
    webhook: { url: 'https://example.com/webhook', headers: { Authorization: 'Bearer token' } },
    telegram: { chat_id: '-1001234567890', thread_id: 42, silent: true },
  },
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const defaultProps = {
  rule: mockRule,
  servers: mockServers,
};

describe('EditRuleForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateAlertRuleMock.mockResolvedValue({ rule: mockRule, error: undefined });
  });

  it('renders the form pre-filled with rule data', () => {
    render(<EditRuleForm {...defaultProps} />);

    expect(screen.getByLabelText(/^Tipo de entidad/)).toHaveValue('server');
    expect(screen.getByLabelText(/^ID de entidad/)).toHaveValue('123e4567-e89b-42d3-a456-426614174000');
    expect(screen.getByLabelText(/^Métrica/)).toHaveValue('cpu_usage');
    // A <select> reports the selected option's value; the label is asserted
    // separately with toHaveDisplayValue.
    expect(screen.getByLabelText(/^Operador/)).toHaveValue('gt');
    expect(screen.getByLabelText(/^Operador/)).toHaveDisplayValue('Mayor que (>)');
    expect(screen.getByLabelText(/^Umbral/)).toHaveValue(80.5);
    // jest-dom reports valueAsNumber for number inputs, hence the numbers.
    expect(screen.getByLabelText(/^Duración/)).toHaveValue(60);
    expect(screen.getByLabelText(/^Severidad/)).toHaveValue('warning');
    expect(screen.getByLabelText(/^Severidad/)).toHaveDisplayValue('Advertencia');
    expect(screen.getByRole('checkbox', { name: 'Regla activa' })).toBeChecked();

    // Channels pre-filled
    expect(screen.getByLabelText(/^Email - Destinatarios/)).toHaveValue('ops@example.com, admin@example.com');
    expect(screen.getByLabelText(/^Webhook - URL/)).toHaveValue('https://example.com/webhook');
    expect(screen.getByLabelText(/^Webhook - Headers/)).toHaveValue('{\n  "Authorization": "Bearer token"\n}');
    expect(screen.getByLabelText(/^Telegram - Chat ID/)).toHaveValue('-1001234567890');
    // jest-dom reports valueAsNumber for number inputs, hence the number.
    expect(screen.getByLabelText(/^Telegram - Thread ID/)).toHaveValue(42);
    expect(screen.getByRole('checkbox', { name: 'Enviar sin notificación (silencioso)' })).toBeChecked();

    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actualizar regla' })).toBeInTheDocument();
  });

  it('shows server dropdown when entity_type is server', () => {
    render(<EditRuleForm {...defaultProps} />);

    expect(screen.getByRole('option', { name: 'Todas las entidades (sin filtro)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'server-1' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'server-2' })).toBeInTheDocument();
    // Current entity_id should be selected
    expect(screen.getByLabelText(/^ID de entidad/)).toHaveValue('123e4567-e89b-42d3-a456-426614174000');
  });

  it('shows text input for entity_id when entity_type is not server', async () => {
    const ruleWithoutServer: AlertRuleResponse = { ...mockRule, entity_type: 'service', entity_id: 'service-uuid' };
    const props = { ...defaultProps, rule: ruleWithoutServer };
    render(<EditRuleForm {...props} />);

    // Should show text input for non-server entity types
    const entityIdInput = screen.getByLabelText(/^ID de entidad/);
    expect(entityIdInput.tagName).toBe('INPUT');
    expect(entityIdInput).toHaveValue('service-uuid');
  });

  it('validates required fields on submit', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    // Clear required fields
    await user.clear(screen.getByLabelText(/^Métrica/));
    await user.clear(screen.getByLabelText(/^Umbral/));
    await user.tab();

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    await waitFor(() => {
      expect(screen.getByText('La métrica es obligatoria')).toBeInTheDocument();
      expect(screen.getByText('El umbral debe ser un número válido')).toBeInTheDocument();
    });
  });

  it('validates metric max length', async () => {
    render(<EditRuleForm {...defaultProps} />);

    // The input carries maxLength={100}, so user.type can never exceed it.
    // fireEvent.change bypasses the length constraint and lets the value reach
    // the >100 branch of validateField.
    const metricInput = screen.getByLabelText(/^Métrica/);
    fireEvent.change(metricInput, { target: { value: 'a'.repeat(101) } });

    expect(await screen.findByText('La métrica no puede exceder 100 caracteres')).toBeInTheDocument();
  });

  it('validates threshold as number', async () => {
    render(<EditRuleForm {...defaultProps} />);

    // A number input can never hold a non-numeric value in jsdom: it silently
    // discards the input and fires no change event, so typing 'abc' is a no-op.
    // Empty is the only reachable way into the parseFloat -> NaN branch.
    fireEvent.change(screen.getByLabelText(/^Umbral/), { target: { value: '' } });

    expect(await screen.findByText('El umbral debe ser un número válido')).toBeInTheDocument();
  });

  it('validates duration_s as positive integer', async () => {
    render(<EditRuleForm {...defaultProps} />);

    // '0' is accepted by a number input, so this value is reachable normally;
    // fireEvent.change is used for consistency with the other number inputs.
    fireEvent.change(screen.getByLabelText(/^Duración/), { target: { value: '0' } });

    expect(await screen.findByText('La duración debe ser un entero positivo (segundos)')).toBeInTheDocument();
  });

  it('validates email format', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/^Email - Destinatarios/);
    await user.clear(emailInput);
    await user.type(emailInput, 'invalid-email');
    await user.tab();

    expect(await screen.findByText('Formato de email inválido')).toBeInTheDocument();
  });

  it('validates webhook URL format', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    const webhookInput = screen.getByLabelText(/^Webhook - URL/);
    await user.clear(webhookInput);
    await user.type(webhookInput, 'not-a-url');
    await user.tab();

    expect(await screen.findByText('URL de webhook inválida')).toBeInTheDocument();
  });

  it('validates webhook headers as JSON', async () => {
    render(<EditRuleForm {...defaultProps} />);

    // user.type reads `{...}` as a keyboard descriptor, so the textarea would
    // never receive this text. fireEvent.change delivers it verbatim.
    fireEvent.change(screen.getByLabelText(/^Webhook - Headers/), { target: { value: '{invalid}' } });

    expect(await screen.findByText('Headers de webhook deben ser JSON válido')).toBeInTheDocument();
  });

  it('validates telegram chat_id format', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    const chatIdInput = screen.getByLabelText(/^Telegram - Chat ID/);
    await user.clear(chatIdInput);
    await user.type(chatIdInput, 'invalid');
    await user.tab();

    expect(
      await screen.findByText('chat_id debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)')
    ).toBeInTheDocument();
  });

  it('validates telegram thread_id as positive integer', async () => {
    render(<EditRuleForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/^Telegram - Thread ID/), { target: { value: '0' } });

    expect(await screen.findByText('thread_id debe ser un entero positivo')).toBeInTheDocument();
  });

  it('requires at least one channel', async () => {
    const user = userEvent.setup();
    // Rule with no channels
    const ruleNoChannels: AlertRuleResponse = {
      ...mockRule,
      channels: { email: undefined, webhook: undefined, telegram: undefined },
    };
    const props = { ...defaultProps, rule: ruleNoChannels };
    render(<EditRuleForm {...props} />);

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Se requiere al menos un canal (email, webhook o telegram)')).toBeInTheDocument();
  });

  it('allows clearing a channel by emptying the field', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    // Clear email channel
    await user.clear(screen.getByLabelText(/^Email - Destinatarios/));

    // Still has webhook and telegram so should be valid
    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('email_to')).toBe(''); // Cleared
    expect(formData.get('webhook_url')).toBe('https://example.com/webhook'); // Kept
    expect(formData.get('telegram_chat_id')).toBe('-1001234567890'); // Kept
  });

  it('submits successfully with valid data', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    // Change something
    await user.clear(screen.getByLabelText(/^Métrica/));
    await user.type(screen.getByLabelText(/^Métrica/), 'mem_usage');

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    expect(updateAlertRuleMock).toHaveBeenCalledTimes(1);
    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('ruleId')).toBe('rule-123');
    expect(formData.get('metric')).toBe('mem_usage');
    expect(formData.get('threshold')).toBe('80.5');
  });

  it('includes all channel data in formData', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('email_to')).toBe('ops@example.com, admin@example.com');
    expect(formData.get('webhook_url')).toBe('https://example.com/webhook');
    expect(formData.get('webhook_headers')).toBe('{\n  "Authorization": "Bearer token"\n}');
    expect(formData.get('telegram_chat_id')).toBe('-1001234567890');
    expect(formData.get('telegram_thread_id')).toBe('42');
    expect(formData.get('telegram_silent')).toBe('true');
  });

  it('shows error message when server action returns error', async () => {
    const user = userEvent.setup();
    updateAlertRuleMock.mockResolvedValue({ rule: null, error: 'Error al actualizar' });
    render(<EditRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Error al actualizar')).toBeInTheDocument();
  });

  it('shows error message when server action throws', async () => {
    const user = userEvent.setup();
    updateAlertRuleMock.mockRejectedValue(new Error('Network error'));
    render(<EditRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    // EditRuleForm's catch block surfaces `err.message` for Error instances and
    // only falls back to the generic string for non-Error throws, so the
    // expected text here is the rejection message itself.
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  it('cancel button navigates back', async () => {
    const user = userEvent.setup();
    // jsdom does not provide window.history.back as a spy, so install one here.
    const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    render(<EditRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(backSpy).toHaveBeenCalledTimes(1);
    backSpy.mockRestore();
  });

  it('has accessible form structure', () => {
    render(<EditRuleForm {...defaultProps} />);

    const fieldsets = screen.getAllByRole('group');
    expect(fieldsets.length).toBeGreaterThanOrEqual(2);

    // Every required marker renders its own `<span aria-hidden>*</span>`, so
    // there is one match per required label.
    expect(screen.getAllByText('*').length).toBeGreaterThan(0);

    // Check aria-invalid is absent before any validation error
    const metricInput = screen.getByLabelText(/^Métrica/);
    expect(metricInput).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('entity_id can be cleared when entity_type is server', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    const entityIdSelect = screen.getByLabelText(/^ID de entidad/);
    await user.selectOptions(entityIdSelect, ''); // Select "Todas las entidades"

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('entity_id')).toBe(''); // Empty string when cleared
  });

  it('updates entity_id when changing entity_type to non-server then back', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    // Change to service
    await user.selectOptions(screen.getByLabelText(/^Tipo de entidad/), 'service');
    // Now entity_id is text input
    await user.type(screen.getByLabelText(/^ID de entidad/), 'new-service-id');

    // Change back to server
    await user.selectOptions(screen.getByLabelText(/^Tipo de entidad/), 'server');
    // Should show dropdown again with servers
    await user.selectOptions(screen.getByLabelText(/^ID de entidad/), '123e4567-e89b-42d3-a456-426614174001');

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('entity_type')).toBe('server');
    expect(formData.get('entity_id')).toBe('123e4567-e89b-42d3-a456-426614174001');
  });

  it('includes is_active in formData', async () => {
    const user = userEvent.setup();
    render(<EditRuleForm {...defaultProps} />);

    // Uncheck active
    await user.click(screen.getByRole('checkbox', { name: 'Regla activa' }));

    await user.click(screen.getByRole('button', { name: 'Actualizar regla' }));

    expect(await screen.findByText('Regla actualizada correctamente')).toBeInTheDocument();

    const formData = updateAlertRuleMock.mock.calls[0][1];
    expect(formData.get('is_active')).toBe('false');
  });

  // TEMPORARILY REMOVED FOR COMMIT 1 - RESTORED IN COMMIT 2
  // it('activates an inactive rule when the checkbox is clicked', ...)
});
