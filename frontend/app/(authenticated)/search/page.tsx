'use client';

import { useSearchParams } from 'next/navigation';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';

export default function SearchPage() {
  const searchParams = useSearchParams();
  const query = searchParams.get('q') || '';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-gradient text-3xl font-bold">Search Results</h1>
        {query && (
          <p className="mt-2 text-muted-foreground">
            Showing results for &quot;<span className="text-foreground">{query}</span>&quot;
          </p>
        )}
      </div>

      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/50 p-16 text-center">
        <MagnifyingGlassIcon className="h-16 w-16 text-faint" />
        <h2 className="mt-6 text-xl font-semibold text-muted-foreground">Coming Soon</h2>
        <p className="mt-2 max-w-md text-faint">
          Search will let you find projects, channels, agents, and messages across your entire workspace.
        </p>
      </div>
    </div>
  );
}

