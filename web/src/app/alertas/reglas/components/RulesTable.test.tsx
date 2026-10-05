'use client';

/**
 * Component tests for RulesTable.
 *
 * Query conventions used throughout this file:
 * - RulesTable renders BOTH a desktop <table> and a mobile card list for every
 *   rule (Tailwind hides one at runtime, but jsdom applies no stylesheet, so
 *   both are queryable). Desktop-first JSX order means index [0] of a
 *   getAllBy* result is always the desktop control. Desktop-only assertions are
 *   scoped with `within(screen.getByRole('table'))`.
 * - The confirm <dialog> stays mounted for the component's whole lifetime; only
 *   its `open` state changes. Its presence in the DOM is therefore not evidence
 *   of visibility, and `ruleToDelete`-derived message text is used as the
 *   discriminator for open/closed state instead.
 */

import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RulesTable } from './RulesTable';
import { toggleRuleEnabledAction, deleteAlertRuleAction } from '../actions';
import type { AlertRuleResponse } from '@/lib/api/rules';
import { vi } from 'vitest';

// Mock the server actions
vi.mock('../actions', () => ({
  toggleRuleEnabledAction: vi.fn(),
  deleteAlertRuleAction: vi.fn(),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// vi.mocked() gives the module's server actions the `vi.fn()` mock surface.
const toggleRuleEnabledMock = vi.mocked(toggleRuleEnabledAction);
const deleteAlertRuleMock = vi.mocked(deleteAlertRuleAction);

const mockRules: AlertRuleResponse[] = [
  {
    id: 'rule-1',
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
      email: { to: ['ops@example.com'] },
      webhook: undefined,
      telegram: undefined,
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-2',
    tenant_id: 'tenant-1',
    entity_type: 'service',
    entity_id: '123e4567-e89b-42d3-a456-426614174001',
    metric: 'mem_usage',
    operator: 'gte',
    threshold: 90.0,
    duration_s: 30,
    severity: 'critical',
    is_active: false,
    channels: {
      email: undefined,
      webhook: { url: 'https://example.com/webhook', headers: {} },
      telegram: undefined,
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-3',
    tenant_id: 'tenant-1',
    entity_type: 'process',
    entity_id: null,
    metric: 'disk_usage',
    operator: 'lt',
    threshold: 10.0,
    duration_s: 120,
    severity: 'info',
    is_active: true,
    channels: {
      email: undefined,
      webhook: undefined,
      telegram: { chat_id: '-1001234567890', thread_id: 42, silent: true },
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

const defaultProps = {
  initialRules: mockRules,
  initialHasNext: false,
  initialParams: { offset: 0, limit: 10 },
};

/** Message text that only renders while a specific rule is pending deletion. */
const PENDING_DELETE_MESSAGE = /¿Eliminar la regla "Servidor - cpu_usage"\?/;
/** Fallback message rendered whenever `ruleToDelete` is null (dialog closed). */
const NO_RULE_MESSAGE = /¿Eliminar esta regla de alerta\?/;

function getDialog(): HTMLDialogElement {
  const dialog = document.querySelector('dialog');
  if (!dialog) throw new Error('ConfirmDialog <dialog> is not in the document');
  return dialog as HTMLDialogElement;
}

describe('RulesTable', () => {
  beforeAll(() => {
    // jsdom 25 ships HTMLDialogElement without showModal()/show()/close(), which
    // ConfirmDialog's open effect calls. Polyfill them to reflect the `open`
    // attribute, which is how the real user agent signals modal state.
    const proto = window.HTMLDialogElement.prototype as unknown as Record<string, unknown>;
    proto.showModal = function showModal(this: HTMLDialogElement) {
      this.open = true;
    };
    proto.show = function show(this: HTMLDialogElement) {
      this.open = true;
    };
    proto.close = function close(this: HTMLDialogElement) {
      this.open = false;
    };
  });

  beforeEach(() => {
    vi.clearAllMocks();
    toggleRuleEnabledMock.mockResolvedValue({ rule: mockRules[0], error: undefined });
    deleteAlertRuleMock.mockResolvedValue({ success: true, error: undefined });
  });

  it('renders table with rules in desktop view', () => {
    render(<RulesTable {...defaultProps} />);

    // Desktop-only: the mobile cards repeat several of these labels as <dt>s.
    const table = within(screen.getByRole('table'));

    // Table headers
    expect(table.getByText('Entidad')).toBeInTheDocument();
    expect(table.getByText('ID Entidad')).toBeInTheDocument();
    expect(table.getByText('Métrica')).toBeInTheDocument();
    expect(table.getByText('Operador')).toBeInTheDocument();
    expect(table.getByText('Umbral')).toBeInTheDocument();
    expect(table.getByText('Duración (s)')).toBeInTheDocument();
    expect(table.getByText('Severidad')).toBeInTheDocument();
    expect(table.getByText('Canales')).toBeInTheDocument();
    expect(table.getByText('Estado')).toBeInTheDocument();
    expect(table.getByText('Acciones')).toBeInTheDocument();

    // Rule rows
    expect(table.getByText('Servidor')).toBeInTheDocument();
    expect(table.getByText('cpu_usage')).toBeInTheDocument();
    expect(table.getByText('>')).toBeInTheDocument();
    expect(table.getByText('80.50')).toBeInTheDocument();
    expect(table.getByText('60')).toBeInTheDocument();
    expect(table.getByText('Advertencia')).toBeInTheDocument();
    expect(table.getByText('Email: ops@example.com')).toBeInTheDocument();
    // Both rule-1 and rule-3 are active, so the chip appears twice in the table.
    expect(table.getAllByText('Activa')).toHaveLength(2);

    expect(table.getByText('Servicio')).toBeInTheDocument();
    expect(table.getByText('mem_usage')).toBeInTheDocument();
    expect(table.getByText('≥')).toBeInTheDocument();
    expect(table.getByText('90.00')).toBeInTheDocument();
    expect(table.getByText('30')).toBeInTheDocument();
    expect(table.getByText('Crítica')).toBeInTheDocument();
    expect(table.getByText('Webhook: https://example.com/webhook')).toBeInTheDocument();
    expect(table.getByText('Inactiva')).toBeInTheDocument();

    expect(table.getByText('Proceso')).toBeInTheDocument();
    expect(table.getByText('disk_usage')).toBeInTheDocument();
    expect(table.getByText('<')).toBeInTheDocument();
    expect(table.getByText('10.00')).toBeInTheDocument();
    expect(table.getByText('120')).toBeInTheDocument();
    expect(table.getByText('Informativa')).toBeInTheDocument();
    expect(table.getByText('Telegram: -1001234567890 (thread: 42) [silent]')).toBeInTheDocument();
  });

  it('shows empty state when no rules', () => {
    const props = { ...defaultProps, initialRules: [] };
    render(<RulesTable {...props} />);

    expect(screen.getByText('Sin reglas')).toBeInTheDocument();
    expect(screen.getByText('No se encontraron reglas de alerta.')).toBeInTheDocument();
  });

  it('toggles rule enabled/disabled', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    // Toggle button for rule-1 (active -> inactive). Desktop row and mobile
    // card both render it; [0] is the desktop one because the <table> precedes
    // the card list in the JSX.
    const toggleButton = screen.getAllByRole('button', { name: 'Desactivar regla' })[0];
    await user.click(toggleButton);

    expect(await screen.findByText('Regla desactivada')).toBeInTheDocument();

    expect(toggleRuleEnabledMock).toHaveBeenCalledTimes(1);
    const formData = toggleRuleEnabledMock.mock.calls[0][1];
    expect(formData.get('ruleId')).toBe('rule-1');
    expect(formData.get('is_active')).toBe('false');
  });

  it('toggles rule disabled/enabled', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    // Toggle button for rule-2 (inactive -> active); desktop row, see above.
    const toggleButton = screen.getAllByRole('button', { name: 'Activar regla' })[0];
    await user.click(toggleButton);

    expect(await screen.findByText('Regla activada')).toBeInTheDocument();

    expect(toggleRuleEnabledMock).toHaveBeenCalledTimes(1);
    const formData = toggleRuleEnabledMock.mock.calls[0][1];
    expect(formData.get('ruleId')).toBe('rule-2');
    expect(formData.get('is_active')).toBe('true');
  });

  it('shows error when toggle fails', async () => {
    const user = userEvent.setup();
    toggleRuleEnabledMock.mockResolvedValue({ rule: null, error: 'Error al cambiar estado' });
    render(<RulesTable {...defaultProps} />);

    const toggleButton = screen.getAllByRole('button', { name: 'Desactivar regla' })[0];
    await user.click(toggleButton);

    expect(await screen.findByText('Error al cambiar estado')).toBeInTheDocument();
  });

  it('opens delete confirmation dialog', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    // [0] is the desktop row's delete button (see the toggle test).
    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    expect(await screen.findByText(PENDING_DELETE_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText('Eliminar regla de alerta')).toBeInTheDocument();
    expect(getDialog().open).toBe(true);
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Eliminar' })).toBeInTheDocument();
  });

  it('confirms delete and calls delete action', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    await user.click(screen.getByRole('button', { name: 'Eliminar' }));

    expect(await screen.findByText('Regla eliminada')).toBeInTheDocument();

    expect(deleteAlertRuleMock).toHaveBeenCalledTimes(1);
    const formData = deleteAlertRuleMock.mock.calls[0][1];
    expect(formData.get('ruleId')).toBe('rule-1');
  });

  it('cancels delete when clicking Cancel', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);
    await user.click(screen.getByRole('button', { name: 'Cancelar' }));

    // The <dialog> is never unmounted, so its title stays in the DOM. The
    // rule-specific message is the state signal: it is replaced by the generic
    // fallback once `ruleToDelete` is cleared on close.
    await waitFor(() => {
      expect(screen.queryByText(PENDING_DELETE_MESSAGE)).not.toBeInTheDocument();
      expect(screen.getByText(NO_RULE_MESSAGE)).toBeInTheDocument();
    });
    expect(getDialog().open).toBe(false);
    expect(deleteAlertRuleMock).not.toHaveBeenCalled();
  });

  it('shows error when delete fails', async () => {
    const user = userEvent.setup();
    deleteAlertRuleMock.mockResolvedValue({ success: false, error: 'Error al eliminar' });
    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    await user.click(screen.getByRole('button', { name: 'Eliminar' }));

    expect(await screen.findByText('Error al eliminar')).toBeInTheDocument();
  });

  it('shows error when delete throws', async () => {
    const user = userEvent.setup();
    deleteAlertRuleMock.mockRejectedValue(new Error('Network error'));
    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    await user.click(screen.getByRole('button', { name: 'Eliminar' }));

    // handleDeleteConfirm's catch block surfaces `err.message` for Error
    // instances and only falls back to the generic string for non-Error
    // throws, so the expected text is the rejection message itself.
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  it('disables prev button on first page', () => {
    render(<RulesTable {...defaultProps} />);

    expect(screen.getByRole('button', { name: 'Página anterior' })).toBeDisabled();
  });

  it('disables next button when no next page', () => {
    render(<RulesTable {...defaultProps} />);

    expect(screen.getByRole('button', { name: 'Página siguiente' })).toBeDisabled();
  });

  it('enables next button when hasNext is true', () => {
    const props = { ...defaultProps, initialHasNext: true };
    render(<RulesTable {...props} />);

    expect(screen.getByRole('button', { name: 'Página siguiente' })).not.toBeDisabled();
  });

  it('enables prev button when offset is greater than zero', () => {
    const props = { ...defaultProps, initialParams: { offset: 10, limit: 10 } };
    render(<RulesTable {...props} />);

    expect(screen.getByRole('button', { name: 'Página anterior' })).not.toBeDisabled();
  });

  it('edit link navigates to edit page', () => {
    render(<RulesTable {...defaultProps} />);

    // [0] is the desktop row's edit link; both variants share the same href.
    const editLink = screen.getAllByRole('link', { name: /Editar regla Servidor - cpu_usage/i })[0];
    expect(editLink).toHaveAttribute('href', '/alertas/reglas/rule-1/editar');
  });

  it('shows correct entity_id display', () => {
    render(<RulesTable {...defaultProps} />);

    // `entity_id.slice(0, 8)` yields '123e4567' (8 chars, the 9th being the
    // separator dash), so the truncated form is '123e4567…' with no dash.
    // Rendered by the two rules with an entity_id, in the table and in the cards.
    expect(screen.getAllByText('123e4567…').length).toBeGreaterThanOrEqual(4);
    // The rule without entity_id renders the explicit "all entities" marker.
    expect(screen.getAllByText('— (todas)').length).toBeGreaterThanOrEqual(1);
  });

  it('displays pagination info', () => {
    render(<RulesTable {...defaultProps} />);

    expect(screen.getByText(/Mostrando 1–3/)).toBeInTheDocument();
    expect(screen.getByText(/límite: 10/)).toBeInTheDocument();
  });

  it('has accessible table structure', () => {
    render(<RulesTable {...defaultProps} />);

    const table = screen.getByRole('table');
    expect(table).toBeInTheDocument();

    expect(table.querySelector('thead')).toBeInTheDocument();
    expect(table.querySelector('tbody')).toBeInTheDocument();

    expect(screen.getByRole('columnheader', { name: 'Entidad' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Métrica' })).toBeInTheDocument();
  });

  it('confirm dialog has proper accessibility attributes', async () => {
    const user = userEvent.setup();
    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    await waitFor(() => {
      expect(getDialog().open).toBe(true);
    });

    // jsdom does not implement modal dialog semantics, so the attributes are
    // asserted directly on the element rather than through getByRole('dialog').
    const dialog = getDialog();
    expect(dialog).toBeTruthy();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'dialog-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'dialog-message');
    expect(document.getElementById('dialog-title')).toHaveTextContent('Eliminar regla de alerta');
    expect(document.getElementById('dialog-message')).toHaveTextContent(PENDING_DELETE_MESSAGE);
  });

  it('formats channels correctly for all combinations', () => {
    const ruleWithAllChannels: AlertRuleResponse = {
      ...mockRules[0],
      id: 'rule-all',
      channels: {
        email: { to: ['a@b.com', 'c@d.com'] },
        webhook: { url: 'https://hook.com', headers: { 'X-Custom': 'val' } },
        telegram: { chat_id: '@channel', thread_id: 1, silent: false },
      },
    };

    const props = { ...defaultProps, initialRules: [ruleWithAllChannels] };
    render(<RulesTable {...props} />);

    // One match in the table cell, one in the mobile card's channel line.
    expect(
      screen.getAllByText('Email: a@b.com, c@d.com; Webhook: https://hook.com; Telegram: @channel (thread: 1)')
        .length
    ).toBeGreaterThan(0);
  });

  it('formats channels with only telegram silent', () => {
    const ruleSilentTelegram: AlertRuleResponse = {
      ...mockRules[0],
      id: 'rule-silent',
      channels: {
        email: undefined,
        webhook: undefined,
        telegram: { chat_id: '-1001234567890', thread_id: undefined, silent: true },
      },
    };

    const props = { ...defaultProps, initialRules: [ruleSilentTelegram] };
    render(<RulesTable {...props} />);

    expect(screen.getAllByText('Telegram: -1001234567890 [silent]').length).toBeGreaterThan(0);
  });

  it('handles rule with all channels empty', () => {
    const ruleNoChannels: AlertRuleResponse = {
      ...mockRules[0],
      id: 'rule-none',
      channels: { email: undefined, webhook: undefined, telegram: undefined },
    };

    const props = { ...defaultProps, initialRules: [ruleNoChannels] };
    render(<RulesTable {...props} />);

    // formatChannels falls back to an em dash, rendered in the table cell and
    // in the mobile card's channel line.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('shows entity type and operator labels', () => {
    render(<RulesTable {...defaultProps} />);

    // Each label appears once per rule in the table and once in the cards.
    expect(screen.getAllByText('Servidor').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Servicio').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Proceso').length).toBeGreaterThan(0);

    expect(screen.getAllByText('>').length).toBeGreaterThan(0);
    expect(screen.getAllByText('≥').length).toBeGreaterThan(0);
    expect(screen.getAllByText('<').length).toBeGreaterThan(0);
  });

  it('shows loading label on confirm button while deleting', async () => {
    const user = userEvent.setup();
    // Structural stand-in for the non-exported DeleteRuleResult.
    let resolveDelete: (value: { success: boolean; error?: string }) => void;
    const deletePromise = new Promise<{ success: boolean; error?: string }>(resolve => {
      resolveDelete = resolve;
    });
    deleteAlertRuleMock.mockReturnValue(deletePromise);

    render(<RulesTable {...defaultProps} />);

    const deleteButton = screen.getAllByRole('button', { name: /Eliminar regla Servidor - cpu_usage/i })[0];
    await user.click(deleteButton);

    await user.click(screen.getByRole('button', { name: 'Eliminar' }));

    const loadingButton = screen.getByRole('button', { name: 'Eliminando…' });
    expect(loadingButton).toBeDisabled();

    await act(async () => {
      resolveDelete!({ success: true, error: undefined });
    });
  });
});
