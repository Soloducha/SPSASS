import {
  validateCreateRuleData,
  validateEntityId,
  validateRuleId,
  validateUpdateRuleData,
} from './rule-validation';
import type { AlertRuleCreate, AlertRuleUpdate } from '@/lib/api/rules';

const VALID_UUID = '123e4567-e89b-42d3-a456-426614174000';

function baseValidCreate(): AlertRuleCreate {
  return {
    entity_type: 'server',
    metric: 'cpu_usage',
    operator: 'gt',
    threshold: 80,
    channels: { email: { to: ['ops@example.com'] } },
  };
}

describe('validateCreateRuleData', () => {
  it('accepts a minimal valid rule', () => {
    expect(validateCreateRuleData(baseValidCreate())).toBeNull();
  });

  it('accepts all 3 channels', () => {
    const data = baseValidCreate();
    data.channels = {
      email: { to: ['ops@example.com'] },
      webhook: { url: 'https://example.com/hook', headers: {} },
      telegram: { chat_id: '-1001234567890' },
    };
    expect(validateCreateRuleData(data)).toBeNull();
  });

  it('accepts telegram with numeric chat_id', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '-1001234567890' } };
    expect(validateCreateRuleData(data)).toBeNull();
  });

  it('accepts telegram with @username chat_id', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '@canal_bot' } };
    expect(validateCreateRuleData(data)).toBeNull();
  });

  it('accepts telegram with thread_id and silent', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '-1001234567890', thread_id: 42, silent: true } };
    expect(validateCreateRuleData(data)).toBeNull();
  });

  it('rejects missing entity_type', () => {
    const data = baseValidCreate();
    // @ts-expect-error intentional invalid data
    delete data.entity_type;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects empty metric', () => {
    const data = baseValidCreate();
    data.metric = '   ';
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects metric longer than 100 chars', () => {
    const data = baseValidCreate();
    data.metric = 'a'.repeat(101);
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects invalid operator', () => {
    const data = baseValidCreate();
    data.operator = 'between' as AlertRuleCreate['operator'];
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects NaN threshold', () => {
    const data = baseValidCreate();
    data.threshold = NaN;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects non-finite threshold', () => {
    const data = baseValidCreate();
    data.threshold = Infinity;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects duration_s < 1', () => {
    const data = baseValidCreate();
    data.duration_s = 0;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects non-integer duration_s', () => {
    const data = baseValidCreate();
    data.duration_s = 1.5;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects invalid severity', () => {
    const data = baseValidCreate();
    data.severity = 'fatal' as AlertRuleCreate['severity'];
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects missing channels', () => {
    const data = baseValidCreate();
    // @ts-expect-error intentional invalid data
    delete data.channels;
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects empty channels', () => {
    const data = baseValidCreate();
    data.channels = {};
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects email with bad format', () => {
    const data = baseValidCreate();
    data.channels = { email: { to: ['not-an-email'] } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects webhook with missing URL', () => {
    const data = baseValidCreate();
    data.channels = { webhook: { url: '', headers: {} } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects webhook with invalid URL', () => {
    const data = baseValidCreate();
    data.channels = { webhook: { url: 'not a url', headers: {} } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects telegram missing chat_id', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '' } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects telegram chat_id invalid format', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: 'not_a_valid_id' } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects telegram thread_id non-integer', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '-1001234567890', thread_id: 1.5 } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects telegram thread_id < 1', () => {
    const data = baseValidCreate();
    data.channels = { telegram: { chat_id: '-1001234567890', thread_id: 0 } };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });

  it('rejects telegram silent non-boolean', () => {
    const data = baseValidCreate();
    data.channels = {
      telegram: { chat_id: '-1001234567890', silent: 'yes' as unknown as boolean },
    };
    expect(validateCreateRuleData(data)).not.toBeNull();
  });
});

describe('validateUpdateRuleData', () => {
  it('accepts an empty object', () => {
    expect(validateUpdateRuleData({})).toBeNull();
  });

  it('accepts partial update (only metric)', () => {
    expect(validateUpdateRuleData({ metric: 'cpu_usage' })).toBeNull();
  });

  it('accepts channels with telegram only', () => {
    expect(validateUpdateRuleData({ channels: { telegram: { chat_id: '-1001234567890' } } })).toBeNull();
  });

  it('accepts clearing channels (all undefined)', () => {
    const data: AlertRuleUpdate = { channels: { email: undefined, webhook: undefined, telegram: undefined } };
    expect(validateUpdateRuleData(data)).toBeNull();
  });

  it('rejects invalid entity_type', () => {
    expect(validateUpdateRuleData({ entity_type: 'pod' as AlertRuleUpdate['entity_type'] })).not.toBeNull();
  });

  it('rejects empty metric', () => {
    expect(validateUpdateRuleData({ metric: '   ' })).not.toBeNull();
  });

  it('rejects invalid operator', () => {
    expect(validateUpdateRuleData({ operator: 'between' as AlertRuleUpdate['operator'] })).not.toBeNull();
  });

  it('rejects invalid threshold', () => {
    expect(validateUpdateRuleData({ threshold: NaN })).not.toBeNull();
  });

  it('rejects invalid duration_s', () => {
    expect(validateUpdateRuleData({ duration_s: 0 })).not.toBeNull();
    expect(validateUpdateRuleData({ duration_s: 1.5 })).not.toBeNull();
  });

  it('rejects invalid severity', () => {
    expect(validateUpdateRuleData({ severity: 'fatal' as AlertRuleUpdate['severity'] })).not.toBeNull();
  });

  it('rejects empty channels object', () => {
    expect(validateUpdateRuleData({ channels: {} })).not.toBeNull();
  });
});

describe('validateRuleId', () => {
  it('accepts a valid UUID', () => {
    expect(validateRuleId(VALID_UUID)).toBeNull();
  });

  it('rejects empty string', () => {
    expect(validateRuleId('')).not.toBeNull();
  });

  it('rejects non-UUID', () => {
    expect(validateRuleId('not-a-uuid')).not.toBeNull();
  });
});

describe('validateEntityId', () => {
  it('accepts undefined', () => {
    expect(validateEntityId(undefined)).toBeNull();
  });

  it('accepts empty string', () => {
    expect(validateEntityId('')).toBeNull();
  });

  it('accepts valid UUID', () => {
    expect(validateEntityId(VALID_UUID)).toBeNull();
  });

  it('rejects non-UUID', () => {
    expect(validateEntityId('not-a-uuid')).not.toBeNull();
  });
});
