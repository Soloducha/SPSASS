/** Generic table component for entity lists with pagination. */

'use client';

import { type ReactNode } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

export interface PaginationProps {
  currentPage: number;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  isLoading?: boolean;
}

export function Pagination({ currentPage, hasNext, onPrevious, onNext, isLoading }: PaginationProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t">
      <div className="flex items-center gap-2">
        <button
          onClick={onPrevious}
          disabled={currentPage === 0 || isLoading}
          className="p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Página anterior"
        >
          <ChevronLeftIcon className="h-5 w-5" />
        </button>
        <span className="text-sm text-gray-600 min-w-[3rem] text-center">
          Página {currentPage + 1}
        </span>
        <button
          onClick={onNext}
          disabled={!hasNext || isLoading}
          className="p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Página siguiente"
        >
          <ChevronRightIcon className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

export type ColumnType =
  | 'text'
  | 'badge'
  | 'date'
  | 'boolean'
  | 'link'
  | 'custom';

export interface ColumnConfig<T> {
  key: string;
  header: string;
  type?: ColumnType;
  /** For 'badge' type: maps value to variant */
  badgeVariantMap?: Record<string, 'default' | 'success' | 'warning' | 'error' | 'info'>;
  /** For 'link' type: base URL path */
  linkBasePath?: string;
  /** For 'date' type: locale string options */
  dateOptions?: Intl.DateTimeFormatOptions;
  /** For 'boolean' type: true/false labels */
  booleanLabels?: { true: string; false: string };
  className?: string;
  /** For 'text' type: truncate to N characters */
  truncate?: number;
  /** Custom cell renderer key - implemented in renderCell() */
  customRenderer?: string;
}

export interface EntityTableProps<T> {
  columns: ColumnConfig<T>[];
  data: T[];
  isLoading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  pagination?: PaginationProps;
  rowKey: (item: T) => string;
  onRowClick?: (item: T) => void;
  actions?: (item: T) => ReactNode;
}

function renderCell<T>(item: T, col: ColumnConfig<T>): ReactNode {
  const value = (item as Record<string, unknown>)[col.key];

  if (value === undefined || value === null) {
    return <span className="text-gray-400">—</span>;
  }

  switch (col.type) {
    case 'badge': {
      const variant = col.badgeVariantMap?.[String(value)] ?? 'default';
      return (
        <span
          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
            {
              default: 'bg-gray-100 text-gray-800',
              success: 'bg-green-100 text-green-800',
              warning: 'bg-yellow-100 text-yellow-800',
              error: 'bg-red-100 text-red-800',
              info: 'bg-blue-100 text-blue-800',
            }[variant]
          }`}
        >
          {String(value)}
        </span>
      );
    }
    case 'date': {
      if (!value) return <span className="text-gray-400">—</span>;
      const date = new Date(String(value));
      return date.toLocaleString(undefined, col.dateOptions);
    }
    case 'boolean': {
      const labels = col.booleanLabels ?? { true: 'Sí', false: 'No' };
      return <span>{Boolean(value) ? labels.true : labels.false}</span>;
    }
    case 'link': {
      const basePath = col.linkBasePath ?? '';
      const href = `${basePath}${value}`;
      return (
        <a href={href} className="text-blue-600 hover:underline font-medium">
          {String(value)}
        </a>
      );
    }
    case 'custom':
      // Custom renderers are handled by the parent via a map
      return String(value);
    default: {
      const str = String(value);
      if (col.truncate && str.length > col.truncate) {
        return str.slice(0, col.truncate) + '…';
      }
      return str;
    }
  }
}

export function EntityTable<T>({
  columns,
  data,
  isLoading,
  error,
  emptyMessage = 'No hay datos',
  pagination,
  rowKey,
  onRowClick,
  actions,
}: EntityTableProps<T>) {
  if (isLoading) {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className={`px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ${col.className || ''}`}
                >
                  {col.header}
                </th>
              ))}
              {actions && (
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Acciones
                </th>
              )}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={`skeleton-${i}`} className="animate-pulse">
                {columns.map((col) => (
                  <td key={col.key} className={`px-6 py-4 whitespace-nowrap ${col.className || ''}`}>
                    <div className="h-4 bg-gray-200 rounded w-3/4" />
                  </td>
                ))}
                {actions && (
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="h-6 w-20 bg-gray-200 rounded" />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-6 text-center">
        <p className="text-red-600" role="alert">{error}</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="px-4 py-12 text-center">
        <p className="text-gray-500">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ${col.className || ''}`}
              >
                {col.header}
              </th>
            ))}
            {actions && (
              <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Acciones
              </th>
            )}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {data.map((item) => (
            <tr
              key={rowKey(item)}
              className={onRowClick ? 'hover:bg-gray-50 cursor-pointer' : ''}
              onClick={() => onRowClick?.(item)}
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-6 py-4 whitespace-nowrap text-sm text-gray-900 ${col.className || ''}`}>
                  {renderCell(item, col)}
                </td>
              ))}
              {actions && (
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  {actions(item)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {pagination && <Pagination {...pagination} />}
    </div>
  );
}

// Badge component for status
export interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
  className?: string;
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  const variants = {
    default: 'bg-gray-100 text-gray-800',
    success: 'bg-green-100 text-green-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-800',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variants[variant]} ${className || ''}`}>
      {children}
    </span>
  );
}