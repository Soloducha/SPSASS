/**
 * Docs utility functions - Server-side only.
 * These functions use fs and should only be imported in server components.
 */

import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';

const DOCS_ROOT = path.join(process.cwd(), 'docs', 'content', 'en');

export interface DocMetadata {
  title: string;
  description?: string;
  sidebar?: string;
  order?: number;
  [key: string]: unknown;
}

export interface DocContent {
  slug: string;
  metadata: DocMetadata;
  content: string;
}

export interface SidebarGroup {
  title: string;
  slug: string;
  items: SidebarItem[];
}

export interface SidebarItem {
  slug: string;
  title: string;
  order?: number;
}

/**
 * Get all sidebar groups (installation, alerts, reports, troubleshooting, api)
 */
export function getSidebarGroups() {
  const groups = [
    { title: 'Instalación', slug: 'installation', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Alertas', slug: 'alerts', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Reportes', slug: 'reports', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Troubleshooting', slug: 'troubleshooting', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'API Reference', slug: 'api', items: [] as { slug: string; title: string; order?: number }[] },
  ];

  for (const group of groups) {
    const groupPath = path.join(DOCS_ROOT, group.slug);
    if (fs.existsSync(groupPath)) {
      const files = fs.readdirSync(groupPath).filter(f => f.endsWith('.mdx'));
      for (const file of files) {
        const filePath = path.join(groupPath, file);
        const source = fs.readFileSync(filePath, 'utf8');
        const { data } = matter(source);
        const slug = file.replace('.mdx', '');
        group.items.push({
          slug,
          title: data.title || slug,
          order: data.order,
        });
      }
      // Sort by order
      group.items.sort((a, b) => (a.order || 999) - (b.order || 999));
    }
  }

  return groups;
}

/**
 * Get a single doc by slug (e.g., 'installation/linux-systemd')
 */
export function getDoc(slug: string) {
  // slug format: "group/file" or just "group"
  const parts = slug.split('/');
  if (parts.length < 2) return null;

  const group = parts[0];
  const file = parts.slice(1).join('/');
  const filePath = path.join(DOCS_ROOT, group, `${file}.mdx`);

  if (!fs.existsSync(filePath)) return null;

  const source = fs.readFileSync(filePath, 'utf8');
  const { data, content } = matter(source);

  return {
    slug,
    metadata: data as { title: string; description?: string; sidebar?: string; order?: number },
    content,
  };
}

/**
 * Get all docs for a sidebar group
 */
export function getGroupDocs(groupSlug: string) {
  const groupPath = path.join(DOCS_ROOT, groupSlug);
  if (!fs.existsSync(groupPath)) return [];

  const files = fs.readdirSync(groupPath).filter(f => f.endsWith('.mdx'));
  const docs = [];

  for (const file of files) {
    const filePath = path.join(groupPath, file);
    const source = fs.readFileSync(filePath, 'utf8');
    const { data, content } = matter(source);
    const slug = `${groupSlug}/${file.replace('.mdx', '')}`;
    docs.push({
      slug,
      metadata: data as { title: string; description?: string; sidebar?: string; order?: number },
      content,
    });
  }

  return docs.sort((a, b) => (a.metadata.order || 999) - (b.metadata.order || 999));
}

/**
 * Search docs by query (simple text search in title + content)
 */
export function searchDocs(query: string) {
  const groups = [
    { title: 'Instalación', slug: 'installation', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Alertas', slug: 'alerts', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Reportes', slug: 'reports', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'Troubleshooting', slug: 'troubleshooting', items: [] as { slug: string; title: string; order?: number }[] },
    { title: 'API Reference', slug: 'api', items: [] as { slug: string; title: string; order?: number }[] },
  ];

  const results = [];
  const lowerQuery = query.toLowerCase();

  for (const group of groups) {
    const groupPath = path.join(DOCS_ROOT, group.slug);
    if (!fs.existsSync(groupPath)) continue;

    const files = fs.readdirSync(groupPath).filter(f => f.endsWith('.mdx'));
    for (const file of files) {
      const filePath = path.join(groupPath, file);
      const source = fs.readFileSync(filePath, 'utf8');
      const { data, content } = matter(source);
      const slug = `${group.slug}/${file.replace('.mdx', '')}`;

      const searchable = `${data.title} ${content}`.toLowerCase();
      if (searchable.includes(lowerQuery)) {
        results.push({
          slug,
          metadata: data as { title: string; description?: string; sidebar?: string; order?: number },
          content,
        });
      }
    }
  }

  return results;
}