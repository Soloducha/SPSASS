import { parseCreateRuleFormData, parseUpdateRuleFormData } from './rule-form-parsing';

function makeForm(entries: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(entries)) {
    fd.append(k, v);
  }
  return fd;
}

describe('parseCreateRuleFormData', () => {
  it('parses a full valid form with email + webhook + telegram', () => {
    const fd = makeForm({
      entity_type: 'server',
      entity_id: ' 123e4567-e89b-42d3-a456-426614174000 ',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80.5',
      duration_s: '120',
      severity: 'critical',
      is_active: 'true',
      email_to: 'ops@example.com, alerts@example.com',
      webhook_url: 'https://hooks.example.com/ingest',
      webhook_headers: '{"Authorization":"Bearer abc"}',
      telegram_chat_id: '-1001234567890',
      telegram_thread_id: '42',
      telegram_silent: 'true',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData).not.toBeNull();
    expect(ruleData!.entity_type).toBe('server');
    expect(ruleData!.entity_id).toBe('123e4567-e89b-42d3-a456-426614174000');
    expect(ruleData!.metric).toBe('cpu_usage');
    expect(ruleData!.operator).toBe('gt');
    expect(ruleData!.threshold).toBe(80.5);
    expect(ruleData!.duration_s).toBe(120);
    expect(ruleData!.severity).toBe('critical');
    expect(ruleData!.is_active).toBe(true);
    expect(ruleData!.channels.email).toEqual({ to: ['ops@example.com', 'alerts@example.com'] });
    expect(ruleData!.channels.webhook).toEqual({
      url: 'https://hooks.example.com/ingest',
      headers: { Authorization: 'Bearer abc' },
    });
    expect(ruleData!.channels.telegram).toEqual({ chat_id: '-1001234567890', thread_id: 42, silent: true });
  });

  it('parses a minimal form with only email channel', () => {
    const fd = makeForm({
      entity_type: 'service',
      metric: 'error_rate',
      operator: 'gt',
      threshold: '1',
      email_to: 'ops@example.com',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData).not.toBeNull();
    expect(ruleData!.entity_id).toBeUndefined();
    expect(ruleData!.duration_s).toBe(60);
    expect(ruleData!.severity).toBe('warning');
    expect(ruleData!.is_active).toBe(false);
    expect(ruleData!.channels.email).toEqual({ to: ['ops@example.com'] });
    expect(ruleData!.channels.webhook).toBeUndefined();
    expect(ruleData!.channels.telegram).toBeUndefined();
  });

  it('parses telegram-only with numeric chat_id, thread_id and silent=true', () => {
    const fd = makeForm({
      entity_type: 'server',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80',
      telegram_chat_id: '-1001234567890',
      telegram_thread_id: '7',
      telegram_silent: 'true',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels.telegram).toEqual({ chat_id: '-1001234567890', thread_id: 7, silent: true });
    expect(ruleData!.channels.email).toBeUndefined();
  });

  it('parses telegram-only with @username chat_id, no thread_id and silent=false', () => {
    const fd = makeForm({
      entity_type: 'server',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80',
      telegram_chat_id: '@mychannel',
      telegram_silent: 'false',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels.telegram).toEqual({ chat_id: '@mychannel' });
  });

  it('parses webhook with valid JSON headers', () => {
    const fd = makeForm({
      entity_type: 'server',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80',
      webhook_url: 'https://example.com/hook',
      webhook_headers: '{"X-Key":"v"}',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels.webhook).toEqual({
      url: 'https://example.com/hook',
      headers: { 'X-Key': 'v' },
    });
  });

  it('returns error when webhook headers are invalid JSON', () => {
    const fd = makeForm({
      entity_type: 'server',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80',
      webhook_url: 'https://example.com/hook',
      webhook_headers: '{invalid',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(ruleData).toBeNull();
    expect(error).toBe('Headers de webhook deben ser JSON válido');
  });

  it('produces empty channels object when no channels present', () => {
    const fd = makeForm({
      entity_type: 'server',
      metric: 'cpu_usage',
      operator: 'gt',
      threshold: '80',
    });

    const { ruleData, error } = parseCreateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels).toEqual({});
  });
});

describe('parseUpdateRuleFormData', () => {
  it('parses a full update with all fields', () => {
    const fd = makeForm({
      entity_type: 'service',
      entity_id: ' 123e4567-e89b-42d3-a456-426614174000 ',
      metric: 'latency',
      operator: 'lt',
      threshold: '100',
      duration_s: '30',
      severity: 'info',
      is_active: 'false',
      email_to: 'ops@example.com',
    });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData).toEqual({
      entity_type: 'service',
      entity_id: '123e4567-e89b-42d3-a456-426614174000',
      metric: 'latency',
      operator: 'lt',
      threshold: 100,
      duration_s: 30,
      severity: 'info',
      is_active: false,
      channels: { email: { to: ['ops@example.com'] } },
    });
  });

  it('parses a partial update with only metric + operator', () => {
    const fd = makeForm({ metric: 'latency', operator: 'lt' });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData).toEqual({ metric: 'latency', operator: 'lt' });
  });

  it('clears email channel when email_to is empty string', () => {
    const fd = makeForm({ email_to: '' });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels).toEqual({ email: undefined });
  });

  it('clears telegram channel when telegram_chat_id is empty string', () => {
    const fd = makeForm({ telegram_chat_id: '' });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels).toEqual({ telegram: undefined });
  });

  it('does not set silent key when telegram_silent is empty string', () => {
    const fd = makeForm({ telegram_chat_id: '-1001', telegram_silent: '' });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData!.channels!.telegram).toEqual({ chat_id: '-1001' });
    expect('silent' in ruleData!.channels!.telegram!).toBe(false);
  });

  it('omits channels from ruleData when no channel fields present', () => {
    const fd = makeForm({ metric: 'latency' });

    const { ruleData, error } = parseUpdateRuleFormData(fd);
    expect(error).toBeUndefined();
    expect(ruleData).toEqual({ metric: 'latency' });
    expect('channels' in ruleData!).toBe(false);
  });
});
