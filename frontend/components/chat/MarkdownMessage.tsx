'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface MarkdownMessageProps {
  content: string;
  /** Max characters before showing "Show more" (0 = no limit) */
  maxLength?: number;
}

/**
 * Parse @mentions and #channels in text and wrap them in styled spans.
 * Only applies to plain text, not inside code or links.
 */
function parseInlineEntities(text: string): React.ReactNode[] {
  // Match @username or #channel patterns (alphanumeric, underscores, hyphens)
  const pattern = /(@[\w-]+|#[\w-]+)/g;
  const parts = text.split(pattern);

  return parts.map((part, index) => {
    if (part.startsWith('@')) {
      return (
        <span
          key={index}
          className="inline-flex items-center rounded-md bg-primary/20 px-1.5 py-0.5 text-sm font-medium text-primary ring-1 ring-inset ring-ring/30"
        >
          {part}
        </span>
      );
    }
    if (part.startsWith('#')) {
      return (
        <span
          key={index}
          className="inline-flex items-center rounded-md bg-secondary/20 px-1.5 py-0.5 text-sm font-medium text-secondary ring-1 ring-inset ring-secondary/30"
        >
          {part}
        </span>
      );
    }
    return part;
  });
}

/**
 * Custom text renderer that parses @mentions and #channels
 */
function TextWithEntities({ children }: { children: React.ReactNode }) {
  if (typeof children === 'string') {
    return <>{parseInlineEntities(children)}</>;
  }
  return <>{children}</>;
}

export default function MarkdownMessage({
  content,
  maxLength = 3000,
}: MarkdownMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Determine if content should be collapsed
  const shouldCollapse = maxLength > 0 && content.length > maxLength;
  const displayContent = shouldCollapse && !isExpanded
    ? content.slice(0, maxLength) + '...'
    : content;

  // Custom components for ReactMarkdown
  const components = useMemo(() => ({
    // Paragraphs with entity parsing
    p: ({ children }: { children?: React.ReactNode }) => (
      <p className="my-2 leading-relaxed">
        <TextWithEntities>{children}</TextWithEntities>
      </p>
    ),

    // Headings
    h1: ({ children }: { children?: React.ReactNode }) => (
      <h1 className="mb-3 mt-4 text-xl font-bold text-foreground">{children}</h1>
    ),
    h2: ({ children }: { children?: React.ReactNode }) => (
      <h2 className="mb-2 mt-3 text-lg font-bold text-foreground">{children}</h2>
    ),
    h3: ({ children }: { children?: React.ReactNode }) => (
      <h3 className="mb-2 mt-3 text-base font-bold text-foreground">{children}</h3>
    ),
    h4: ({ children }: { children?: React.ReactNode }) => (
      <h4 className="mb-1 mt-2 text-sm font-bold text-foreground">{children}</h4>
    ),

    // Lists
    ul: ({ children }: { children?: React.ReactNode }) => (
      <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
    ),
    ol: ({ children }: { children?: React.ReactNode }) => (
      <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
      <li className="leading-relaxed">
        <TextWithEntities>{children}</TextWithEntities>
      </li>
    ),

    // Links
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline decoration-primary/50 underline-offset-2 hover:decoration-primary"
      >
        {children}
      </a>
    ),

    // Blockquotes
    blockquote: ({ children }: { children?: React.ReactNode }) => (
      <blockquote className="my-3 border-l-4 border-border-strong pl-4 italic text-muted-foreground">
        {children}
      </blockquote>
    ),

    // Horizontal rule
    hr: () => <hr className="my-4 border-border" />,

    // Code blocks and inline code
    code: ({ className, children, ...props }: { className?: string; children?: React.ReactNode }) => {
      const match = /language-(\w+)/.exec(className || '');
      const codeString = String(children).replace(/\n$/, '');
      const hasNewlines = codeString.includes('\n');

      // Fenced code block with language
      if (match) {
        return (
          <SyntaxHighlighter
            style={oneDark}
            language={match[1]}
            PreTag="div"
            customStyle={{
              margin: '0.75rem 0',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
              overflowX: 'auto',
            }}
            wrapLongLines={false}
          >
            {codeString}
          </SyntaxHighlighter>
        );
      }

      // Multi-line code block without language specifier
      if (hasNewlines) {
        return (
          <SyntaxHighlighter
            style={oneDark}
            language="text"
            PreTag="div"
            customStyle={{
              margin: '0.75rem 0',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
              overflowX: 'auto',
            }}
            wrapLongLines={false}
          >
            {codeString}
          </SyntaxHighlighter>
        );
      }

      // Inline code - pill style (single line only)
      return (
        <code
          className="rounded-md bg-surface2 px-1.5 py-0.5 text-sm text-secondary"
          {...props}
        >
          {children}
        </code>
      );
    },

    // Pre tag (wrapper for code blocks)
    pre: ({ children }: { children?: React.ReactNode }) => (
      <div className="my-3 overflow-x-auto">{children}</div>
    ),

    // Tables
    table: ({ children }: { children?: React.ReactNode }) => (
      <div className="my-3 overflow-x-auto">
        <table className="min-w-full divide-y divide-border">{children}</table>
      </div>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => (
      <thead className="bg-card">{children}</thead>
    ),
    tbody: ({ children }: { children?: React.ReactNode }) => (
      <tbody className="divide-y divide-border">{children}</tbody>
    ),
    tr: ({ children }: { children?: React.ReactNode }) => <tr>{children}</tr>,
    th: ({ children }: { children?: React.ReactNode }) => (
      <th className="px-3 py-2 text-left text-sm font-semibold text-foreground">
        {children}
      </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
      <td className="px-3 py-2 text-sm text-muted-foreground">{children}</td>
    ),

    // Strong/bold
    strong: ({ children }: { children?: React.ReactNode }) => (
      <strong className="font-semibold text-foreground">{children}</strong>
    ),

    // Emphasis/italic
    em: ({ children }: { children?: React.ReactNode }) => (
      <em className="italic">{children}</em>
    ),
  }), []);

  return (
    <div className="text-[15px] leading-relaxed text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {displayContent}
      </ReactMarkdown>

      {shouldCollapse && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="mt-2 text-sm font-medium text-primary hover:text-primary/80"
        >
          {isExpanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

