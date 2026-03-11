'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/lib/auth';
import { useRouter } from 'next/navigation';
import {
  getWorkspaces,
  createWorkspace,
  getDashboardStats,
  getDailyActivity,
  getBusiestWorkspaces,
  getAgentTemplates,
  startAgent,
  Workspace,
  DashboardStats,
  DailyActivityItem,
  WorkspaceActivityItem,
  AgentTemplate,
  ApiError,
} from '@/lib/api';
import {
  RocketLaunchIcon,
  ChatBubbleLeftRightIcon,
  FolderIcon,
  CalendarDaysIcon,
  ArrowTrendingUpIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';
import WorkspaceCard from '@/components/WorkspaceCard';
import Modal from '@/components/Common/Modal';
import Button from '@/components/Common/Button';
import { ActivityHeatmap } from '@/components/ui/calendar-heatmap';

export default function DashboardPage() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activity, setActivity] = useState<DailyActivityItem[]>([]);
  const [busiestWorkspaces, setBusiestWorkspaces] = useState<WorkspaceActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [workspaceType, setWorkspaceType] = useState<'chat' | 'agent'>('chat');
  const [agentPurpose, setAgentPurpose] = useState('');
  const [agentTemplate, setAgentTemplate] = useState('custom');
  const [agentRepoUrl, setAgentRepoUrl] = useState('');
  const [agentTemplates, setAgentTemplates] = useState<Record<string, AgentTemplate>>({});
  const [isCreating, setIsCreating] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const { token } = useAuth();
  const { toast } = useToast();

  useEffect(() => {
    if (token) {
      setIsLoading(true);
      Promise.all([
        getWorkspaces(token, { archived: false }),
        getDashboardStats(token),
        getDailyActivity(token, 90),
        getBusiestWorkspaces(token, 6),
      ])
        .then(([workspacesRes, statsRes, activityRes, busiestRes]) => {
          setWorkspaces(workspacesRes.workspaces);
          setStats(statsRes);
          setActivity(activityRes.activity);
          setBusiestWorkspaces(busiestRes.workspaces);
        })
        .finally(() => setIsLoading(false));
    }
  }, [token]);

  // Convert activity data for heatmap
  const heatmapData = activity.map((item) => ({
    date: item.date,
    count: item.count,
  }));

  // Fetch agent templates when dialog opens with agent type
  useEffect(() => {
    if (isDialogOpen && workspaceType === 'agent' && token && Object.keys(agentTemplates).length === 0) {
      getAgentTemplates(token).then((res) => setAgentTemplates(res.templates)).catch(() => {});
    }
  }, [isDialogOpen, workspaceType, token, agentTemplates]);

  const handleCreateWorkspace = async () => {
    if (!token || !newWorkspaceName.trim()) return;
    setIsCreating(true);

    try {
      const agentConfig: Record<string, string> = { template: agentTemplate };
      if (agentTemplate === 'coder' && agentRepoUrl.trim()) {
        agentConfig.repo_url = agentRepoUrl.trim();
      }
      const options = workspaceType === 'agent' ? {
        workspace_type: 'agent' as const,
        agent_purpose: agentPurpose || undefined,
        agent_config: agentConfig,
      } : undefined;

      const workspace = await createWorkspace(token, newWorkspaceName.trim(), options);

      // Auto-start agent if this is an agent workspace
      if (workspaceType === 'agent') {
        try {
          await startAgent(token, workspace.id);
          toast({ title: 'Agent started', description: `${workspace.name} is now running.` });
        } catch (agentErr) {
          const msg = agentErr instanceof ApiError ? agentErr.message : 'Could not start agent';
          toast({ variant: 'destructive', title: 'Agent created but failed to start', description: msg });
        }
      }

      // Store workspace ID for the workspace settings page
      sessionStorage.setItem('mai-tai-new-workspace', JSON.stringify({
        workspaceId: workspace.id,
        workspaceName: workspace.name,
      }));

      setNewWorkspaceName('');
      setWorkspaceType('chat');
      setAgentPurpose('');
      setAgentTemplate('custom');
      setAgentRepoUrl('');
      setIsDialogOpen(false);

      // Navigate to the workspace
      router.push(`/workspaces/${workspace.id}?new=true`);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to create workspace',
        description: error instanceof ApiError ? error.message : 'Please try again',
      });
      setIsCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* New Workspace Modal */}
      <Modal
        open={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        title="Create a new workspace"
        subTitle={workspaceType === 'agent'
          ? 'Launch an autonomous AI agent that runs on your server.'
          : 'Each workspace is a chat room where you and your AI agents collaborate.'}
        onOk={handleCreateWorkspace}
        okText={isCreating ? 'Creating...' : workspaceType === 'agent' ? 'Create Agent' : 'Create Workspace'}
        okDisabled={!newWorkspaceName.trim()}
        okLoading={isCreating}
        cancelText="Cancel"
        size="sm"
      >
        <div className="space-y-4 py-2">
          {/* Workspace type toggle */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setWorkspaceType('chat')}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition ${
                workspaceType === 'chat'
                  ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                  : 'border-gray-600 bg-gray-700/50 text-gray-400 hover:border-gray-500 hover:text-gray-300'
              }`}
            >
              <ChatBubbleLeftRightIcon className="h-5 w-5" />
              Chat
            </button>
            <button
              type="button"
              onClick={() => setWorkspaceType('agent')}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition ${
                workspaceType === 'agent'
                  ? 'border-purple-500 bg-purple-500/20 text-purple-300'
                  : 'border-gray-600 bg-gray-700/50 text-gray-400 hover:border-gray-500 hover:text-gray-300'
              }`}
            >
              <CpuChipIcon className="h-5 w-5" />
              Agent
            </button>
          </div>

          {/* Name input */}
          <input
            type="text"
            placeholder={workspaceType === 'agent' ? 'Agent name (e.g. Rivian Scout)' : 'Workspace name'}
            value={newWorkspaceName}
            onChange={(e) => setNewWorkspaceName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !isCreating && newWorkspaceName.trim() && handleCreateWorkspace()}
            autoFocus
            className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />

          {/* Agent-specific fields */}
          {workspaceType === 'agent' && (
            <>
              {/* Template picker */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-300">Template</label>
                <select
                  value={agentTemplate}
                  onChange={(e) => setAgentTemplate(e.target.value)}
                  className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {Object.entries(agentTemplates).length > 0 ? (
                    Object.entries(agentTemplates).map(([key, tmpl]) => (
                      <option key={key} value={key}>{tmpl.label}</option>
                    ))
                  ) : (
                    <>
                      <option value="custom">Custom Agent</option>
                      <option value="coder">Coding Agent</option>
                      <option value="research">Research Assistant</option>
                      <option value="monitor">Daily Monitor</option>
                      <option value="assistant">Personal Assistant</option>
                    </>
                  )}
                </select>
                {agentTemplates[agentTemplate]?.description && (
                  <p className="mt-1 text-xs text-gray-500">{agentTemplates[agentTemplate].description}</p>
                )}
              </div>

              {/* Purpose */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-300">Purpose</label>
                <textarea
                  placeholder="What should this agent do? (e.g. Search for Rivian R1S deals daily and report findings)"
                  value={agentPurpose}
                  onChange={(e) => setAgentPurpose(e.target.value)}
                  rows={3}
                  className="w-full resize-none rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Repository URL (coder template only) */}
              {agentTemplate === 'coder' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-300">Repository URL</label>
                  <input
                    type="text"
                    placeholder="https://github.com/username/repo"
                    value={agentRepoUrl}
                    onChange={(e) => setAgentRepoUrl(e.target.value)}
                    className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    The agent will clone this repo. For private repos, add a GitHub token in Settings → AI.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </Modal>

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-6">
          {/* Stats skeleton */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <div key={`stat-skeleton-${i}`} className="h-24 animate-pulse rounded-xl bg-gray-800" />
            ))}
          </div>
          {/* Heatmap skeleton */}
          <div className="h-48 animate-pulse rounded-xl bg-gray-800" />
          {/* Projects skeleton */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {[...Array(6)].map((_, i) => (
              <div key={`project-skeleton-${i}`} className="aspect-[4/3] animate-pulse rounded-xl bg-gray-800" />
            ))}
          </div>
        </div>
      )}

      {/* Welcome banner for new users */}
      {!isLoading && workspaces.length === 0 && (
        <div className="rounded-xl border border-indigo-500/30 bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10 p-8">
          <div className="flex flex-col items-center text-center md:flex-row md:text-left md:items-start md:gap-6">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-indigo-500/20 md:mb-0">
              <RocketLaunchIcon className="h-8 w-8 text-indigo-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-xl font-bold text-white">🍹 Welcome to Mai-Tai!</h3>
              <p className="mt-2 text-gray-300">
                Connect your AI coding agent and chat in real-time.
              </p>
              <p className="mt-1 text-sm text-gray-400">
                Each workspace is a chat room for you and your AI agent — create one for each codebase.
              </p>
              <div className="mt-4">
                <Button buttonType="primary" onClick={() => setIsDialogOpen(true)}>
                  <RocketLaunchIcon className="mr-2 h-5 w-5" />
                  Create Your First Workspace
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dashboard content */}
      {!isLoading && workspaces.length > 0 && (
        <>
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white lg:text-3xl">Dashboard</h1>
              <p className="mt-1 text-gray-400">Your activity overview</p>
            </div>
            <Button buttonType="primary" onClick={() => setIsDialogOpen(true)}>
              <RocketLaunchIcon className="mr-2 h-5 w-5" />
              Add Workspace
            </Button>
          </div>

          {/* Stats Row */}
          {stats && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard
                icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />}
                label="Total Messages"
                value={stats.total_messages.toLocaleString()}
                color="indigo"
              />
              <StatCard
                icon={<ArrowTrendingUpIcon className="h-6 w-6" />}
                label="This Week"
                value={stats.messages_this_week.toLocaleString()}
                color="purple"
              />
              <StatCard
                icon={<FolderIcon className="h-6 w-6" />}
                label="Active Workspaces"
                value={(stats.active_workspaces ?? 0).toString()}
                color="blue"
              />
              <StatCard
                icon={<CalendarDaysIcon className="h-6 w-6" />}
                label="Total Workspaces"
                value={(stats.total_workspaces ?? 0).toString()}
                color="gray"
              />
            </div>
          )}

          {/* Activity Heatmap */}
          <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-4">
            <h2 className="mb-3 text-lg font-semibold text-white">Activity</h2>
            <ActivityHeatmap data={heatmapData} />
          </div>

          {/* Busiest Workspaces */}
          <div>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Most Active Workspaces</h2>
              <Link
                href="/workspaces"
                className="text-sm text-indigo-400 hover:text-indigo-300 transition"
              >
                View all →
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {busiestWorkspaces.map((workspace, index) => (
                <WorkspaceCard
                  key={workspace.id}
                  id={workspace.id}
                  name={workspace.name}
                  createdAt={workspace.last_activity || ''}
                  colorIndex={index}
                  badge={workspace.message_count > 0 ? `${workspace.message_count} msgs` : undefined}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// Stat card component
function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: 'indigo' | 'purple' | 'blue' | 'gray';
}) {
  const colorClasses = {
    indigo: 'bg-indigo-500/20 text-indigo-400',
    purple: 'bg-purple-500/20 text-purple-400',
    blue: 'bg-blue-500/20 text-blue-400',
    gray: 'bg-gray-500/20 text-gray-400',
  };

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-4">
      <div className="flex items-center gap-3">
        <div className={`rounded-lg p-2 ${colorClasses[color]}`}>{icon}</div>
        <div>
          <p className="text-2xl font-bold text-white">{value}</p>
          <p className="text-sm text-gray-400">{label}</p>
        </div>
      </div>
    </div>
  );
}

