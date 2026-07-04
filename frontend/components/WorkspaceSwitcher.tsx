'use client';

import { Fragment, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Menu, Transition } from '@headlessui/react';
import { ChevronDownIcon, CheckIcon } from '@heroicons/react/24/outline';
import { useAuth } from '@/lib/auth';
import { getWorkspaces, getAgentStatus, Workspace, AgentStatus } from '@/lib/api';

interface WorkspaceSwitcherProps {
  currentWorkspaceId: string;
  currentWorkspaceName: string;
}

interface WorkspaceWithStatus extends Workspace {
  agentStatus?: AgentStatus;
}

export default function WorkspaceSwitcher({
  currentWorkspaceId,
  currentWorkspaceName,
}: WorkspaceSwitcherProps) {
  const router = useRouter();
  const { token } = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceWithStatus[]>([]);
  const [workspaceCount, setWorkspaceCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch workspace count on mount to determine if dropdown should be shown
  useEffect(() => {
    if (!token) return;
    getWorkspaces(token, { archived: false })
      .then((response) => setWorkspaceCount(response.total))
      .catch(() => setWorkspaceCount(1)); // Assume 1 on error
  }, [token]);

  // Fetch workspaces and their statuses when dropdown opens
  const fetchWorkspaces = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const response = await getWorkspaces(token, { archived: false });
      // Sort by most recently updated
      const sorted = response.workspaces.sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );

      // Fetch agent status for each workspace (in parallel)
      const workspacesWithStatus = await Promise.all(
        sorted.map(async (ws) => {
          try {
            const status = await getAgentStatus(token, ws.id);
            return { ...ws, agentStatus: status };
          } catch {
            return { ...ws, agentStatus: undefined };
          }
        })
      );

      setWorkspaces(workspacesWithStatus);
    } catch (error) {
      console.error('Failed to fetch workspaces:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleWorkspaceClick = (workspaceId: string) => {
    if (workspaceId !== currentWorkspaceId) {
      router.push(`/workspaces/${workspaceId}`);
    }
  };

  const getStatusColor = (status?: AgentStatus) => {
    if (!status) return 'bg-surface2';
    switch (status.status) {
      case 'connected':
        return 'bg-success';
      case 'idle':
        return 'bg-warning';
      default:
        return 'bg-surface2';
    }
  };

  // If only one workspace (or still loading count), show plain text
  if (workspaceCount === null || workspaceCount <= 1) {
    return (
      <h1 className="text-xl font-bold text-foreground lg:text-2xl">
        {currentWorkspaceName || 'Loading...'}
      </h1>
    );
  }

  // Multiple workspaces: show dropdown
  return (
    <Menu as="div" className="relative">
      {({ open }) => (
        <>
          <Menu.Button
            onClick={() => {
              if (!open) fetchWorkspaces();
            }}
            className="flex items-center gap-1 text-xl font-bold text-foreground hover:text-primary/80 transition-colors lg:text-2xl"
          >
            {currentWorkspaceName || 'Loading...'}
            <ChevronDownIcon className="h-5 w-5" />
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
            <Menu.Items className="absolute left-0 mt-2 w-72 origin-top-left rounded-lg shadow-lg ring-1 ring-border focus:outline-none overflow-hidden z-50">
              <div className="glass-effect max-h-80 overflow-y-auto">
                {isLoading ? (
                  <div className="px-4 py-3 text-sm text-muted-foreground">Loading...</div>
                ) : workspaces.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-muted-foreground">No workspaces found</div>
                ) : (
                  workspaces.map((ws) => (
                    <Menu.Item key={ws.id}>
                      {({ active }) => (
                        <button
                          onClick={() => handleWorkspaceClick(ws.id)}
                          className={`flex w-full items-center justify-between px-4 py-3 text-left text-sm transition-colors ${
                            active ? 'bg-surface2/50' : ''
                          } ${ws.id === currentWorkspaceId ? 'bg-primary/20' : ''}`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <span
                              className={`h-2 w-2 shrink-0 rounded-full ${getStatusColor(ws.agentStatus)}`}
                              title={ws.agentStatus?.message || 'Unknown status'}
                            />
                            <span className="truncate text-foreground font-medium">{ws.name}</span>
                          </div>
                          {ws.id === currentWorkspaceId && (
                            <CheckIcon className="h-4 w-4 shrink-0 text-primary" />
                          )}
                        </button>
                      )}
                    </Menu.Item>
                  ))
                )}
              </div>
            </Menu.Items>
          </Transition>
        </>
      )}
    </Menu>
  );
}

