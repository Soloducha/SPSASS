import { validateChannels, validateField } from './validation';

const VALID_UUID = '123e4567-e89b-42d3-a456-426614174000';

describe('validateField', () => {
  describe('entity_type', () => {
    it('accepts a valid entity type', () => {
      expect(validateField('entity_type', 'server')).toBeNull();
    });

    it('returns error for invalid entity type', () => {
      expect(validateField('entity_type', 'unknown')).toBe('Tipo de entidad no válido');
    });
  });

  describe('entity_id', () => {
    it('passes when empty or undefined', () => {
      expect(validateField('entity_id', '')).toBeNull();
      expect(validateField('entity_id', '   ')).toBeNull();
      expect(validateField('entity_id', undefined as unknown as string)).toBeNull();
    });

    it('passes with a valid UUID', () => {
      expect(validateField('entity_id', VALID_UUID)).toBeNull();
    });

    it('returns error for invalid UUID', () => {
      expect(validateField('entity_id', 'not-a-uuid')).toBe('ID de entidad debe ser un UUID válido');
    });
  });

  describe('metric', () => {
    it('accepts a valid metric', () => {
      expect(validateField('metric', 'cpu_usage')).toBeNull();
    });

    it('returns error when empty', () => {
      expect(validateField('metric', '')).toBe('La métrica es obligatoria');
      expect(validateField('metric', '   ')).toBe('La métrica es obligatoria');
    });

    it('returns error when longer than 100 chars', () => {
      expect(validateField('metric', 'a'.repeat(101))).toBe('La métrica no puede exceder 100 caracteres');
    });
  });

  describe('operator', () => {
    it('accepts a valid operator', () => {
      expect(validateField('operator', 'gt')).toBeNull();
    });

    it('returns error for invalid operator', () => {
      expect(validateField('operator', 'maybe')).toBe('Operador no válido');
    });
  });

  describe('threshold', () => {
    it('accepts a valid number', () => {
      expect(validateField('threshold', '80.5')).toBeNull();
    });

    it('returns error for NaN', () => {
      expect(validateField('threshold', 'abc')).toBe('El umbral debe ser un número válido');
    });
  });

  describe('duration_s', () => {
    it('accepts a valid duration', () => {
      expect(validateField('duration_s', '60')).toBeNull();
    });

    it('returns error for 0', () => {
      expect(validateField('duration_s', '0')).toBe('La duración debe ser un entero positivo (segundos)');
    });

    it('returns error for non-integer/non-numeric', () => {
      expect(validateField('duration_s', 'abc')).toBe('La duración debe ser un entero positivo (segundos)');
      expect(validateField('duration_s', '0.5')).toBe('La duración debe ser un entero positivo (segundos)');
    });
  });

  describe('severity', () => {
    it('accepts a valid severity', () => {
      expect(validateField('severity', 'critical')).toBeNull();
    });

    it('returns error for invalid severity', () => {
      expect(validateField('severity', 'fatal')).toBe('Severidad no válida');
    });
  });

  describe('email_to', () => {
    it('accepts a valid email', () => {
      expect(validateField('email_to', 'ops@example.com')).toBeNull();
    });

    it('returns error for invalid email', () => {
      expect(validateField('email_to', 'not-an-email')).toBe('Formato de email inválido');
    });

    it('passes when empty (optional)', () => {
      expect(validateField('email_to', '')).toBeNull();
    });
  });

  describe('webhook_url', () => {
    it('accepts a valid URL', () => {
      expect(validateField('webhook_url', 'https://example.com/hook')).toBeNull();
    });

    it('returns error for invalid URL', () => {
      expect(validateField('webhook_url', 'not a url')).toBe('URL de webhook inválida');
    });

    it('passes when empty', () => {
      expect(validateField('webhook_url', '')).toBeNull();
    });
  });

  describe('webhook_headers', () => {
    it('accepts valid JSON', () => {
      expect(validateField('webhook_headers', '{"Authorization":"Bearer token"}')).toBeNull();
    });

    it('returns error for invalid JSON', () => {
      expect(validateField('webhook_headers', '{invalid}')).toBe('Headers de webhook deben ser JSON válido');
    });

    it('passes when empty', () => {
      expect(validateField('webhook_headers', '')).toBeNull();
    });
  });

  describe('telegram_chat_id', () => {
    it('accepts a numeric ID', () => {
      expect(validateField('telegram_chat_id', '-1001234567890')).toBeNull();
    });

    it('accepts a @username', () => {
      expect(validateField('telegram_chat_id', '@my_channel')).toBeNull();
    });

    it('returns error for invalid format', () => {
      expect(validateField('telegram_chat_id', 'not a chat id')).toBe(
        'chat_id debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)',
      );
    });

    it('passes when empty', () => {
      expect(validateField('telegram_chat_id', '')).toBeNull();
    });
  });

  describe('telegram_thread_id', () => {
    it('accepts a valid thread id', () => {
      expect(validateField('telegram_thread_id', '5')).toBeNull();
    });

    it('returns error for 0', () => {
      expect(validateField('telegram_thread_id', '0')).toBe('thread_id debe ser un entero positivo');
    });

    it('returns error for non-integer/non-numeric', () => {
      expect(validateField('telegram_thread_id', 'abc')).toBe('thread_id debe ser un entero positivo');
      expect(validateField('telegram_thread_id', '0.5')).toBe('thread_id debe ser un entero positivo');
    });

    it('passes when empty', () => {
      expect(validateField('telegram_thread_id', '')).toBeNull();
    });
  });

  it('returns null for an unknown field name', () => {
    expect(validateField('unknown_field', 'anything')).toBeNull();
  });
});

describe('validateChannels', () => {
  it('returns null when all three channels are present', () => {
    expect(validateChannels('ops@example.com', 'https://example.com/hook', '-1001234567890')).toBeNull();
  });

  it('returns null with only email', () => {
    expect(validateChannels('ops@example.com', '', '')).toBeNull();
  });

  it('returns null with only webhook', () => {
    expect(validateChannels('', 'https://example.com/hook', '')).toBeNull();
  });

  it('returns null with only telegram', () => {
    expect(validateChannels('', '', '-1001234567890')).toBeNull();
  });

  it('returns an error when no channels are present', () => {
    expect(validateChannels('', '', '')).toBe('Se requiere al menos un canal (email, webhook o telegram)');
  });
});
