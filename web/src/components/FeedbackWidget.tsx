'use client';

/**
 * Feedback Widget para Beta Cerrada (T5).
 *
 * Botón flotante que abre un modal con formulario de feedback.
 * POST a /api/v1/beta/feedback (requiere JWT de piloto activo).
 */

import { useState, FormEvent } from 'react';
import { ChatBubbleLeftRightIcon, XMarkIcon } from '@heroicons/react/24/outline';

interface FeedbackWidgetProps {
  /** URL actual de la página (se envía automáticamente) */
  pageUrl?: string;
  /** User agent (se captura automáticamente) */
  userAgent?: string;
  /** Screen resolution (se captura automáticamente) */
  screenResolution?: string;
}

type Category = 'bug' | 'feature' | 'ux' | 'performance' | 'other';

const CATEGORY_LABELS: Record<Category, string> = {
  bug: '🐛 Bug / Error',
  feature: '💡 Nueva funcionalidad',
  ux: '🎨 Experiencia de usuario (UX)',
  performance: '⚡ Rendimiento',
  other: '📝 Otro',
};

const CATEGORY_COLORS: Record<Category, string> = {
  bug: 'bg-red-50 text-red-700 border-red-200',
  feature: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  ux: 'bg-purple-50 text-purple-700 border-purple-200',
  performance: 'bg-amber-50 text-amber-700 border-amber-200',
  other: 'bg-gray-50 text-gray-700 border-gray-200',
};

export function FeedbackWidget({
  pageUrl = typeof window !== 'undefined' ? window.location.href : '',
  userAgent = typeof window !== 'undefined' ? navigator.userAgent : '',
  screenResolution = typeof window !== 'undefined' ? `${window.screen.width}x${window.screen.height}` : '',
}: FeedbackWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [formData, setFormData] = useState<{
    category: Category;
    title: string;
    description: string;
    rating: number | null;
  }>({
    category: 'feature',
    title: '',
    description: '',
    rating: null,
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        throw new Error('No hay sesión activa. Inicia sesión para enviar feedback.');
      }

      const response = await fetch('/api/v1/beta/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          category: formData.category,
          title: formData.title.trim(),
          description: formData.description.trim(),
          rating: formData.rating,
          page_url: pageUrl,
          user_agent: userAgent,
          screen_resolution: screenResolution,
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Error desconocido' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      setSuccess(true);
      setFormData({ category: 'feature', title: '', description: '', rating: null });

      // Auto-cerrar tras 2s
      setTimeout(() => {
        setIsOpen(false);
        setSuccess(false);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al enviar feedback');
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen && !success) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 bg-indigo-600 text-white rounded-full shadow-lg hover:bg-indigo-700 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        aria-label="Enviar feedback"
      >
        <ChatBubbleLeftRightIcon className="h-5 w-5" />
        <span className="hidden sm:inline font-medium text-sm">Feedback</span>
      </button>
    );
  }

  if (success) {
    return (
      <div className="fixed bottom-6 right-6 z-50 w-full max-w-md animate-slide-up">
        <div className="bg-white rounded-xl shadow-xl border border-green-200 p-6">
          <div className="flex items-center gap-3 text-green-600">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="font-semibold">¡Gracias por tu feedback!</p>
          </div>
          <p className="mt-2 text-sm text-gray-600">Tu opinión nos ayuda a mejorar SPSAAS.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-md animate-slide-up">
      <div className="bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100 bg-gray-50">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2">
            <ChatBubbleLeftRightIcon className="h-5 w-5 text-indigo-600" />
            Feedback Beta
          </h2>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Cerrar"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm" role="alert">
              {error}
            </div>
          )}

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Categoría <span className="text-red-500">*</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(['bug', 'feature', 'ux', 'performance', 'other'] as Category[]).map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, category: cat }))}
                  className={`p-3 rounded-lg border-2 text-left transition-all ${
                    formData.category === cat
                      ? `border-indigo-500 ${CATEGORY_COLORS[cat].replace('bg-', 'bg-').replace('text-', 'text-').replace('border-', 'border-')}`
                      : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
                  }`}
                >
                  <p className="font-medium text-sm">{CATEGORY_LABELS[cat]}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Title */}
          <div>
            <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
              Título <span className="text-red-500">*</span>
            </label>
            <input
              id="title"
              type="text"
              required
              maxLength={255}
              value={formData.title}
              onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
              placeholder="Resume el feedback en una frase"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
            />
          </div>

          {/* Description */}
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Descripción <span className="text-red-500">*</span>
            </label>
            <textarea
              id="description"
              required
              maxLength={5000}
              rows={4}
              value={formData.description}
              onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Describe el problema, la idea o la mejora con detalle..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y"
            />
          </div>

          {/* Rating */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Valoración (opcional)
            </label>
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, rating: prev.rating === star ? null : star }))}
                  className={`p-1 rounded transition-colors ${
                    formData.rating && formData.rating >= star
                      ? 'text-amber-500'
                      : 'text-gray-300 hover:text-amber-300'
                  }`}
                  aria-label={`${star} estrella${star > 1 ? 's' : ''}`}
                >
                  <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.88-1.515a1 1 0 00-1.175 0l-2.88 1.515c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                </button>
              ))}
            </div>
            {formData.rating && (
              <p className="mt-1 text-sm text-gray-500">{formData.rating} de 5 estrellas</p>
            )}
          </div>

          {/* Submit */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
              disabled={loading}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Enviando…' : 'Enviar feedback'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Keyframes para animación
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slide-up {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .animate-slide-up { animation: slide-up 0.2s ease-out; }
  `;
  document.head.appendChild(style);
}