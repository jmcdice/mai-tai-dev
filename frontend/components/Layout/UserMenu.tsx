'use client';

import { Fragment } from 'react';
import Link from 'next/link';
import { Menu, Transition } from '@headlessui/react';
import {
  UserIcon,
  Cog6ToothIcon,
  BoltIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '@/lib/auth';

export default function UserMenu() {
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
  };

  return (
    <Menu as="div" className="relative">
      <Menu.Button className="flex items-center rounded-full ring-1 ring-border hover:ring-border-strong focus:outline-none focus:ring-border-strong transition-all">
        <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-surface2 sm:h-10 sm:w-10">
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.name || 'Avatar'}
              className="h-full w-full object-cover"
            />
          ) : user?.name ? (
            <span className="text-sm font-medium text-foreground">
              {user.name.charAt(0).toUpperCase()}
            </span>
          ) : user?.email ? (
            <span className="text-sm font-medium text-foreground">
              {user.email.charAt(0).toUpperCase()}
            </span>
          ) : (
            <UserIcon className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
      </Menu.Button>

      <Transition
        as={Fragment}
        enter="transition ease-out duration-100"
        enterFrom="transform opacity-0 scale-95"
        enterTo="transform opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="transform opacity-100 scale-100"
        leaveTo="transform opacity-0 scale-95"
      >
        <Menu.Items className="absolute right-0 mt-2 w-64 origin-top-right rounded-lg shadow-lg ring-1 ring-border focus:outline-none overflow-hidden">
          <div className="glass-effect divide-y divide-border">
            {/* User info */}
            <div className="flex items-center gap-3 px-4 py-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface2">
                {user?.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.name || 'Avatar'}
                    className="h-full w-full object-cover"
                  />
                ) : user?.name ? (
                  <span className="text-sm font-medium text-foreground">
                    {user.name.charAt(0).toUpperCase()}
                  </span>
                ) : (
                  <UserIcon className="h-5 w-5 text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {user?.name || 'Guest'}
                </p>
                {user?.email && (
                  <p className="truncate text-xs text-muted-foreground">
                    {user.email}
                  </p>
                )}
              </div>
            </div>

            {/* Menu items */}
            <div className="py-1">
              <Menu.Item>
                {({ active }) => (
                  <Link
                    href="/settings"
                    className={`flex items-center px-4 py-2 text-sm font-medium transition-colors ${
                      active
                        ? 'nav-active text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Cog6ToothIcon className="mr-3 h-5 w-5" />
                    Settings
                  </Link>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <Link
                    href="/settings?tab=shortcuts"
                    className={`flex items-center px-4 py-2 text-sm font-medium transition-colors ${
                      active
                        ? 'nav-active text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <BoltIcon className="mr-3 h-5 w-5" />
                    Shortcuts
                  </Link>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <button
                    onClick={handleLogout}
                    className={`flex w-full items-center px-4 py-2 text-sm font-medium transition-colors ${
                      active
                        ? 'nav-active text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <ArrowRightOnRectangleIcon className="mr-3 h-5 w-5" />
                    Sign out
                  </button>
                )}
              </Menu.Item>
            </div>
          </div>
        </Menu.Items>
      </Transition>
    </Menu>
  );
}

