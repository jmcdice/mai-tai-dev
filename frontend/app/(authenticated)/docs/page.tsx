'use client';

import { useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  RocketLaunchIcon,
  CpuChipIcon,
  ChatBubbleLeftRightIcon,
  QuestionMarkCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  HomeIcon,
} from '@heroicons/react/24/outline';
import { mdxContent } from './mdx-content';

// Documentation structure - simplified
const docSections = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: RocketLaunchIcon,
    items: [
      { id: 'what-is-mai-tai', title: 'What is Mai-Tai?' },
      { id: 'quick-start', title: 'Connect Your Agent' },
    ],
  },
  {
    id: 'setting-up-agents',
    title: 'Setting Up Agents',
    icon: CpuChipIcon,
    items: [
      { id: 'mcp-installation', title: 'MCP Installation' },
      { id: 'claude-code', title: 'Claude Code' },
      { id: 'augment', title: 'Augment' },
      { id: 'claude-desktop', title: 'Claude Desktop' },
    ],
  },
  {
    id: 'using-mai-tai',
    title: 'Using Mai-Tai',
    icon: ChatBubbleLeftRightIcon,
    items: [
      { id: 'starting-mode', title: 'Starting Mai-Tai Mode' },
      { id: 'best-practices', title: 'Best Practices' },
    ],
  },
  {
    id: 'troubleshooting',
    title: 'Troubleshooting',
    icon: QuestionMarkCircleIcon,
    items: [
      { id: 'common-issues', title: 'Common Issues' },
      { id: 'faq', title: 'FAQ' },
    ],
  },
];

// Flatten all items for navigation
const allItems = docSections.flatMap((section) =>
	  section.items.map((item) => ({
	    ...item,
	    sectionTitle: section.title,
	    sectionId: section.id,
	  }))
	);

