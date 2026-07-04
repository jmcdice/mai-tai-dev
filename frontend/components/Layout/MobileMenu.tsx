'use client';

import { Fragment, useState, useCallback } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Transition } from '@headlessui/react';
import {
  HomeIcon,
  ChatBubbleLeftRightIcon,
  EllipsisHorizontalIcon,
  XMarkIcon,
  Cog6ToothIcon,
  BookOpenIcon,
  BookmarkIcon,
  ChatBubbleLeftEllipsisIcon,
  ShieldCheckIcon,
  ArrowRightOnRectangleIcon,
  BoltIcon,
  SunIcon,
  MoonIcon,
  ComputerDesktopIcon,
} from '@heroicons/react/24/outline';
import {
  HomeIcon as HomeIconSolid,
  ChatBubbleLeftRightIcon as ChatBubbleLeftRightIconSolid,
  BoltIcon as BoltIconSolid,
} from '@heroicons/react/24/solid';
import { useAuth } from '@/lib/auth';
import { getWorkspaces, Workspace } from '@/lib/api';
import { FeedbackModal } from '@/components/FeedbackModal';
import { useChatShortcuts } from '@/lib/chat-shortcuts';
import { useTheme } from '@/lib/theme';

export default function MobileMenu() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, token, logout } = useAuth();
  const isAdmin = user?.is_admin ?? false;
  const { shortcuts, selectShortcut, isInChatContext } = useChatShortcuts();
  const { theme, setTheme, palette, setPalette, palettes } = useTheme();

  const modeOptions = [
    { value: 'light' as const, label: 'Light', icon: SunIcon },
    { value: 'dark' as const, label: 'Dark', icon: MoonIcon },
    { value: 'system' as const, label: 'Auto', icon: ComputerDesktopIcon },
  ];

  const [isMoreOpen, setIsMoreOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [showWorkspaces, setShowWorkspaces] = useState(false);
  const [isLoadingWorkspaces, setIsLoadingWorkspaces] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);

  // Fetch workspaces for the switcher
  const fetchWorkspaces = useCallback(async () => {
    if (!token) return;
    setIsLoadingWorkspaces(true);
    try {
      const response = await getWorkspaces(token, { archived: false });
      const sorted = response.workspaces
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 8);
      setWorkspaces(sorted);
    } catch (error) {
      console.error('Failed to fetch workspaces:', error);
    } finally {
      setIsLoadingWorkspaces(false);
    }
  }, [token]);

  const handleNavigation = useCallback((href: string) => {
    router.push(href);
    setIsMoreOpen(false);
    setShowWorkspaces(false);
    setShowShortcuts(false);
  }, [router]);

  const handleWorkspacesClick = useCallback(() => {
    if (!showWorkspaces) {
      fetchWorkspaces();
    }
    setShowWorkspaces(!showWorkspaces);
    setIsMoreOpen(false);
    setShowShortcuts(false);
  }, [showWorkspaces, fetchWorkspaces]);

  const handleShortcutsClick = useCallback(() => {
    if (!isInChatContext) return;
    setShowShortcuts(!showShortcuts);
    setIsMoreOpen(false);
    setShowWorkspaces(false);
  }, [isInChatContext, showShortcuts]);

  const handleMoreClick = useCallback(() => {
    setIsMoreOpen(!isMoreOpen);
    setShowWorkspaces(false);
    setShowShortcuts(false);
  }, [isMoreOpen]);

  const isHomeActive = /^\/dashboard$/.test(pathname);
  const isAnyMenuOpen = showWorkspaces || isMoreOpen || showShortcuts;

  const closeAllMenus = useCallback(() => {
    setShowWorkspaces(false);
    setIsMoreOpen(false);
    setShowShortcuts(false);
  }, []);

  return (
    <>
      {/* Transparent backdrop — clicking above the menu closes it */}
      {isAnyMenuOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={closeAllMenus}
        />
      )}
      <div className="fixed bottom-0 left-0 right-0 z-50 lg:hidden">
      {/* Workspaces Popup */}
      <Transition
        show={showWorkspaces}
        as={Fragment}
        enter="transition ease-out duration-200"
        enterFrom="opacity-0 translate-y-full"
        enterTo="opacity-100 translate-y-0"
        leave="transition ease-in duration-150"
        leaveFrom="opacity-100 translate-y-0"
        leaveTo="opacity-0 translate-y-full"
      >
        <div className="absolute bottom-full left-0 right-0 border-t border-border-strong bg-background/95 backdrop-blur">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-sm font-medium text-foreground">Recent Workspaces</h3>
          </div>
          <div className="py-2 max-h-64 overflow-y-auto">
            {isLoadingWorkspaces ? (
              <div className="px-4 py-4 text-center text-sm text-muted-foreground">Loading...</div>
            ) : workspaces.length === 0 ? (
              <div className="px-4 py-4 text-center text-sm text-muted-foreground">No workspaces yet</div>
            ) : (
              workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => handleNavigation(`/workspaces/${ws.id}`)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-sm text-muted-foreground hover:bg-surface2/50 hover:text-foreground transition-colors"
                >
                  <ChatBubbleLeftRightIcon className="h-5 w-5 text-faint flex-shrink-0" />
                  <span className="truncate">{ws.name}</span>
                </button>
              ))
            )}
          </div>
          <div className="px-4 py-2 border-t border-border">
            <button
              onClick={() => handleNavigation('/workspaces')}
              className="w-full text-center text-xs text-primary hover:text-primary/80 py-1"
            >
              View all workspaces
            </button>
          </div>
        </div>
      </Transition>

      {/* More Menu Popup */}
      <Transition
        show={isMoreOpen}
        as={Fragment}
        enter="transition ease-out duration-200"
        enterFrom="opacity-0 translate-y-full"
        enterTo="opacity-100 translate-y-0"
        leave="transition ease-in duration-150"
        leaveFrom="opacity-100 translate-y-0"
        leaveTo="opacity-0 translate-y-full"
      >
        <div className="absolute bottom-full left-0 right-0 border-t border-border-strong bg-background/95 backdrop-blur px-6 py-4 space-y-4">
          {/* Dashboard */}
          <button
            onClick={() => handleNavigation('/dashboard')}
            className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
          >
            <HomeIcon className="h-5 w-5" />
            <span className="font-medium">Dashboard</span>
          </button>

          {/* Workspaces */}
          <button
            onClick={() => handleNavigation('/workspaces')}
            className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
          >
            <ChatBubbleLeftRightIcon className="h-5 w-5" />
            <span className="font-medium">Workspaces</span>
          </button>

          {/* Stash */}
          <button
            onClick={() => handleNavigation('/stash')}
            className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
          >
            <BookmarkIcon className="h-5 w-5" />
            <span className="font-medium">Stash</span>
          </button>

          {/* Settings */}
          <button
            onClick={() => handleNavigation('/settings')}
            className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
          >
            <Cog6ToothIcon className="h-5 w-5" />
            <span className="font-medium">Settings</span>
          </button>

          {/* Help & Docs */}
          <button
            onClick={() => handleNavigation('/docs')}
            className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
          >
            <BookOpenIcon className="h-5 w-5" />
            <span className="font-medium">Help & Docs</span>
          </button>

          {/* Feedback */}
          <FeedbackModal
            trigger={
              <button className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors">
                <ChatBubbleLeftEllipsisIcon className="h-5 w-5" />
                <span className="font-medium">Feedback</span>
              </button>
            }
          />

          {/* Admin (if admin) */}
          {isAdmin && (
            <button
              onClick={() => handleNavigation('/admin')}
              className="flex w-full items-center gap-3 text-foreground hover:text-foreground transition-colors"
            >
              <ShieldCheckIcon className="h-5 w-5" />
              <span className="font-medium">Admin</span>
            </button>
          )}

          {/* Theme */}
          <div className="space-y-2 border-t border-border pt-4">
            <div className="grid grid-cols-3 gap-2">
              {modeOptions.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  onClick={() => setTheme(value)}
                  className={`flex flex-col items-center gap-1 rounded-lg border py-2 text-xs font-medium transition-colors ${
                    theme === value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border-strong text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              {palettes.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setPalette(p.id)}
                  aria-label={p.label}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-lg border py-2 text-xs font-medium transition-colors ${
                    palette === p.id
                      ? 'border-primary text-foreground'
                      : 'border-border-strong text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <span
                    className="h-3.5 w-3.5 rounded-full border border-border-strong"
                    style={{ backgroundColor: p.dot }}
                  />
                  <span className="truncate">{p.label.split(' ')[0]}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Sign out */}
          <button
            onClick={() => {
              logout();
              setIsMoreOpen(false);
            }}
            className="flex w-full items-center gap-3 border-t border-border pt-4 text-foreground hover:text-foreground transition-colors"
          >
            <ArrowRightOnRectangleIcon className="h-5 w-5" />
            <span className="font-medium">Sign out</span>
          </button>
        </div>
      </Transition>

      {/* Shortcuts Popup */}
      <Transition
        show={showShortcuts}
        as={Fragment}
        enter="transition ease-out duration-200"
        enterFrom="opacity-0 translate-y-full"
        enterTo="opacity-100 translate-y-0"
        leave="transition ease-in duration-150"
        leaveFrom="opacity-100 translate-y-0"
        leaveTo="opacity-0 translate-y-full"
      >
        <div className="absolute bottom-full left-0 right-0 border-t border-border-strong bg-background/95 backdrop-blur">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-sm font-medium text-foreground">Quick Shortcuts</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Tap to add to chat</p>
          </div>
          <div className="py-2 max-h-64 overflow-y-auto">
            {shortcuts.map((shortcut) => {
              const maxLength = 40;
              const displayLabel = shortcut.label.length > maxLength
                ? shortcut.label.slice(0, maxLength) + '…'
                : shortcut.label;
              return (
                <button
                  key={shortcut.id}
                  onClick={() => {
                    selectShortcut(shortcut.text);
                    setShowShortcuts(false);
                  }}
                  className="flex w-full items-center px-4 py-3 text-sm text-muted-foreground hover:bg-surface2/50 hover:text-foreground transition-colors"
                  title={shortcut.label}
                >
                  <span className="font-medium">{displayLabel}</span>
                </button>
              );
            })}
          </div>
        </div>
      </Transition>

      {/* Bottom Navigation Bar */}
      <nav className="glass-effect border-t border-border safe-area-bottom">
        <div className="flex items-center justify-around">
          {/* Home */}
          <button
            type="button"
            onClick={() => handleNavigation('/dashboard')}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              isHomeActive ? 'text-primary' : 'text-muted-foreground active:text-foreground'
            }`}
          >
            {isHomeActive ? <HomeIconSolid className="h-6 w-6" /> : <HomeIcon className="h-6 w-6" />}
            <span className="mt-1">Home</span>
          </button>

          {/* Workspaces (switcher) */}
          <button
            type="button"
            onClick={handleWorkspacesClick}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              showWorkspaces ? 'text-primary' : 'text-muted-foreground active:text-foreground'
            }`}
          >
            {showWorkspaces ? (
              <XMarkIcon className="h-6 w-6" />
            ) : (
              <ChatBubbleLeftRightIcon className="h-6 w-6" />
            )}
            <span className="mt-1">{showWorkspaces ? 'Close' : 'Workspaces'}</span>
          </button>

          {/* Stash */}
          <button
            type="button"
            onClick={() => handleNavigation('/stash')}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              /^\/stash/.test(pathname) ? 'text-primary' : 'text-muted-foreground active:text-foreground'
            }`}
          >
            <BookmarkIcon className="h-6 w-6" />
            <span className="mt-1">Stash</span>
          </button>

          {/* Quick Shortcuts - only active in chat context */}
          <button
            type="button"
            onClick={handleShortcutsClick}
            disabled={!isInChatContext}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              !isInChatContext
                ? 'text-faint cursor-not-allowed'
                : showShortcuts
                ? 'text-primary'
                : 'text-muted-foreground active:text-foreground'
            }`}
          >
            {showShortcuts ? <XMarkIcon className="h-6 w-6" /> : <BoltIcon className="h-6 w-6" />}
            <span className="mt-1">{showShortcuts ? 'Close' : 'Quick'}</span>
          </button>

          {/* More */}
          <button
            type="button"
            onClick={handleMoreClick}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              isMoreOpen ? 'text-primary' : 'text-muted-foreground active:text-foreground'
            }`}
          >
            {isMoreOpen ? <XMarkIcon className="h-6 w-6" /> : <EllipsisHorizontalIcon className="h-6 w-6" />}
            <span className="mt-1">{isMoreOpen ? 'Close' : 'More'}</span>
          </button>
        </div>
      </nav>
    </div>
    </>
  );
}

