'use client';

import { Fragment, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Popover, Transition } from '@headlessui/react';
import { ChatBubbleLeftRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useAuth } from '@/lib/auth';
import { getWorkspaces, Workspace } from '@/lib/api';

export default function WorkspacesPopup() {
  const router = useRouter();
  const { token } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch recent workspaces when popup opens
  const fetchWorkspaces = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const response = await getWorkspaces(token, { archived: false });
      // Get the 5 most recent workspaces
      const sorted = response.workspaces
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 5);
      setWorkspaces(sorted);
    } catch (error) {
      console.error('Failed to fetch workspaces:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleWorkspaceClick = (workspace: Workspace, close: () => void) => {
    router.push(`/workspaces/${workspace.id}`);
    close();
  };

  return (
    <Popover className="relative flex flex-1">
      {({ open, close }) => (
        <>
          <Popover.Button
            onClick={() => {
              if (!open) fetchWorkspaces();
            }}
            className="flex flex-1 flex-col items-center py-3 text-xs font-medium text-muted-foreground active:text-foreground transition-colors touch-manipulation focus:outline-none"
          >
            {open ? (
              <XMarkIcon className="h-6 w-6 text-primary" />
            ) : (
              <ChatBubbleLeftRightIcon className="h-6 w-6" />
            )}
            <span className={`mt-1 ${open ? 'text-primary' : ''}`}>Chats</span>
          </Popover.Button>

          <Transition
            as={Fragment}
            enter="transition ease-out duration-200"
            enterFrom="opacity-0 translate-y-4"
            enterTo="opacity-100 translate-y-0"
            leave="transition ease-in duration-150"
            leaveFrom="opacity-100 translate-y-0"
            leaveTo="opacity-0 translate-y-4"
          >
            <Popover.Panel className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-80 origin-bottom rounded-lg shadow-lg ring-1 ring-border focus:outline-none overflow-hidden z-50">
              <div className="glass-effect">
                <div className="px-4 py-3 border-b border-border">
                  <h3 className="text-sm font-medium text-foreground">Recent Workspaces</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Jump to a recent conversation</p>
                </div>
                <div className="py-1">
                  {isLoading ? (
                    <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                      Loading...
                    </div>
                  ) : workspaces.length === 0 ? (
                    <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                      No workspaces yet
                    </div>
                  ) : (
                    workspaces.map((workspace) => (
                      <button
                        key={workspace.id}
                        onClick={() => handleWorkspaceClick(workspace, close)}
                        className="flex w-full items-center gap-3 px-4 py-3 text-sm text-muted-foreground hover:bg-surface2/50 hover:text-foreground transition-colors touch-manipulation"
                      >
                        <ChatBubbleLeftRightIcon className="h-5 w-5 text-faint flex-shrink-0" />
                        <div className="min-w-0 flex-1 text-left">
                          <p className="font-medium truncate">{workspace.name}</p>
                        </div>
                      </button>
                    ))
                  )}
                </div>
                <div className="px-4 py-2 border-t border-border">
                  <button
                    onClick={() => {
                      router.push('/workspaces');
                      close();
                    }}
                    className="w-full text-center text-xs text-primary hover:text-primary/80 py-1"
                  >
                    View all workspaces
                  </button>
                </div>
              </div>
            </Popover.Panel>
          </Transition>
        </>
      )}
    </Popover>
  );
}

