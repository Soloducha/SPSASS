"use client";

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';

interface SearchResult {
  slug: string;
  title: string;
  description?: string;
  sidebar?: string;
}

export function Search() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Debounced search via API
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (query.length >= 2) {
        setIsLoading(true);
        try {
          const response = await fetch(`/api/docs/search?q=${encodeURIComponent(query)}`);
          const data = await response.json();
          setResults(data.results || []);
          setShowResults(true);
          setSelectedIndex(-1);
        } catch (error) {
          console.error('Search error:', error);
          setResults([]);
        } finally {
          setIsLoading(false);
        }
      } else {
        setResults([]);
        setShowResults(false);
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [query]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!showResults) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, -1));
          break;
        case 'Enter':
          e.preventDefault();
          if (selectedIndex >= 0 && results[selectedIndex]) {
            window.location.href = `/docs/${results[selectedIndex].slug}`;
          }
          break;
        case 'Escape':
          setShowResults(false);
          setSelectedIndex(-1);
          inputRef.current?.blur();
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [results, selectedIndex, showResults]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (resultsRef.current && !resultsRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={resultsRef}>
      <label htmlFor="doc-search" className="sr-only">
        Buscar en la documentación
      </label>
      <div className="relative">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <input
          ref={inputRef}
          id="doc-search"
          type="search"
          placeholder="Buscar docs... (/) "
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => query.length >= 2 && setShowResults(true)}
          onBlur={() => setTimeout(() => setShowResults(false), 200)}
          className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent placeholder-gray-400"
          aria-autocomplete="list"
          aria-controls="search-results"
          aria-expanded={showResults && results.length > 0}
          autoComplete="off"
        />
        <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 px-1.5 py-0.5 bg-gray-100 rounded">
          /
        </kbd>
      </div>

      {showResults && (
        <div
          id="search-results"
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-96 overflow-y-auto z-50"
        >
          {isLoading && (
            <div className="px-4 py-3 text-center text-gray-500 text-sm">
              Buscando...
            </div>
          )}
          {!isLoading && results.length === 0 && query.length >= 2 && (
            <div className="px-4 py-3 text-center text-gray-500 text-sm">
              No se encontraron resultados para "{query}"
            </div>
          )}
          {!isLoading && results.map((result, index) => (
            <Link
              key={result.slug}
              href={`/docs/${result.slug}`}
              role="option"
              aria-selected={index === selectedIndex}
              className={`block px-4 py-3 hover:bg-gray-50 transition-colors ${
                index === selectedIndex ? 'bg-blue-50 text-blue-700' : ''
              }`}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 font-mono">{result.sidebar || 'docs'}</span>
                <span className="text-gray-600 font-medium">{result.title}</span>
              </div>
              {result.description && (
                <p className="text-xs text-gray-400 mt-1 line-clamp-1">{result.description}</p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const inputRef = { current: null as HTMLInputElement | null };
const resultsRef = { current: null as HTMLDivElement | null };