'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import {
  getAdminUsers,
  getAdminStats,
  getAdminSettings,
  updateAdminSettings,
  deleteUser,
  impersonateUser,
  toggleUserAdmin,
  getAdminFeedback,
  updateFeedbackStatus,
  AdminUser,
  AdminStats,
  AdminSettings,
  AdminFeedback,
  ApiError,
} from '@/lib/api';
import {
  UsersIcon,
  FolderIcon,
  ChatBubbleLeftRightIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserIcon,
  CpuChipIcon,
  ChatBubbleLeftEllipsisIcon,
  CheckIcon,
  ArchiveBoxIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';

export default function AdminPage() {
  const { user, token, login } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [adminSettings, setAdminSettings] = useState<AdminSettings | null>(null);
  const [feedback, setFeedback] = useState<AdminFeedback[]>([]);
  const [feedbackFilter, setFeedbackFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    const fetchData = async () => {
      try {
        const [usersData, statsData, settingsData, feedbackData] = await Promise.all([
          getAdminUsers(token),
          getAdminStats(token),
          getAdminSettings(token),
          getAdminFeedback(token),
        ]);
        setUsers(usersData);
        setStats(statsData);
        setAdminSettings(settingsData);
        setFeedback(feedbackData);
        setError(null);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          router.push('/dashboard');
          return;
        }
        setError('Failed to load admin data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [token, router]);

  const handleDelete = async (userId: string, userName: string) => {
    if (!confirm(`Delete user "${userName}"? This cannot be undone.`)) return;
    if (!token) return;

    setActionLoading(userId);
    try {
      await deleteUser(token, userId);
      setUsers(users.filter((u) => u.id !== userId));
      if (stats) {
        setStats({ ...stats, total_users: stats.total_users - 1 });
      }
    } catch (err) {
      alert('Failed to delete user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleImpersonate = async (userId: string, userName: string) => {
    if (!confirm(`Impersonate "${userName}"? You'll be logged in as them.`)) return;
    if (!token) return;

    setActionLoading(userId);
    try {
      const response = await impersonateUser(token, userId);
      login(response.access_token, response.refresh_token);
      router.push('/dashboard');
    } catch (err) {
      alert('Failed to impersonate user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleAdmin = async (userId: string) => {
    if (!token) return;

    setActionLoading(userId);
    try {
      const response = await toggleUserAdmin(token, userId);
      setUsers(users.map((u) => (u.id === userId ? { ...u, is_admin: response.is_admin } : u)));
      if (stats) {
        setStats({
          ...stats,
          admin_count: response.is_admin ? stats.admin_count + 1 : stats.admin_count - 1,
        });
      }
    } catch (err) {
      alert('Failed to toggle admin status');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleRegistration = async () => {
    if (!token || !adminSettings) return;
    setActionLoading('registration');
    try {
      const updated = await updateAdminSettings(token, {
        registration_enabled: !adminSettings.registration_enabled,
      });
      setAdminSettings(updated);
    } catch {
      alert('Failed to update registration setting');
    } finally {
      setActionLoading(null);
    }
  };

  const handleFeedbackStatus = async (feedbackId: string, status: string) => {
    if (!token) return;

    setActionLoading(feedbackId);
    try {
      const updated = await updateFeedbackStatus(token, feedbackId, status);
      setFeedback(feedback.map((f) => (f.id === feedbackId ? updated : f)));
    } catch (err) {
      alert('Failed to update feedback status');
    } finally {
      setActionLoading(null);
    }
  };

  const filteredFeedback = feedbackFilter
    ? feedback.filter((f) => f.status === feedbackFilter)
    : feedback;

  const feedbackCounts = {
    new: feedback.filter((f) => f.status === 'new').length,
    read: feedback.filter((f) => f.status === 'read').length,
    archived: feedback.filter((f) => f.status === 'archived').length,
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-secondary border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold text-foreground">Admin Dashboard</h1>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <StatCard icon={UsersIcon} label="Users" value={stats.total_users} />
          <StatCard icon={FolderIcon} label="Workspaces" value={stats.total_workspaces} />
          <StatCard icon={ChatBubbleLeftRightIcon} label="Messages" value={stats.total_messages} />
          <StatCard icon={ShieldCheckIcon} label="Admins" value={stats.admin_count} />
          <StatCard icon={CpuChipIcon} label="Connected Agents" value={stats.connected_agents ?? 0} />
        </div>
      )}

      {/* Site Settings */}
      {adminSettings && (
        <div className="rounded-lg border border-border bg-card/50 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-foreground">User Registration</h3>
              <p className="text-sm text-muted-foreground">
                {adminSettings.registration_enabled
                  ? 'New users can create accounts'
                  : 'Registration is disabled — only existing users can log in'}
              </p>
            </div>
            <button
              onClick={handleToggleRegistration}
              disabled={actionLoading === 'registration'}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                adminSettings.registration_enabled
                  ? 'bg-success/20 text-success hover:bg-success/30'
                  : 'bg-destructive/20 text-destructive hover:bg-destructive/30'
              }`}
            >
              {actionLoading === 'registration'
                ? 'Updating...'
                : adminSettings.registration_enabled
                ? 'Enabled'
                : 'Disabled'}
            </button>
          </div>
        </div>
      )}

      {/* Users - Mobile Cards */}
      <div className="space-y-3 md:hidden">
        {users.map((u) => (
          <div key={u.id} className="rounded-lg border border-border bg-card/50 p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center">
                {u.avatar_url ? (
                  <img src={u.avatar_url} alt="" className="h-10 w-10 rounded-full" />
                ) : (
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface2">
                    <span className="text-sm font-medium text-foreground">
                      {u.name.charAt(0).toUpperCase()}
                    </span>
                  </div>
                )}
                <div className="ml-3">
                  <p className="font-medium text-foreground">{u.name}</p>
                  <p className="text-sm text-muted-foreground">{u.email}</p>
                </div>
              </div>
              <button
                onClick={() => handleToggleAdmin(u.id)}
                disabled={u.id === user?.id || actionLoading === u.id}
                className={`rounded px-2 py-1 text-xs font-medium ${
                  u.is_admin
                    ? 'bg-secondary/20 text-secondary'
                    : 'bg-surface2/20 text-muted-foreground'
                } ${u.id === user?.id ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                {u.is_admin ? 'Admin' : 'User'}
              </button>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <div className="flex gap-4 text-muted-foreground">
                <span>{u.workspace_count} workspaces</span>
                <span>{(u.message_count ?? 0).toLocaleString()} msgs</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleImpersonate(u.id, u.name)}
                  disabled={u.id === user?.id || actionLoading === u.id}
                  className="rounded p-1.5 text-muted-foreground hover:bg-surface2 hover:text-foreground disabled:opacity-50"
                  title="Impersonate"
                >
                  <UserIcon className="h-5 w-5" />
                </button>
                <button
                  onClick={() => handleDelete(u.id, u.name)}
                  disabled={u.id === user?.id || actionLoading === u.id}
                  className="rounded p-1.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive disabled:opacity-50"
                  title="Delete"
                >
                  <TrashIcon className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Users - Desktop Table */}
      <div className="hidden overflow-hidden rounded-lg border border-border bg-card/50 md:block">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-card">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                User
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Workspaces
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Messages
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Admin
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Joined
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-surface2/50">
                <td className="whitespace-nowrap px-4 py-3">
                  <div className="flex items-center">
                    {u.avatar_url ? (
                      <img src={u.avatar_url} alt="" className="h-8 w-8 rounded-full" />
                    ) : (
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface2">
                        <span className="text-sm font-medium text-foreground">
                          {u.name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    <div className="ml-3">
                      <p className="text-sm font-medium text-foreground">{u.name}</p>
                      <p className="text-xs text-muted-foreground">{u.email}</p>
                    </div>
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
                  {u.workspace_count}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
                  {(u.message_count ?? 0).toLocaleString()}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <button
                    onClick={() => handleToggleAdmin(u.id)}
                    disabled={u.id === user?.id || actionLoading === u.id}
                    className={`rounded px-2 py-1 text-xs font-medium ${
                      u.is_admin
                        ? 'bg-secondary/20 text-secondary'
                        : 'bg-surface2/20 text-muted-foreground'
                    } ${u.id === user?.id ? 'cursor-not-allowed opacity-50' : 'hover:opacity-80'}`}
                  >
                    {u.is_admin ? 'Admin' : 'User'}
                  </button>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <div className="flex items-center justify-end space-x-2">
                    <button
                      onClick={() => handleImpersonate(u.id, u.name)}
                      disabled={u.id === user?.id || actionLoading === u.id}
                      className="rounded p-1 text-muted-foreground hover:bg-surface2 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                      title="Impersonate"
                    >
                      <UserIcon className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(u.id, u.name)}
                      disabled={u.id === user?.id || actionLoading === u.id}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                      title="Delete"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Feedback Section */}
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <ChatBubbleLeftEllipsisIcon className="h-6 w-6" />
            User Feedback
          </h2>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setFeedbackFilter(null)}
              className={`rounded px-3 py-1 text-sm ${
                feedbackFilter === null
                  ? 'bg-secondary/20 text-secondary'
                  : 'bg-surface2 text-muted-foreground hover:text-foreground'
              }`}
            >
              All ({feedback.length})
            </button>
            <button
              onClick={() => setFeedbackFilter('new')}
              className={`rounded px-3 py-1 text-sm ${
                feedbackFilter === 'new'
                  ? 'bg-destructive/20 text-destructive'
                  : 'bg-surface2 text-muted-foreground hover:text-foreground'
              }`}
            >
              New ({feedbackCounts.new})
            </button>
            <button
              onClick={() => setFeedbackFilter('read')}
              className={`rounded px-3 py-1 text-sm ${
                feedbackFilter === 'read'
                  ? 'bg-info/20 text-info'
                  : 'bg-surface2 text-muted-foreground hover:text-foreground'
              }`}
            >
              Read ({feedbackCounts.read})
            </button>
            <button
              onClick={() => setFeedbackFilter('archived')}
              className={`rounded px-3 py-1 text-sm ${
                feedbackFilter === 'archived'
                  ? 'bg-surface2/20 text-muted-foreground'
                  : 'bg-surface2 text-muted-foreground hover:text-foreground'
              }`}
            >
              Archived ({feedbackCounts.archived})
            </button>
          </div>
        </div>

        {filteredFeedback.length === 0 ? (
          <div className="rounded-lg border border-border bg-card/50 p-8 text-center">
            <EnvelopeIcon className="mx-auto h-12 w-12 text-faint" />
            <p className="mt-2 text-muted-foreground">No feedback yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredFeedback.map((f) => (
              <div
                key={f.id}
                className="rounded-lg border border-border bg-card/50 p-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          f.status === 'new'
                            ? 'bg-destructive'
                            : f.status === 'read'
                            ? 'bg-info'
                            : 'bg-surface2'
                        }`}
                      />
                      <h3 className="font-medium text-foreground">{f.subject}</h3>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{f.message}</p>
                    <p className="mt-2 text-xs text-faint">
                      From {f.user_name} ({f.user_email}) •{' '}
                      {new Date(f.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="ml-4 flex gap-1">
                    {f.status !== 'read' && (
                      <button
                        onClick={() => handleFeedbackStatus(f.id, 'read')}
                        disabled={actionLoading === f.id}
                        className="rounded p-1.5 text-muted-foreground hover:bg-info/20 hover:text-info disabled:opacity-50"
                        title="Mark as read"
                      >
                        <CheckIcon className="h-4 w-4" />
                      </button>
                    )}
                    {f.status !== 'archived' && (
                      <button
                        onClick={() => handleFeedbackStatus(f.id, 'archived')}
                        disabled={actionLoading === f.id}
                        className="rounded p-1.5 text-muted-foreground hover:bg-surface2/20 hover:text-muted-foreground disabled:opacity-50"
                        title="Archive"
                      >
                        <ArchiveBoxIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-lg border border-border bg-card/50 p-4">
      <div className="flex items-center">
        <Icon className="h-8 w-8 text-secondary" />
        <div className="ml-3">
          <p className="text-2xl font-bold text-foreground">{value.toLocaleString()}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
    </div>
  );
}

