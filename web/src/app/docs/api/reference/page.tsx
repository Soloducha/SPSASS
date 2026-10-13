"use client";

import { useEffect, useRef } from 'react';
import SwaggerUI from 'swagger-ui-react';
import 'swagger-ui-dist/swagger-ui.css';

export default function SwaggerPage() {
  const specRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!specRef.current) return;

    // Fetch the OpenAPI spec from the API
    fetch('/api/openapi.json')
      .then((res) => res.json())
      .then((spec) => {
        if (specRef.current) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (window as any).SwaggerUIBundle({
            spec,
            domNode: specRef.current,
            deepLinking: true,
            presets: [
              (window as any).SwaggerUIBundle.presets.apis,
              (window as any).SwaggerUIBundle.standalonePreset,
            ],
            layout: "BaseLayout",
            tryItOutEnabled: true,
            filter: true,
            showExtensions: true,
            showCommonExtensions: true,
            syntaxHighlight: {
              theme: "monokai",
            },
            oauth2RedirectUrl: window.location.origin + "/docs/api/oauth2-redirect.html",
          });
        }
      })
      .catch(console.error);
  }, []);

  return (
    <div className="prose prose-gray max-w-none">
      <header className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">API Reference</h1>
        <p className="text-xl text-gray-600 mb-6">
          Referencia interactiva de la API REST de SPSAAS. Usa el botón <strong>Authorize</strong> para autenticarte y probar endpoints.
        </p>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-8">
          <h3 className="font-semibold text-blue-800 mb-2">Autenticación</h3>
          <ul className="text-sm text-blue-700 space-y-1">
            <li>
              {'• '}
              <strong>Web (JWT)</strong>{' '}: Click <strong>Authorize</strong>{' '}→{' '}
              <code>{'Bearer <token>'}</code>
            </li>
            <li>
              {'• '}
              <strong>Agentes (API Key)</strong>{' '}: Click <strong>Authorize</strong>{' '}→{' '}
              <code>spsk_xxx</code>
            </li>
          </ul>
        </div>
      </header>

      <div ref={specRef as React.RefObject<HTMLDivElement>} style={{ minHeight: '800px' }} />
    </div>
  );
}