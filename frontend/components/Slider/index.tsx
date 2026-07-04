'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

interface SliderProps {
  sliderKey: string;
  items: React.ReactNode[];
  isLoading?: boolean;
  emptyMessage?: string;
  placeholder?: React.ReactNode;
  placeholderCount?: number;
}

export default function Slider({
  sliderKey,
  items,
  isLoading = false,
  emptyMessage = 'No items to display',
  placeholder,
  placeholderCount = 6,
}: SliderProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollPos, setScrollPos] = useState({ isStart: true, isEnd: false });

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const { scrollWidth, clientWidth, scrollLeft } = container;

    if (!items || items.length === 0) {
      setScrollPos({ isStart: true, isEnd: true });
    } else if (clientWidth >= scrollWidth) {
      setScrollPos({ isStart: true, isEnd: true });
    } else if (scrollLeft >= scrollWidth - clientWidth - 10) {
      setScrollPos({ isStart: false, isEnd: true });
    } else if (scrollLeft > 10) {
      setScrollPos({ isStart: false, isEnd: false });
    } else {
      setScrollPos({ isStart: true, isEnd: false });
    }
  }, [items]);

  useEffect(() => {
    handleScroll();
    window.addEventListener('resize', handleScroll, { passive: true });
    return () => window.removeEventListener('resize', handleScroll);
  }, [handleScroll, items]);

  const slide = (direction: 'left' | 'right') => {
    const container = containerRef.current;
    if (!container) return;

    const cardWidth = container.firstElementChild?.getBoundingClientRect().width ?? 200;
    const visibleItems = Math.floor(container.clientWidth / cardWidth);
    const scrollAmount = cardWidth * Math.max(visibleItems - 1, 1);

    container.scrollBy({
      left: direction === 'left' ? -scrollAmount : scrollAmount,
      behavior: 'smooth',
    });
  };

  const isEmpty = !isLoading && items.length === 0;

  return (
    <div className="relative">
      {/* Navigation arrows */}
      <div className="absolute -top-8 right-0 flex gap-1 text-muted-foreground">
        <button
          type="button"
          onClick={() => slide('left')}
          disabled={scrollPos.isStart}
          className={`rounded p-1 transition-colors ${
            scrollPos.isStart
              ? 'cursor-not-allowed text-faint'
              : 'hover:bg-card hover:text-foreground'
          }`}
        >
          <ChevronLeftIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => slide('right')}
          disabled={scrollPos.isEnd}
          className={`rounded p-1 transition-colors ${
            scrollPos.isEnd
              ? 'cursor-not-allowed text-faint'
              : 'hover:bg-card hover:text-foreground'
          }`}
        >
          <ChevronRightIcon className="h-5 w-5" />
        </button>
      </div>

      {/* Scrollable container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="hide-scrollbar -mx-4 flex gap-4 overflow-x-auto px-4 py-2"
      >
        {items.map((item, index) => (
          <div key={`${sliderKey}-${index}`} className="flex-shrink-0">
            {item}
          </div>
        ))}

        {/* Loading placeholders */}
        {isLoading &&
          [...Array(placeholderCount)].map((_, i) => (
            <div key={`placeholder-${i}`} className="flex-shrink-0">
              {placeholder || <PlaceholderCard />}
            </div>
          ))}

        {/* Empty state */}
        {isEmpty && (
          <div className="flex min-h-[200px] w-full items-center justify-center">
            <p className="text-faint">{emptyMessage}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Default placeholder card
function PlaceholderCard() {
  return (
    <div className="w-36 sm:w-44 md:w-52">
      <div
        className="animate-pulse rounded-xl bg-card"
        style={{ paddingBottom: '133%' }}
      />
    </div>
  );
}

