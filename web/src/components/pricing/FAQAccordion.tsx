"use client";

import { useState } from 'react';
import { MDXRemote } from 'next-mdx-remote/rsc';
import React from 'react';

type MDXComponentProps = {
  children?: React.ReactNode;
  className?: string;
  href?: string;
  [key: string]: unknown;
};

type MDXComponents = Record<string, React.ComponentType<MDXComponentProps> | undefined>;

interface FAQAccordionProps {
  source: string;
  components?: MDXComponents;
}

interface FAQItem {
  question: string;
  answer: string;
}

/**
 * Parses FAQ from MDX content.
 * Expected format:
 * ## Pregunta 1
 * Respuesta 1
 * 
 * ## Pregunta 2
 * Respuesta 2
 */
function parseFAQ(content: string): FAQItem[] {
  const items: FAQItem[] = [];
  const lines = content.split('\n');
  let currentQuestion = '';
  let currentAnswer: string[] = [];
  let inAnswer = false;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      // Save previous item
      if (currentQuestion) {
        items.push({
          question: currentQuestion,
          answer: currentAnswer.join('\n').trim(),
        });
      }
      // Start new item
      currentQuestion = line.replace('## ', '').trim();
      currentAnswer = [];
      inAnswer = true;
    } else if (inAnswer) {
      currentAnswer.push(line);
    }
  }

  // Save last item
  if (currentQuestion) {
    items.push({
      question: currentQuestion,
      answer: currentAnswer.join('\n').trim(),
    });
  }

  return items;
}

export function FAQAccordion({ source, components }: FAQAccordionProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const faqItems = parseFAQ(source);

  const mdxComponents: MDXComponents = {
    ...components,
    h1: ({ children, ...props }) => <h1 {...props} className="text-2xl font-bold text-gray-900 mb-2">{children}</h1>,
    h2: ({ children, ...props }) => <h2 {...props} className="text-xl font-semibold text-gray-800 mb-2">{children}</h2>,
    h3: ({ children, ...props }) => <h3 {...props} className="text-lg font-medium text-gray-700 mb-2">{children}</h3>,
    p: ({ children, ...props }) => <p {...props} className="text-gray-600 leading-relaxed mb-4">{children}</p>,
    ul: ({ children, ...props }) => <ul {...props} className="list-disc list-inside space-y-2 mb-4 text-gray-600">{children}</ul>,
    ol: ({ children, ...props }) => <ol {...props} className="list-decimal list-inside space-y-2 mb-4 text-gray-600">{children}</ol>,
    li: ({ children, ...props }) => <li {...props} className="ml-4 mb-1 leading-relaxed">{children}</li>,
    a: ({ children, href, ...props }) => (
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
    code: ({ children, className, ...props }) => (
      !className?.startsWith('language-') ? (
        <code {...props} className="bg-gray-100 text-red-600 px-1.5 py-0.5 rounded text-sm font-mono">{children}</code>
      ) : (
        <code {...props} className={className}>{children}</code>
      )
    ),
    pre: ({ children, ...props }) => (
      <div className="relative group my-4">
        <pre {...props} className="bg-gray-950 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm line-height-relaxed">{children}</pre>
        <button className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 rounded" onClick={() => navigator.clipboard.writeText(typeof children === 'string' ? children : '')} aria-label="Copiar código">Copiar</button>
      </div>
    ),
    blockquote: ({ children, ...props }) => <blockquote {...props} className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-4 bg-blue-50 py-2 rounded-r">{children}</blockquote>,
    table: ({ children, ...props }) => <div className="overflow-x-auto my-4"><table {...props} className="min-w-full divide-y divide-gray-200">{children}</table></div>,
    thead: ({ children, ...props }) => <thead {...props} className="bg-gray-50">{children}</thead>,
    tbody: ({ children, ...props }) => <tbody {...props} className="divide-y divide-gray-200">{children}</tbody>,
    tr: ({ children, ...props }) => <tr {...props} className="hover:bg-gray-50">{children}</tr>,
    th: ({ children, ...props }) => <th {...props} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{children}</th>,
    td: ({ children, ...props }) => <td {...props} className="px-4 py-3 text-sm text-gray-600">{children}</td>,
    hr: ({ ...props }) => <hr {...props} className="my-8 border-gray-200" />,
    strong: ({ children, ...props }) => <strong {...props} className="font-semibold text-gray-900">{children}</strong>,
    em: ({ children, ...props }) => <em {...props} className="italic text-gray-700">{children}</em>,
  };

  return (
    <section className="py-16" aria-labelledby="faq-heading">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <header className="text-center mb-12">
          <h2 id="faq-heading" className="text-3xl font-bold text-gray-900 mb-4">
            Preguntas Frecuentes
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Respuestas a las dudas más comunes sobre planes, facturación, límites y migraciones
          </p>
        </header>

        <div className="space-y-4" role="list" aria-label="Preguntas frecuentes">
          {faqItems.map((item, index) => (
            <FAQItem
              key={index}
              index={index}
              question={item.question}
              answer={item.answer}
              isOpen={openIndex === index}
              onToggle={() => setOpenIndex(openIndex === index ? null : index)}
              components={mdxComponents}
            />
          ))}
        </div>

        <div className="mt-12 text-center">
          <p className="text-gray-600 mb-4">
            ¿No encontraste tu respuesta?
          </p>
          <a
            href="/contact"
            className="inline-flex items-center px-6 py-3 rounded-lg font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors"
          >
            Contáctanos
            <svg className="ml-2 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
            </svg>
          </a>
        </div>
      </div>
    </section>
  );
}

function FAQItem({
  index,
  question,
  answer,
  isOpen,
  onToggle,
  components,
}: {
  index: number;
  question: string;
  answer: string;
  isOpen: boolean;
  onToggle: () => void;
  components: Record<string, React.ComponentType | undefined>;
}) {
  return (
    <details
      className="group bg-white border border-gray-200 rounded-xl overflow-hidden transition-all duration-200"
      open={isOpen}
      onToggle={onToggle}
      role="listitem"
    >
      <summary className="flex items-center justify-between p-6 cursor-pointer list-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
        <h3 className="text-lg font-semibold text-gray-900 pr-10">{question}</h3>
        <svg
          className="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform duration-200 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </summary>
      <div className="px-6 pb-6 animate-slide-down">
        <div className="prose prose-gray max-w-none">
          <MDXRemote source={answer} components={components as any} />
        </div>
      </div>
    </details>
  );
}