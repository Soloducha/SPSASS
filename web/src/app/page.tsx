export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 py-20">
      <div className="w-full max-w-2xl text-center">
        <h1 className="mb-6 text-4xl font-bold text-gray-900 sm:text-5xl">
          SPSAAS
        </h1>
        <p className="mb-8 text-lg text-gray-600 sm:text-xl">
          Monitoreo para entornos legacy y Linux — sitio en construcción
        </p>
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <p className="text-gray-500">
            Próximamente: dashboards, alertas, métricas en tiempo real y más.
          </p>
        </div>
      </div>
    </main>
  );
}