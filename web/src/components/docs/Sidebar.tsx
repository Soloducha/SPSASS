"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { SidebarGroup } from '@/lib/docs/utils';

interface SidebarProps {
  groups: SidebarGroup[];
}

export function Sidebar({ groups }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="w-72 flex-shrink-0 border-r border-gray-200 bg-white h-full sticky top-0 h-screen overflow-y-auto">
      <nav className="p-4 space-y-6" aria-label="Documentation sidebar">
        {groups.map((group) => (
          <div key={group.slug}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 px-2">
              {group.title}
            </h3>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const href = `/docs/${group.slug}/${item.slug}`;
                const isActive = pathname === href;
                return (
                  <li key={item.slug}>
                    <Link
                      href={href}
                      className={`block px-3 py-2 text-sm rounded-lg transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-700 font-medium'
                          : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                      }`}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      {item.title}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}