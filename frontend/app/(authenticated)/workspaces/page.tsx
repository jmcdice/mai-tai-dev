'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PlusIcon } from '@heroicons/react/24/outline';
import { useAuth } from '@/lib/auth';
import { getWorkspaces, Workspace } from '@/lib/api';
import WorkspaceCard from '@/components/WorkspaceCard';
import Button from '@/components/Common/Button';
import OnboardingFlow from '@/components/Setup/OnboardingFlow';

export default function WorkspacesPage() {
  const router = useRouter();
  const { token, isLoading } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'name'>('newest');
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    if (!isLoading && !token) {
      router.push('/login');
    }
  }, [isLoading, token, router]);

  useEffect(() => {
    if (token) {
      getWorkspaces(token).then((res) => setWorkspaces(res.workspaces));
    }
  }, [token]);

  // Filter and sort workspaces
  const sortedWorkspaces = useMemo(() => {
    const filtered = showArchived ? workspaces : workspaces.filter(w => !w.archived);
    return [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'newest':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'oldest':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case 'name':
          return a.name.localeCompare(b.name);
        default:
          return 0;
      }
    });
  }, [workspaces, sortBy, showArchived]);

  const archivedCount = useMemo(() => workspaces.filter(w => w.archived).length, [workspaces]);

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  // Show onboarding flow for new users with no workspaces
  if (workspaces.length === 0) {
    return (
      <div className="py-8">
        <OnboardingFlow />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white lg:text-3xl">Workspaces</h1>
          <p className="mt-1 text-gray-400">
            {sortedWorkspaces.length} {sortedWorkspaces.length === 1 ? 'workspace' : 'workspaces'}
            {showArchived && archivedCount > 0 && ` (${archivedCount} archived)`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {/* Show archived toggle */}
          {archivedCount > 0 && (
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500"
              />
              Show archived
            </label>
          )}
          {/* Sort dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'newest' | 'oldest' | 'name')}
            className="rounded-lg border border-gray-600 bg-gray-700 px-4 py-2.5 text-white transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="name">Name (A-Z)</option>
          </select>
          <Link href="/dashboard">
            <Button buttonType="primary">
              <PlusIcon className="mr-2 h-5 w-5" />
              New Workspace
            </Button>
          </Link>
        </div>
      </div>

      {/* Workspaces Grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {sortedWorkspaces.map((workspace, index) => (
          <WorkspaceCard
            key={workspace.id}
            id={workspace.id}
            name={workspace.name}
            createdAt={workspace.created_at}
            colorIndex={index}
            archived={workspace.archived}
            workspaceType={workspace.workspace_type}
          />
        ))}
      </div>
    </div>
  );
}

