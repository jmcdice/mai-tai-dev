'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  HomeIcon,
  ChatBubbleLeftRightIcon,
  Cog6ToothIcon,
  ShieldCheckIcon,
  BookOpenIcon,
  BookmarkIcon,
  XMarkIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ArrowRightOnRectangleIcon,
  ChatBubbleLeftEllipsisIcon,
} from '@heroicons/react/24/outline';
import {
  HomeIcon as HomeIconSolid,
  ChatBubbleLeftRightIcon as ChatBubbleLeftRightIconSolid,
  Cog6ToothIcon as Cog6ToothIconSolid,
  ShieldCheckIcon as ShieldCheckIconSolid,
  BookOpenIcon as BookOpenIconSolid,
  BookmarkIcon as BookmarkIconSolid,
} from '@heroicons/react/24/solid';
import { useAuth } from '@/lib/auth';
import { getWorkspaces, Workspace } from '@/lib/api';
import { events, WORKSPACE_UPDATED } from '@/lib/events';
import { FeedbackModal } from '@/components/FeedbackModal';

interface SidebarLink {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  activeIcon: React.ComponentType<{ className?: string }>;
  activePattern: RegExp;
  adminOnly?: boolean;
  hasChildren?: boolean;
}

const navLinks: SidebarLink[] = [
  {
    href: '/dashboard',
    label: 'Dashboard',
    icon: HomeIcon,
    activeIcon: HomeIconSolid,
    activePattern: /^\/dashboard$/,
  },
  {
    href: '/workspaces',
    label: 'Workspaces',
    icon: ChatBubbleLeftRightIcon,
    activeIcon: ChatBubbleLeftRightIconSolid,
    activePattern: /^\/workspaces/,
    hasChildren: true,
  },
  {
    href: '/stash',
    label: 'Stash',
    icon: BookmarkIcon,
    activeIcon: BookmarkIconSolid,
    activePattern: /^\/stash/,
  },
  {
    href: '/settings',
    label: 'Settings',
    icon: Cog6ToothIcon,
    activeIcon: Cog6ToothIconSolid,
    activePattern: /^\/settings/,
  },
  {
    href: '/docs',
    label: 'Help & Docs',
    icon: BookOpenIcon,
    activeIcon: BookOpenIconSolid,
    activePattern: /^\/docs/,
  },
  {
    href: '/admin',
    label: 'Admin',
    icon: ShieldCheckIcon,
    activeIcon: ShieldCheckIconSolid,
    activePattern: /^\/admin/,
    adminOnly: true,
  },
];

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user, token, logout } = useAuth();
  const isAdmin = user?.is_admin ?? false;
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspacesExpanded, setWorkspacesExpanded] = useState(true);

  // Fetch workspaces function
  const fetchWorkspaces = useCallback(() => {
    if (token) {
      getWorkspaces(token, { archived: false })
        .then((res) => setWorkspaces(res.workspaces))
        .catch(() => setWorkspaces([]));
    }
  }, [token]);

  // Fetch workspaces - refetch when pathname changes (e.g., after creating a new workspace)
  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces, pathname]);

  // Listen for workspace updates (e.g., rename)
  useEffect(() => {
    const unsubscribe = events.on(WORKSPACE_UPDATED, fetchWorkspaces);
    return unsubscribe;
  }, [fetchWorkspaces]);

  // Filter links based on admin status
  const visibleLinks = navLinks.filter((link) => !link.adminOnly || isAdmin);

  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-16 flex-shrink-0 items-center px-4">
        <Link href="/dashboard" className="flex items-center space-x-3">
          <img
            src="/logo.png"
            alt="Mai-Tai"
            className="h-10 w-10 rounded-full object-cover"
          />
          <span className="text-gradient text-xl font-bold">Mai-Tai</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="mt-4 flex-1 space-y-1 px-2">
        {visibleLinks.map((link) => {
          const isActive = link.activePattern.test(pathname);
          const Icon = isActive ? link.activeIcon : link.icon;

          // Special handling for Workspaces with children
          if (link.hasChildren && link.label === 'Workspaces') {
            return (
              <div key={link.href}>
                <button
                  onClick={() => setWorkspacesExpanded(!workspacesExpanded)}
                  className={`group flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-base font-medium leading-6 transition duration-150 ease-in-out lg:text-lg ${
                    isActive
                      ? 'nav-active text-white'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                  }`}
                >
                  <span className="flex items-center">
                    <Icon className="mr-3 h-5 w-5 flex-shrink-0 lg:h-6 lg:w-6" />
                    {link.label}
                  </span>
                  {workspacesExpanded ? (
                    <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                  ) : (
                    <ChevronRightIcon className="h-4 w-4 text-gray-400" />
                  )}
                </button>
                {workspacesExpanded && (
                  <div className="ml-6 mt-1 space-y-0.5 border-l border-gray-700 pl-3">
                    {workspaces.map((ws) => {
                      const wsActive = pathname === `/workspaces/${ws.id}`;
                      return (
                        <Link
                          key={ws.id}
                          href={`/workspaces/${ws.id}`}
                          onClick={onClose}
                          className={`block px-3 py-1.5 text-sm transition ${
                            wsActive
                              ? 'text-indigo-400'
                              : 'text-gray-400 hover:text-white'
                          }`}
                        >
                          {ws.name}
                        </Link>
                      );
                    })}
                    {workspaces.length === 0 && (
                      <span className="block px-3 py-1.5 text-sm text-gray-500">
                        No workspaces yet
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          }

          return (
            <Link
              key={link.href}
              href={link.href}
              onClick={onClose}
              className={`group flex items-center rounded-lg px-3 py-2.5 text-base font-medium leading-6 transition duration-150 ease-in-out lg:text-lg ${
                isActive
                  ? 'nav-active text-white'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              <Icon className="mr-3 h-5 w-5 flex-shrink-0 lg:h-6 lg:w-6" />
              {link.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-40 lg:flex lg:w-64 lg:flex-col">
        <div className="sidebar-gradient flex flex-1 flex-col border-r border-gray-700">
          {sidebarContent}
          {/* Desktop-only feedback + logout buttons */}
          <div className="flex-shrink-0 border-t border-gray-700 px-2 py-3">
            <FeedbackModal
              trigger={
                <button className="group flex w-full items-center rounded-lg px-3 py-2.5 text-base font-medium leading-6 text-gray-300 transition duration-150 ease-in-out hover:bg-gray-700 hover:text-white lg:text-lg">
                  <ChatBubbleLeftEllipsisIcon className="mr-3 h-5 w-5 flex-shrink-0 lg:h-6 lg:w-6" />
                  Feedback
                </button>
              }
            />
            <button
              onClick={logout}
              className="group flex w-full items-center rounded-lg px-3 py-2.5 text-base font-medium leading-6 text-gray-300 transition duration-150 ease-in-out hover:bg-gray-700 hover:text-white lg:text-lg"
            >
              <ArrowRightOnRectangleIcon className="mr-3 h-5 w-5 flex-shrink-0 lg:h-6 lg:w-6" />
              Sign out
            </button>
          </div>
        </div>
      </div>

      {/* Mobile sidebar (slide-over) */}
      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-gray-900 bg-opacity-80 lg:hidden"
            onClick={onClose}
          />

          {/* Sidebar panel */}
          <div className="fixed inset-y-0 left-0 z-50 w-64 lg:hidden">
            <div className="sidebar-gradient flex h-full flex-col border-r border-gray-700">
              {/* Close button */}
              <div className="absolute right-0 top-0 -mr-12 pt-2">
                <button
                  type="button"
                  className="ml-1 flex h-10 w-10 items-center justify-center rounded-full focus:outline-none focus:ring-2 focus:ring-inset focus:ring-white"
                  onClick={onClose}
                >
                  <XMarkIcon className="h-6 w-6 text-white" />
                </button>
              </div>
              {sidebarContent}
              {/* Mobile feedback + logout buttons */}
              <div className="flex-shrink-0 border-t border-gray-700 px-2 py-3">
                <FeedbackModal
                  trigger={
                    <button className="group flex w-full items-center rounded-lg px-3 py-2.5 text-base font-medium leading-6 text-gray-300 transition duration-150 ease-in-out hover:bg-gray-700 hover:text-white">
                      <ChatBubbleLeftEllipsisIcon className="mr-3 h-5 w-5 flex-shrink-0" />
                      Feedback
                    </button>
                  }
                />
                <button
                  onClick={logout}
                  className="group flex w-full items-center rounded-lg px-3 py-2.5 text-base font-medium leading-6 text-gray-300 transition duration-150 ease-in-out hover:bg-gray-700 hover:text-white"
                >
                  <ArrowRightOnRectangleIcon className="mr-3 h-5 w-5 flex-shrink-0" />
                  Sign out
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

