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

export default function MobileMenu() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, token, logout } = useAuth();
  const isAdmin = user?.is_admin ?? false;
  const { shortcuts, selectShortcut, isInChatContext } = useChatShortcuts();

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
        .slice(0, 5);
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

  return (
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
        <div className="absolute bottom-full left-0 right-0 border-t border-gray-600 bg-gray-900 bg-opacity-95 backdrop-blur">
          <div className="px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-medium text-gray-200">Recent Workspaces</h3>
          </div>
          <div className="py-2 max-h-64 overflow-y-auto">
            {isLoadingWorkspaces ? (
              <div className="px-4 py-4 text-center text-sm text-gray-400">Loading...</div>
            ) : workspaces.length === 0 ? (
              <div className="px-4 py-4 text-center text-sm text-gray-400">No workspaces yet</div>
            ) : (
              workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => handleNavigation(`/workspaces/${ws.id}`)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:bg-gray-700/50 hover:text-white transition-colors"
                >
                  <ChatBubbleLeftRightIcon className="h-5 w-5 text-gray-500 flex-shrink-0" />
                  <span className="truncate">{ws.name}</span>
                </button>
              ))
            )}
          </div>
          <div className="px-4 py-2 border-t border-gray-700">
            <button
              onClick={() => handleNavigation('/workspaces')}
              className="w-full text-center text-xs text-indigo-400 hover:text-indigo-300 py-1"
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
        <div className="absolute bottom-full left-0 right-0 border-t border-gray-600 bg-gray-900 bg-opacity-95 backdrop-blur px-6 py-4 space-y-4">
          {/* Dashboard */}
          <button
            onClick={() => handleNavigation('/dashboard')}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
          >
            <HomeIcon className="h-5 w-5" />
            <span className="font-medium">Dashboard</span>
          </button>

          {/* Workspaces */}
          <button
            onClick={() => handleNavigation('/workspaces')}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
          >
            <ChatBubbleLeftRightIcon className="h-5 w-5" />
            <span className="font-medium">Workspaces</span>
          </button>

          {/* Stash */}
          <button
            onClick={() => handleNavigation('/stash')}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
          >
            <BookmarkIcon className="h-5 w-5" />
            <span className="font-medium">Stash</span>
          </button>

          {/* Settings */}
          <button
            onClick={() => handleNavigation('/settings')}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
          >
            <Cog6ToothIcon className="h-5 w-5" />
            <span className="font-medium">Settings</span>
          </button>

          {/* Help & Docs */}
          <button
            onClick={() => handleNavigation('/docs')}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
          >
            <BookOpenIcon className="h-5 w-5" />
            <span className="font-medium">Help & Docs</span>
          </button>

          {/* Feedback */}
          <FeedbackModal
            trigger={
              <button className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors">
                <ChatBubbleLeftEllipsisIcon className="h-5 w-5" />
                <span className="font-medium">Feedback</span>
              </button>
            }
          />

          {/* Admin (if admin) */}
          {isAdmin && (
            <button
              onClick={() => handleNavigation('/admin')}
              className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
            >
              <ShieldCheckIcon className="h-5 w-5" />
              <span className="font-medium">Admin</span>
            </button>
          )}

          {/* Sign out */}
          <button
            onClick={() => {
              logout();
              setIsMoreOpen(false);
            }}
            className="flex w-full items-center gap-3 text-gray-200 hover:text-white transition-colors"
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
        <div className="absolute bottom-full left-0 right-0 border-t border-gray-600 bg-gray-900 bg-opacity-95 backdrop-blur">
          <div className="px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-medium text-gray-200">Quick Shortcuts</h3>
            <p className="text-xs text-gray-400 mt-0.5">Tap to add to chat</p>
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
                  className="flex w-full items-center px-4 py-3 text-sm text-gray-300 hover:bg-gray-700/50 hover:text-white transition-colors"
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
      <nav className="glass-effect border-t border-gray-700 safe-area-bottom">
        <div className="flex items-center justify-around">
          {/* Home */}
          <button
            type="button"
            onClick={() => handleNavigation('/dashboard')}
            className={`flex flex-1 flex-col items-center py-3 text-xs font-medium transition-colors touch-manipulation ${
              isHomeActive ? 'text-indigo-400' : 'text-gray-400 active:text-gray-200'
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
              showWorkspaces ? 'text-indigo-400' : 'text-gray-400 active:text-gray-200'
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
              /^\/stash/.test(pathname) ? 'text-indigo-400' : 'text-gray-400 active:text-gray-200'
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
                ? 'text-gray-600 cursor-not-allowed'
                : showShortcuts
                ? 'text-indigo-400'
                : 'text-gray-400 active:text-gray-200'
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
              isMoreOpen ? 'text-indigo-400' : 'text-gray-400 active:text-gray-200'
            }`}
          >
            {isMoreOpen ? <XMarkIcon className="h-6 w-6" /> : <EllipsisHorizontalIcon className="h-6 w-6" />}
            <span className="mt-1">{isMoreOpen ? 'Close' : 'More'}</span>
          </button>
        </div>
      </nav>
    </div>
  );
}

