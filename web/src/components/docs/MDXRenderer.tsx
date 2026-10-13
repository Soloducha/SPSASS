"use client";

import { MDXRemote } from 'next-mdx-remote/rsc';
import React from 'react';

/**
 * Custom components for MDX rendering.
 * Provides styled components for code blocks, tables, alerts, etc.
 */

type MDXComponentProps = {
  children?: React.ReactNode;
  className?: string;
  href?: string;
  [key: string]: unknown;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type MDXComponents = Record<string, React.ComponentType<any> | undefined>;

/**
 * Custom components for MDX rendering.
 * Provides styled components for code blocks, tables, alerts, etc.
 */
export const mdxComponents = {
  h1: ({ children, ...props }: MDXComponentProps) => (
    <h1 {...props} className="text-3xl font-bold text-gray-900 mb-6 mt-8 border-b border-gray-200 pb-2">
      {children}
    </h1>
  ),
  h2: ({ children, ...props }: MDXComponentProps) => (
    <h2 {...props} className="text-2xl font-semibold text-gray-800 mb-4 mt-10 border-b border-gray-100 pb-1">
      {children}
    </h2>
  ),
  h3: ({ children, ...props }: MDXComponentProps) => (
    <h3 {...props} className="text-xl font-medium text-gray-700 mb-3 mt-8">
      {children}
    </h3>
  ),
  p: ({ children, ...props }: MDXComponentProps) => (
    <p {...props} className="text-gray-600 leading-relaxed mb-4">
      {children}
    </p>
  ),
  ul: ({ children, ...props }: MDXComponentProps) => (
    <ul {...props} className="list-disc list-inside space-y-2 mb-4 text-gray-600">
      {children}
    </ul>
  ),
  ol: ({ children, ...props }: MDXComponentProps) => (
    <ol {...props} className="list-decimal list-inside space-y-2 mb-4 text-gray-600">
      {children}
    </ol>
  ),
  li: ({ children, ...props }: MDXComponentProps) => (
    <li {...props} className="ml-4 mb-1 leading-relaxed">
      {children}
    </li>
  ),
  a: ({ children, href, ...props }: MDXComponentProps) => (
    <a
      {...props}
      href={href as string}
      className="text-blue-600 hover:text-blue-800 underline hover:no-underline transition-colors"
      target={href?.startsWith('http') ? '_blank' : undefined}
      rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
    >
      {children}
    </a>
  ),
  code: ({ children, className, ...props }: MDXComponentProps) => {
    // Inline code
    if (!className?.startsWith('language-')) {
      return (
        <code
          {...props}
          className="bg-gray-100 text-red-600 px-1.5 py-0.5 rounded text-sm font-mono"
        >
          {children}
        </code>
      );
    }
    return <code {...props} className={className as string}>{children}</code>;
  },
  pre: ({ children, ...props }: MDXComponentProps) => (
    <div className="relative group my-6">
      <pre
        {...props}
        className="bg-gray-950 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm line-height-relaxed"
      >
        {children}
      </pre>
      <button
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 rounded"
        onClick={() => {
          const code = typeof children === 'string' ? children : '';
          navigator.clipboard.writeText(code);
        }}
        aria-label="Copiar código"
      >
        Copiar
      </button>
    </div>
  ),
  blockquote: ({ children, ...props }: MDXComponentProps) => (
    <blockquote
      {...props}
      className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-4 bg-blue-50 py-2 rounded-r"
    >
      {children}
    </blockquote>
  ),
  table: ({ children, ...props }: MDXComponentProps) => (
    <div className="overflow-x-auto my-6">
      <table {...props} className="min-w-full divide-y divide-gray-200">
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }: MDXComponentProps) => (
    <thead {...props} className="bg-gray-50">
      {children}
    </thead>
  ),
  tbody: ({ children, ...props }: MDXComponentProps) => (
    <tbody {...props} className="divide-y divide-gray-200">
      {children}
    </tbody>
  ),
  tr: ({ children, ...props }: MDXComponentProps) => (
    <tr {...props} className="hover:bg-gray-50">
      {children}
    </tr>
  ),
  th: ({ children, ...props }: MDXComponentProps) => (
    <th
      {...props}
      className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }: MDXComponentProps) => (
    <td {...props} className="px-4 py-3 text-sm text-gray-600">
      {children}
    </td>
  ),
  hr: ({ ...props }: MDXComponentProps) => (
    <hr {...props} className="my-8 border-gray-200" />
  ),
  strong: ({ children, ...props }: MDXComponentProps) => (
    <strong {...props} className="font-semibold text-gray-900">
      {children}
    </strong>
  ),
  em: ({ children, ...props }: MDXComponentProps) => (
    <em {...props} className="italic text-gray-700">
      {children}
    </em>
  ),
};

/**
 * Wrapper component for MDX content with custom components.
 */
interface MDXRendererProps {
  source: string;
  components?: MDXComponents;
}

export function MDXRenderer({ source, components }: MDXRendererProps) {
  return (
    <div className="prose prose-gray max-w-none">
      <MDXRemote source={source} components={{ ...mdxComponents, ...components }} />
    </div>
  );
}