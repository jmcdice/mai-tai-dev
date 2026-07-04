'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from './Sidebar';
import MobileMenu from './MobileMenu';
import UserMenu from './UserMenu';
import SearchInput from './SearchInput';
import { ThemeToggle } from '@/components/theme-toggle';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const pathname = usePathname();

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  // Detect scroll for top bar blur effect
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main content area */}
      <div className="flex flex-1 flex-col lg:pl-64">
        {/* Top bar - hidden on mobile, visible on desktop */}
        <header
          className={`sticky top-0 z-30 hidden h-16 items-center gap-4 px-4 transition-colors duration-200 lg:flex lg:px-6 ${
            isScrolled
              ? 'glass-effect border-b border-border'
              : 'bg-transparent'
          }`}
        >
          {/* Mobile menu button - hidden, using bottom nav instead */}
          {/* Keeping sidebar state for potential future use */}

          {/* Search bar */}
          <div className="max-w-2xl flex-1">
            <SearchInput />
          </div>

          {/* Spacer to push controls to right */}
          <div className="flex-1" />

          {/* Right side - theme switcher + user menu */}
          <div className="flex flex-shrink-0 items-center gap-1">
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 px-4 py-6 pb-24 lg:px-8 lg:pb-6">
          {children}
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <MobileMenu />
    </div>
  );
}