export default function DocsPage() {
	  const router = useRouter();
	  const pathname = usePathname();
	  const searchParams = useSearchParams();

	  const itemParam = searchParams.get('item');
	  const initialItemFromParams =
	    itemParam && allItems.some((item) => item.id === itemParam)
	      ? itemParam
	      : null;

	  const [activeSection, setActiveSection] = useState<string | null>(initialItemFromParams); // null = show TOC

	  const setActiveItem = (itemId: string | null) => {
	    setActiveSection(itemId);
	    if (typeof window === 'undefined') return;
	    const params = new URLSearchParams(window.location.search);
	    if (itemId) {
	      params.set('item', itemId);
	    } else {
	      params.delete('item');
	    }
	    const query = params.toString();
	    const url = query ? `${pathname}?${query}` : pathname;
	    router.push(url, { scroll: true });
	  };

	  // Get current index and nav items
	  const currentIndex = activeSection ? allItems.findIndex((item) => item.id === activeSection) : -1;
	  const prevItem = currentIndex > 0 ? allItems[currentIndex - 1] : null;
	  const nextItem = currentIndex < allItems.length - 1 ? allItems[currentIndex + 1] : null;
	  const currentItem = activeSection ? allItems.find((item) => item.id === activeSection) : null;

	  // Show TOC view
	  if (activeSection === null) {
	    return (
	      <div className="mx-auto max-w-4xl px-4 py-8">
	        <div className="mb-8 text-center">
	          <h1 className="text-3xl font-bold text-white sm:text-4xl">🍹 Mai-Tai Documentation</h1>
	          <p className="mt-2 text-gray-400">Chat with your AI coding agents from anywhere</p>
	          <p className="mt-1 text-sm text-gray-500">
	            Connect Claude Code, Augment, or Claude Desktop and chat in real-time from any device.
	          </p>
	        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          {docSections.map((section) => (
            <div
              key={section.id}
              className="rounded-xl border border-gray-700 bg-gray-800/50 p-6 transition-colors hover:border-gray-600"
            >
              <div className="mb-4 flex items-center gap-3">
                <section.icon className="h-6 w-6 text-indigo-400" />
                <h2 className="text-lg font-semibold text-white">{section.title}</h2>
              </div>
	              <ul className="space-y-2">
	                {section.items.map((item) => (
	                  <li key={item.id}>
	                    <button
	                      onClick={() => setActiveItem(item.id)}
	                      className="w-full rounded-lg px-3 py-2 text-left text-sm text-gray-300 transition-colors hover:bg-gray-700 hover:text-white"
	                    >
	                      {item.title}
	                    </button>
	                  </li>
	                ))}
	              </ul>
            </div>
          ))}
        </div>
      </div>
    );
  }

	  // Show article view
	  return (
	    <div className="mx-auto max-w-5xl px-4 py-8 lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(220px,1fr)] lg:gap-10">
	      <div>
	        {/* Back to TOC */}
	        <button
	          onClick={() => setActiveItem(null)}
	          className="mb-4 flex items-center gap-2 text-sm text-gray-400 transition-colors hover:text-white"
	        >
	          <HomeIcon className="h-4 w-4" />
	          Back to Table of Contents
	        </button>

	        {/* Breadcrumbs */}
	        {currentItem && (
	          <div className="mb-6 text-sm text-gray-400">
	            <button
	              type="button"
	              onClick={() => setActiveItem(null)}
	              className="inline-flex items-center gap-1 text-gray-400 hover:text-white"
	            >
	              <HomeIcon className="h-3 w-3" />
	              <span>{currentItem.sectionTitle}</span>
	            </button>
	            <span className="px-2 text-gray-600">/</span>
	            <span className="text-gray-200">{currentItem.title}</span>
	          </div>
	        )}

	        {/* Article content */}
	        <DocContent sectionId={activeSection} />

	        {/* Navigation buttons */}
	        <div className="mt-12 flex items-center justify-between border-t border-gray-700 pt-6">
	          {prevItem ? (
	            <button
	              onClick={() => setActiveItem(prevItem.id)}
	              className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-800 hover:text-white"
	            >
	              <ChevronLeftIcon className="h-4 w-4" />
	              <div className="text-left">
	                <div className="text-[11px] uppercase tracking-wide text-gray-500">
	                  {prevItem.sectionTitle}
	                </div>
	                <div>{prevItem.title}</div>
	              </div>
	            </button>
	          ) : (
	            <div />
	          )}

	          {nextItem ? (
	            <button
	              onClick={() => setActiveItem(nextItem.id)}
	              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
	            >
	              <div className="text-right">
	                <div className="text-[11px] uppercase tracking-wide text-indigo-200">
	                  {nextItem.sectionTitle}
	                </div>
	                <div>{nextItem.title}</div>
	              </div>
	              <ChevronRightIcon className="h-4 w-4" />
	            </button>
	          ) : (
	            <button
	              onClick={() => setActiveItem(null)}
	              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
	            >
	              <div className="text-right">
	                <div className="text-[11px] uppercase tracking-wide text-indigo-200">Finished</div>
	                <div>Back to TOC</div>
	              </div>
	              <HomeIcon className="h-4 w-4" />
	            </button>
	          )}
	        </div>
	      </div>

	      {/* Mini TOC - desktop only */}
	      <aside className="mt-8 hidden text-sm text-gray-400 lg:block">
	        <div className="sticky top-24 space-y-4 border-l border-gray-800 pl-6">
	          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
	            On this page
	          </div>
	          <ul className="space-y-3">
	            {docSections.map((section) => (
	              <li key={section.id}>
	                <div className="mb-1 text-xs font-semibold text-gray-500">{section.title}</div>
	                <ul className="space-y-0.5">
	                  {section.items.map((item) => {
	                    const isActive = item.id === activeSection;
	                    return (
	                      <li key={item.id}>
	                        <button
	                          type="button"
	                          onClick={() => setActiveItem(item.id)}
	                          className={`w-full truncate rounded-md px-2 py-1 text-left text-xs ${
	                            isActive
	                              ? 'bg-gray-800 text-white'
	                              : 'text-gray-400 hover:bg-gray-800 hover:text-white'
	                          }`}
	                        >
	                          {item.title}
	                        </button>
	                      </li>
	                    );
	                  })}
	                </ul>
	              </li>
	            ))}
	          </ul>
	        </div>
	      </aside>
	    </div>
	  );
}

// Content component
function DocContent({ sectionId }: { sectionId: string }) {
  const MDXComponent = mdxContent[sectionId];

  if (!MDXComponent) {
    return (
      <article className="prose prose-invert max-w-3xl prose-headings:text-white prose-p:text-gray-300 prose-li:text-gray-300 prose-strong:text-white prose-code:text-indigo-300 prose-pre:bg-gray-800 prose-a:text-indigo-400">
        <DefaultContent sectionId={sectionId} />
      </article>
    );
  }

  return (
    <article className="prose prose-invert max-w-3xl prose-headings:text-white prose-p:text-gray-300 prose-li:text-gray-300 prose-strong:text-white prose-code:text-indigo-300 prose-pre:bg-gray-800 prose-a:text-indigo-400">
      <MDXComponent />
    </article>
  );
}

function DefaultContent({ sectionId }: { sectionId: string }) {
  return (
    <>
      <h1>Documentation</h1>
      <p>Content for &quot;{sectionId}&quot; is coming soon.</p>
    </>
  );
}

