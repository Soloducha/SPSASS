'use client';

/**
 * Component tests for CreateRuleForm.
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

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CreateRuleForm } from './CreateRuleForm';
import { createAlertRuleAction } from '../../actions';
import type { AlertRuleResponse } from '@/lib/api/rules';
import type { ServerOverviewItem } from '@/lib/api/dashboard';
import { vi } from 'vitest';

// Mock the server action
vi.mock('../../actions', () => ({
  createAlertRuleAction: vi.fn(),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// vi.mocked() gives the module's server action the `vi.fn()` mock surface.
const createAlertRuleMock = vi.mocked(createAlertRuleAction);

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
  id: 'new-rule',
  tenant_id: 'tenant-1',
  entity_type: 'server',
  entity_id: null,
  metric: 'cpu_usage',
  operator: 'gt',
  threshold: 80.5,
  duration_s: 60,
  severity: 'warning',
  channels: { email: { to: ['ops@example.com'] } },
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const defaultProps = {
  servers: mockServers,
};

describe('CreateRuleForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createAlertRuleMock.mockResolvedValue({ rule: mockRule, error: undefined });
  });

  it('renders the form with all fields', () => {
    render(<CreateRuleForm {...defaultProps} />);

    expect(screen.getByLabelText(/^Tipo de entidad/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^ID de entidad/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Métrica/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Operador/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Umbral/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Duración/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Severidad/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Regla activa/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Email - Destinatarios/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Webhook - URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Webhook - Headers/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Telegram - Chat ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Telegram - Thread ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Enviar sin notificación/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear regla' })).toBeInTheDocument();
  });

  it('shows server dropdown when entity_type is server', () => {
    render(<CreateRuleForm {...defaultProps} />);

    const entityIdField = screen.getByLabelText(/^ID de entidad/);
    expect(entityIdField).toBeInTheDocument();
    // Should be a select with server options
    expect(screen.getByRole('option', { name: 'Todas las entidades (sin filtro)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'server-1' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'server-2' })).toBeInTheDocument();
  });

  it('shows text input for entity_id when entity_type is not server', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    // Change entity type to service
    await user.selectOptions(screen.getByLabelText(/^Tipo de entidad/), 'service');

    // Should now show text input
    const entityIdInput = screen.getByLabelText(/^ID de entidad/);
    expect(entityIdInput).toBeInTheDocument();
    expect(entityIdInput.tagName).toBe('INPUT');
    expect(entityIdInput).toHaveAttribute('placeholder', 'UUID de la entidad (opcional, vacío = todas)');
  });

  it('validates required fields on submit', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    // Should show validation errors.
    // No 'Operador no válido' assertion: the operator <select> is a controlled
    // input whose state always starts at the valid default 'gt', so that branch
    // of validateField is unreachable from the rendered form.
    await waitFor(() => {
      expect(screen.getByText('La métrica es obligatoria')).toBeInTheDocument();
      expect(screen.getByText('El umbral debe ser un número válido')).toBeInTheDocument();
      // entity_type has default so not error
    });

    // Channels error - no channels provided
    await waitFor(() => {
      expect(screen.getByText('Se requiere al menos un canal (email, webhook o telegram)')).toBeInTheDocument();
    });
  });

  it('validates metric max length', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    // The input carries maxLength={100}, so user.type can never exceed it.
    // fireEvent.change bypasses the length constraint and lets the value reach
    // the >100 branch of validateField.
    const metricInput = screen.getByLabelText(/^Métrica/);
    fireEvent.change(metricInput, { target: { value: 'a'.repeat(101) } });

    expect(await screen.findByText('La métrica no puede exceder 100 caracteres')).toBeInTheDocument();
  });

  it('validates threshold as number', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    // A number input can never hold a non-numeric value in jsdom: it silently
    // discards the input and fires no change event, so typing 'abc' is a no-op.
    // Empty is the only reachable way into the parseFloat -> NaN branch. The
    // field starts at '' already and React's value tracker suppresses a change
    // to the same value, so seed it with a real number first, then clear it.
    const thresholdInput = screen.getByLabelText(/^Umbral/);
    fireEvent.change(thresholdInput, { target: { value: '5' } });
    fireEvent.change(thresholdInput, { target: { value: '' } });

    expect(await screen.findByText('El umbral debe ser un número válido')).toBeInTheDocument();
  });

  it('validates duration_s as positive integer', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    // '0' is accepted by a number input, so this value is reachable normally;
    // fireEvent.change is used for consistency with the other number inputs.
    fireEvent.change(screen.getByLabelText(/^Duración/), { target: { value: '0' } });

    expect(await screen.findByText('La duración debe ser un entero positivo (segundos)')).toBeInTheDocument();
  });

  it('treats an empty duration as valid', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    // validateField('duration_s', '') returns null, so clearing the optional
    // duration must not produce an error. This is the reachable counterpart of
    // the positive-integer case above.
    fireEvent.change(screen.getByLabelText(/^Duración/), { target: { value: '' } });

    expect(screen.queryByText('La duración debe ser un entero positivo (segundos)')).not.toBeInTheDocument();
  });

  it('validates email format', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/^Email - Destinatarios/);
    await user.type(emailInput, 'invalid-email');
    await user.tab();

    expect(await screen.findByText('Formato de email inválido')).toBeInTheDocument();
  });

  it('accepts valid email', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/^Email - Destinatarios/);
    await user.type(emailInput, 'ops@example.com');
    await user.tab();

    await waitFor(() => {
      expect(screen.queryByText('Formato de email inválido')).not.toBeInTheDocument();
    });
  });

  it('validates webhook URL format', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const webhookInput = screen.getByLabelText(/^Webhook - URL/);
    await user.type(webhookInput, 'not-a-url');
    await user.tab();

    expect(await screen.findByText('URL de webhook inválida')).toBeInTheDocument();
  });

  it('validates webhook headers as JSON', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    // user.type reads `{...}` as a keyboard descriptor, so the textarea would
    // never receive this text. fireEvent.change delivers it verbatim.
    fireEvent.change(screen.getByLabelText(/^Webhook - Headers/), { target: { value: '{invalid}' } });

    expect(await screen.findByText('Headers de webhook deben ser JSON válido')).toBeInTheDocument();
  });

  it('validates telegram chat_id format', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const chatIdInput = screen.getByLabelText(/^Telegram - Chat ID/);
    await user.type(chatIdInput, 'invalid');
    await user.tab();

    expect(
      await screen.findByText('chat_id debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)')
    ).toBeInTheDocument();
  });

  it('accepts numeric telegram chat_id', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const chatIdInput = screen.getByLabelText(/^Telegram - Chat ID/);
    await user.type(chatIdInput, '-1001234567890');
    await user.tab();

    await waitFor(() => {
      expect(screen.queryByText(/chat_id debe ser un ID numérico/)).not.toBeInTheDocument();
    });
  });

  it('accepts @username telegram chat_id', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    const chatIdInput = screen.getByLabelText(/^Telegram - Chat ID/);
    await user.type(chatIdInput, '@canal_bot');
    await user.tab();

    await waitFor(() => {
      expect(screen.queryByText(/chat_id debe ser un ID numérico/)).not.toBeInTheDocument();
    });
  });

  it('validates telegram thread_id as positive integer', async () => {
    render(<CreateRuleForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/^Telegram - Thread ID/), { target: { value: '0' } });

    expect(await screen.findByText('thread_id debe ser un entero positivo')).toBeInTheDocument();
  });

  it('submits successfully with valid data and at least one channel', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    // Fill required fields
    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Email - Destinatarios/), 'ops@example.com');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    expect(createAlertRuleMock).toHaveBeenCalledTimes(1);
    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('metric')).toBe('cpu_usage');
    expect(formData.get('threshold')).toBe('80.5');
    expect(formData.get('email_to')).toBe('ops@example.com');
  });

  it('submits successfully with webhook only', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Webhook - URL/), 'https://example.com/webhook');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('webhook_url')).toBe('https://example.com/webhook');
  });

  it('submits successfully with telegram only', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Telegram - Chat ID/), '-1001234567890');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('telegram_chat_id')).toBe('-1001234567890');
  });

  it('includes telegram thread_id when provided', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Telegram - Chat ID/), '-1001234567890');
    await user.type(screen.getByLabelText(/^Telegram - Thread ID/), '42');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('telegram_thread_id')).toBe('42');
  });

  // REGRESSION COVERAGE for a fixed component bug.
  //
  // CreateRuleForm.tsx used to wire this checkbox as
  //   onChange={e => { setTelegramSilent(e.target.checked); handleChange(e); }}
  // and handleChange then did
  //   else if (name === 'telegram_silent') setTelegramSilent(value === 'true')
  // where `value` is `e.target.value`. The input declares no `value` attribute,
  // so a checkbox always reports value 'on', never 'true'. handleChange
  // therefore overwrote the correct `e.target.checked` with `false` in the same
  // event, the checkbox never stayed ticked, and the `telegram_silent` FormData
  // entry (appended only when telegramSilent is true) was never sent.
  //
  // The fix drops the redundant handleChange call from the checkbox and removes
  // the now-unreachable `telegram_silent` / `is_active` branches from
  // handleChange, so only `e.target.checked` drives these two checkboxes.
  it('includes telegram silent when checked', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Telegram - Chat ID/), '-1001234567890');
    // Toggle the checkbox control directly rather than its <label>, so the
    // assertion does not depend on jsdom's label-activation forwarding.
    await user.click(screen.getByRole('checkbox', { name: /Enviar sin notificación/ }));

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('telegram_silent')).toBe('true');
  });

  it('re-checks an active rule after it has been unchecked', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Email - Destinatarios/), 'ops@example.com');

    // `is_active` defaults to checked. Toggling it off then on again must end up
    // checked, and that state must reach the submitted FormData.
    const isActiveCheckbox = screen.getByRole('checkbox', { name: 'Regla activa' });
    expect(isActiveCheckbox).toBeChecked();

    await user.click(isActiveCheckbox);
    expect(isActiveCheckbox).not.toBeChecked();

    await user.click(isActiveCheckbox);
    expect(isActiveCheckbox).toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('is_active')).toBe('true');
  });

  it('includes webhook headers when provided', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Webhook - URL/), 'https://example.com/webhook');
    // user.type parses `{...}` as a keyboard descriptor, so the JSON body is
    // written with fireEvent.change instead.
    fireEvent.change(screen.getByLabelText(/^Webhook - Headers/), {
      target: { value: '{"Authorization": "Bearer token"}' },
    });

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    const formData = createAlertRuleMock.mock.calls[0][1];
    expect(formData.get('webhook_headers')).toBe('{"Authorization": "Bearer token"}');
  });

  it('shows error message when server action returns error', async () => {
    const user = userEvent.setup();
    createAlertRuleMock.mockResolvedValue({ rule: null, error: 'Error del servidor' });
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Email - Destinatarios/), 'ops@example.com');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Error del servidor')).toBeInTheDocument();
  });

  it('shows error message when server action throws', async () => {
    const user = userEvent.setup();
    createAlertRuleMock.mockRejectedValue(new Error('Network error'));
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Email - Destinatarios/), 'ops@example.com');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    // CreateRuleForm's catch block surfaces `err.message` for Error instances
    // and only falls back to the generic string for non-Error throws, so the
    // expected text here is the rejection message itself.
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  it('resets form after successful submit', async () => {
    const user = userEvent.setup();
    render(<CreateRuleForm {...defaultProps} />);

    await user.type(screen.getByLabelText(/^Métrica/), 'cpu_usage');
    await user.type(screen.getByLabelText(/^Umbral/), '80.5');
    await user.type(screen.getByLabelText(/^Email - Destinatarios/), 'ops@example.com');

    await user.click(screen.getByRole('button', { name: 'Crear regla' }));

    expect(await screen.findByText('Regla creada correctamente')).toBeInTheDocument();

    // Check the values the user entered were cleared, and the defaults restored.
    expect(screen.getByLabelText(/^Métrica/)).toHaveValue('');
    // jest-dom reports valueAsNumber for number inputs, which is null when empty.
    expect(screen.getByLabelText(/^Umbral/)).toHaveValue(null);
    expect(screen.getByLabelText(/^Email - Destinatarios/)).toHaveValue('');

    expect(screen.getByLabelText(/^Tipo de entidad/)).toHaveValue('server');
    expect(screen.getByLabelText(/^Operador/)).toHaveValue('gt');
    expect(screen.getByLabelText(/^Duración/)).toHaveValue(60);
    expect(screen.getByLabelText(/^Severidad/)).toHaveValue('warning');
    expect(screen.getByRole('checkbox', { name: 'Regla activa' })).toBeChecked();
  });

  it('has accessible form structure', () => {
    render(<CreateRuleForm {...defaultProps} />);

    // Check fieldset and legend
    const fieldsets = screen.getAllByRole('group');
    expect(fieldsets.length).toBeGreaterThanOrEqual(2);

    // Check required field indicators. Every required marker renders its own
    // `<span aria-hidden>*</span>`, so there is one match per required label.
    expect(screen.getAllByText('*').length).toBeGreaterThan(0);

    // Check aria-invalid is absent before any validation error
    const metricInput = screen.getByLabelText(/^Métrica/);
    expect(metricInput).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('cancel button navigates back', async () => {
    const user = userEvent.setup();
    // jsdom does not provide window.history.back as a spy, so install one here.
    const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    render(<CreateRuleForm {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(backSpy).toHaveBeenCalledTimes(1);
    backSpy.mockRestore();
  });

  it('shows entity type labels correctly', () => {
    render(<CreateRuleForm {...defaultProps} />);

    const select = screen.getByLabelText(/^Tipo de entidad/);
    expect(select).toHaveDisplayValue('Servidor'); // default is server

    // Scope to this select: getAllByRole('option') across the whole form also
    // collects the entity-id, operator and severity options (17 in total).
    expect(within(select).getAllByRole('option')).toHaveLength(5); // ENTITY_TYPES
  });

  it('shows operator labels correctly', () => {
    render(<CreateRuleForm {...defaultProps} />);

    const select = screen.getByLabelText(/^Operador/);
    expect(select).toHaveDisplayValue('Mayor que (>)'); // default is gt
  });

  it('shows severity labels correctly', () => {
    render(<CreateRuleForm {...defaultProps} />);

    const select = screen.getByLabelText(/^Severidad/);
    expect(select).toHaveDisplayValue('Advertencia'); // default is warning
  });
});
