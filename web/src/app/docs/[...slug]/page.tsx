import { getDoc, getGroupDocs, getSidebarGroups } from '@/lib/docs/utils';
import { MDXRenderer } from '@/components/docs/MDXRenderer';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';

interface Props {
  params: Promise<{ slug: string[] }>;
}

export async function generateStaticParams() {
  // For now, generate params for all known docs
  // In production, you'd want to scan the docs directory
  return [
    { slug: ['installation', 'linux-systemd'] },
    { slug: ['installation', 'windows-nssm'] },
    { slug: ['alerts', 'overview'] },
    { slug: ['reports', 'overview'] },
    { slug: ['troubleshooting', 'common-issues'] },
    { slug: ['api', 'reference'] },
  ];
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const resolvedParams = await params;
  const slug = resolvedParams.slug.join('/');
  const doc = getDoc(slug);

  if (!doc) {
    return { title: 'Documentación no encontrada' };
  }

  return {
    title: `${doc.metadata.title} | SPSAAS Docs`,
    description: doc.metadata.description,
  };
}

export default async function DocsPage({ params }: Props) {
  const resolvedParams = await params;
  const slug = resolvedParams.slug.join('/');

  // Handle root /docs
  if (!slug || slug === '') {
    const groups = getSidebarGroups();
    return (
      <div className="prose prose-gray max-w-none">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">Documentación SPSAAS</h1>
        <p className="text-gray-600 text-lg mb-8">
          Bienvenido a la documentación oficial de SPSAAS. Usa la barra lateral para navegar
          o la búsqueda para encontrar lo que necesitas.
        </p>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => (
            <div
              key={group.slug}
              className="border border-gray-200 rounded-lg p-6 hover:border-blue-300 hover:bg-blue-50 transition-colors"
            >
              <h2 className="text-xl font-semibold text-gray-900 mb-3">{group.title}</h2>
              <ul className="space-y-2">
                {group.items.slice(0, 4).map((item) => (
                  <li key={item.slug}>
                    <a
                      href={`/docs/${group.slug}/${item.slug}`}
                      className="text-blue-600 hover:text-blue-800 underline"
                    >
                      {item.title}
                    </a>
                  </li>
                ))}
                {group.items.length > 4 && (
                  <li>
                    <a
                      href={`/docs/${group.slug}`}
                      className="text-sm text-blue-600 hover:underline"
                    >
                      Ver todos ({group.items.length})...
                    </a>
                  </li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const doc = getDoc(slug);

  if (!doc) {
    notFound();
  }

  // Get sibling docs for prev/next navigation
  const groups = getSidebarGroups();
  let currentGroup = '';
  let currentIndex = -1;
  let allItems: { slug: string; title: string; group: string }[] = [];

  for (const group of groups) {
    for (const item of group.items) {
      allItems.push({ slug: `${group.slug}/${item.slug}`, title: item.title, group: group.slug });
      if (`${group.slug}/${item.slug}` === slug) {
        currentGroup = group.slug;
        currentIndex = allItems.length - 1;
      }
    }
  }

  const prevDoc = currentIndex > 0 ? allItems[currentIndex - 1] : null;
  const nextDoc = currentIndex < allItems.length - 1 ? allItems[currentIndex + 1] : null;

  return (
    <article className="prose prose-gray max-w-none">
      <header className="mb-8">
        <nav className="text-sm text-gray-500 mb-4" aria-label="Breadcrumb">
          <ol className="flex items-center space-x-2">
            <li>
              <a href="/docs" className="hover:underline">Docs</a>
            </li>
            <li aria-hidden="true">/</li>
            {doc.metadata.sidebar && (
              <>
                <li>
                  <a href={`/docs/${doc.metadata.sidebar}`} className="hover:underline">
                    {doc.metadata.sidebar.charAt(0).toUpperCase() + doc.metadata.sidebar.slice(1)}
                  </a>
                </li>
                <li aria-hidden="true">/</li>
              </>
            )}
            <li aria-current="page" className="text-gray-900 font-medium">
              {doc.metadata.title}
            </li>
          </ol>
        </nav>

        <h1 className="text-4xl font-bold text-gray-900 mb-4">{doc.metadata.title}</h1>
        {doc.metadata.description && (
          <p className="text-xl text-gray-600 mb-6">{doc.metadata.description}</p>
        )}

        <div className="flex flex-wrap gap-2 mb-8 text-sm text-gray-500">
          {doc.metadata.sidebar && (
            <span className="px-2 py-1 bg-gray-100 rounded">{doc.metadata.sidebar}</span>
          )}
        </div>
      </header>

      <MDXRenderer source={doc.content} />

      {/* Prev/Next navigation */}
      {(prevDoc || nextDoc) && (
        <nav className="mt-16 pt-8 border-t border-gray-200" aria-label="Pagination">
          <div className="flex justify-between">
            {prevDoc && (
              <a
                href={`/docs/${prevDoc.slug}`}
                className="text-blue-600 hover:text-blue-800 flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span>Anterior: {prevDoc.title}</span>
              </a>
            )}
            {nextDoc && (
              <a
                href={`/docs/${nextDoc.slug}`}
                className="text-blue-600 hover:text-blue-800 flex items-center gap-2"
              >
                <span>Siguiente: {nextDoc.title}</span>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </a>
            )}
          </div>
        </nav>
      )}
    </article>
  );
}