import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SPSAAS',
  description: 'Monitoreo para entornos legacy y Linux',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="antialiased bg-gray-50 min-h-screen">{children}</body>
    </html>
  );
}