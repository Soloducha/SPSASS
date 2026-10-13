"use client";

export function FinalCTA() {
  return (
    <section className="py-20 bg-gray-900" aria-labelledby="cta-heading">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 id="cta-heading" className="text-3xl font-bold text-white mb-6">
          ¿Listo para empezar?
        </h2>
        <p className="text-lg text-gray-300 mb-10 max-w-2xl mx-auto">
          Únete a cientos de equipos que ya monitorizan su infraestructura con SPSAAS.
          Empieza gratis hoy, sin tarjeta de crédito.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/onboarding"
            className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-lg font-medium text-lg text-white bg-blue-600 hover:bg-blue-700 transition-colors"
          >
            Empezar gratis
            <svg className="ml-2 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </a>
          <a
            href="/contact"
            className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-lg font-medium text-lg text-gray-100 border border-gray-700 hover:bg-gray-800 transition-colors"
          >
            Contactar ventas
          </a>
        </div>
        <p className="mt-8 text-gray-500 text-sm">
          ¿Preguntas? <a href="/contact" className="text-blue-400 hover:text-blue-300 underline">Habla con nuestro equipo</a>
        </p>
      </div>
    </section>
  );
}