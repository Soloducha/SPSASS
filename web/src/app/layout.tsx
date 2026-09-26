import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'SPSAAS',
  description: 'Monitoreo para entornos legacy y Linux',
};

const navigation = [
  { name: 'Inicio', href: '/' },
  { name: 'Alertas', href: '/alertas' },
] as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="antialiased bg-gray-50 min-h-screen">
        <header className="border-b border-gray-200 bg-white sticky top-0 z-10" role="banner">
          <div className="mx-auto max-w-6xl px-4">
            <nav className="flex h-16 items-center justify-between" aria-label="Navegación principal">
              <Link
                href="/"
                className="text-xl font-bold text-gray-900 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 rounded-md"
                aria-label="SPSAAS - Inicio"
              >
                SPSAAS
              </Link>
              <ul className="flex items-center gap-6" role="list">
                {navigation.map((item) => (
                  <li key={item.name}>
                    <Link
                      href={item.href}
                      className="text-sm font-medium text-gray-700 hover:text-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 rounded-md px-2 py-1 transition-colors"
                    >
                      {item.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </header>
        <main className="flex-1" id="main-content" role="main">
          {children}
        </main>
        <footer className="border-t border-gray-200 bg-white" role="contentinfo">
          <div className="mx-auto max-w-6xl px-4 py-4 text-center text-xs text-gray-500">
            SPSAAS — Monitoreo para entornos legacy y Linux
          </div>
        </footer>
      </body>
    </html>
  );
}