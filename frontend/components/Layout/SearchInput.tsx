'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { MagnifyingGlassIcon } from '@heroicons/react/24/solid';
import { XCircleIcon } from '@heroicons/react/24/outline';

export default function SearchInput() {
  const [searchValue, setSearchValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const router = useRouter();

  const handleClear = useCallback(() => {
    setSearchValue('');
  }, []);

  const handleSearch = useCallback(() => {
    if (searchValue.trim()) {
      // Navigate to search results page (to be implemented)
      router.push(`/search?q=${encodeURIComponent(searchValue.trim())}`);
    }
  }, [searchValue, router]);

  const handleKeyUp = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSearch();
        (e.target as HTMLInputElement).blur();
      }
    },
    [handleSearch]
  );

  return (
    <div className="flex flex-1">
      <div className="flex w-full">
        <label htmlFor="search_field" className="sr-only">
          Search
        </label>
        <div className="relative flex w-full items-center text-foreground focus-within:text-foreground">
          <div className="pointer-events-none absolute inset-y-0 left-4 flex items-center">
            <MagnifyingGlassIcon className="h-5 w-5 text-muted-foreground" />
          </div>
          <input
            id="search_field"
            type="search"
            autoComplete="off"
            placeholder="Search projects, agents, channels..."
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onKeyUp={handleKeyUp}
            className={`block w-full rounded-full border bg-background/80 py-2 pl-10 text-foreground placeholder-faint transition-colors focus:bg-background focus:placeholder-muted-foreground focus:outline-none focus:ring-0 sm:text-base ${
              isFocused
                ? 'border-border-strong'
                : 'border-border hover:border-border-strong'
            }`}
            style={{ paddingRight: searchValue.length > 0 ? '2.5rem' : '1rem' }}
          />
          {searchValue.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="absolute inset-y-0 right-2 m-auto flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition hover:text-foreground focus:outline-none"
            >
              <XCircleIcon className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

