/** Generic form component with validation and Server Action integration. */

'use client';

import { useState, type FormEvent, type ReactNode } from 'react';

export interface FormField {
  name: string;
  label: string;
  type?: 'text' | 'number' | 'select' | 'textarea' | 'checkbox';
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  validation?: (value: string) => string | null;
  helpText?: string;
  disabled?: boolean;
  className?: string;
}

export interface EntityFormProps<T extends Record<string, unknown>> {
  fields: FormField[];
  initialData?: Partial<T>;
  action: (formData: FormData) => void;
  submitLabel?: string;
  cancelHref?: string;
  isLoading?: boolean;
  title?: string;
  description?: string;
  children?: ReactNode;
}

export function EntityForm<T extends Record<string, unknown>>({
  fields,
  initialData = {},
  action,
  submitLabel = 'Guardar',
  cancelHref,
  isLoading: externalLoading,
  title,
  description,
  children,
}: EntityFormProps<T>) {
  const [formData, setFormData] = useState<Partial<T>>(initialData);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [localLoading, setLocalLoading] = useState(false);

  const isLoading = externalLoading || localLoading;

  const validateField = (name: string, value: string): string | null => {
    const field = fields.find((f) => f.name === name);
    if (!field) return null;

    if (field.required && (!value || value.trim() === '')) {
      return `${field.label} es requerido`;
    }

    if (field.validation) {
      return field.validation(value);
    }

    return null;
  };

  const handleChange = (name: string, value: string | number | boolean) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
    const error = validateField(name, String(value));
    setErrors((prev) => ({ ...prev, [name]: error || '' }));
  };

  const validateAll = (): boolean => {
    let hasErrors = false;
    const newErrors: Record<string, string> = {};
    const newTouched: Record<string, boolean> = {};

    fields.forEach((field) => {
      const value = String(formData[field.name] ?? '');
      const error = validateField(field.name, value);
      if (error) {
        newErrors[field.name] = error;
        hasErrors = true;
      }
      newTouched[field.name] = true;
    });

    setErrors(newErrors);
    setTouched(newTouched);
    return !hasErrors;
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!validateAll()) return;

    setLocalLoading(true);
    try {
      const fd = new FormData();
      Object.entries(formData).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          fd.append(key, String(value));
        }
      });
      await action(fd);
      // Éxito: el Server Action debería hacer redirect
    } finally {
      setLocalLoading(false);
    }
  };

  const renderField = (field: FormField) => {
    const error = touched[field.name] ? errors[field.name] : null;
    const hasError = !!error;
    const value = formData[field.name] as string | number | boolean | undefined;

    const inputProps = {
      id: field.name,
      name: field.name,
      disabled: field.disabled || isLoading,
      'aria-invalid': hasError,
      'aria-describedby': error ? `${field.name}-error` : field.helpText ? `${field.name}-help` : undefined,
      className: `w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 disabled:text-gray-500 ${hasError ? 'border-red-500' : 'border-gray-300'} ${field.className || ''}`,
    };

    const stringValue = value === undefined ? '' : String(value);

    switch (field.type) {
      case 'select':
        return (
          <div>
            <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 mb-1">
              {field.label} {field.required && <span className="text-red-500" aria-hidden="true">*</span>}
            </label>
            <select {...inputProps} value={stringValue} onChange={(e) => handleChange(field.name, e.target.value)}>
              <option value="">Seleccionar...</option>
              {field.options?.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {field.helpText && !error && <p id={`${field.name}-help`} className="mt-1 text-sm text-gray-500">{field.helpText}</p>}
            {error && <p id={`${field.name}-error`} className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
          </div>
        );
      case 'checkbox':
        return (
          <div className="flex items-center">
            <input
              type="checkbox"
              {...inputProps}
              checked={Boolean(value)}
              onChange={(e) => handleChange(field.name, e.target.checked)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <label htmlFor={field.name} className="ml-2 block text-sm text-gray-700">
              {field.label}
            </label>
          </div>
        );
      case 'textarea':
        return (
          <div>
            <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 mb-1">
              {field.label} {field.required && <span className="text-red-500" aria-hidden="true">*</span>}
            </label>
            <textarea
              {...inputProps}
              value={stringValue}
              onChange={(e) => handleChange(field.name, e.target.value)}
              rows={3}
            />
            {field.helpText && !error && <p id={`${field.name}-help`} className="mt-1 text-sm text-gray-500">{field.helpText}</p>}
            {error && <p id={`${field.name}-error`} className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
          </div>
        );
      case 'number':
        return (
          <div>
            <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 mb-1">
              {field.label} {field.required && <span className="text-red-500" aria-hidden="true">*</span>}
            </label>
            <input
              type="number"
              {...inputProps}
              value={stringValue}
              onChange={(e) => handleChange(field.name, e.target.valueAsNumber)}
              min={0}
            />
            {field.helpText && !error && <p id={`${field.name}-help`} className="mt-1 text-sm text-gray-500">{field.helpText}</p>}
            {error && <p id={`${field.name}-error`} className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
          </div>
        );
      default:
        return (
          <div>
            <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 mb-1">
              {field.label} {field.required && <span className="text-red-500" aria-hidden="true">*</span>}
            </label>
            <input
              type="text"
              {...inputProps}
              value={stringValue}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder={field.placeholder}
            />
            {field.helpText && !error && <p id={`${field.name}-help`} className="mt-1 text-sm text-gray-500">{field.helpText}</p>}
            {error && <p id={`${field.name}-error`} className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
          </div>
        );
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {title && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
          {description && <p className="mt-1 text-sm text-gray-500">{description}</p>}
        </div>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        {fields.map((field) => (
          <div key={field.name}>{renderField(field)}</div>
        ))}
      </div>

      {children}

      <div className="flex justify-end gap-3 pt-4 border-t">
        {cancelHref && (
          <a
            href={cancelHref}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            aria-label="Cancelar"
          >
            Cancelar
          </a>
        )}
        <button
          type="submit"
          disabled={isLoading}
          className="px-4 py-2 bg-blue-600 border border-transparent rounded-md text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Guardando...
            </span>
          ) : (
            submitLabel
          )}
        </button>
      </div>
    </form>
  );
}