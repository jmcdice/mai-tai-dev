/**
 * API client for mai-tai backend
 */

// Get API URL - uses NEXT_PUBLIC_API_URL if set, otherwise constructs from current host
function getApiUrl(): string {
  // If env var is set (production), use it
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) {
    return envUrl;
  }

  // Server-side fallback
  if (typeof window === 'undefined') {
    return 'http://localhost:8000';
  }

  // Client-side fallback: use same host as the page, but port 8000 (for local dev on LAN)
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8000`;
}

const API_URL = getApiUrl();

interface ApiOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function api<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, token } = options;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Unknown error' }));

    // On 401 (unauthorized), clear tokens and redirect to home
    // Skip for /auth/me endpoint - let auth context handle it during initial load
    if (res.status === 401 && typeof window !== 'undefined' && !endpoint.includes('/auth/me')) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/';
      // Return a promise that never resolves to prevent further code execution
      return new Promise(() => {}) as T;
    }

    throw new ApiError(res.status, error.detail || 'Request failed');
  }

  if (res.status === 204) {
    return null as T;
  }

  return res.json();
}

// Auth
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserShortcut {
  id: string;
  label: string;
  text: string;
}

export interface UserSettings {
  timezone?: string | null;
  time_format?: '12h' | '24h' | null;
  shortcuts?: UserShortcut[] | null;
  anthropic_api_key?: string | null;
  github_token?: string | null;
  stash_llm_provider?: string | null;
  stash_llm_model?: string | null;
  stash_llm_api_key?: string | null;
  stash_ollama_base_url?: string | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url?: string | null;
  is_admin?: boolean;
  settings?: UserSettings | null;
}

// Admin APIs
export interface AdminUser {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  is_admin: boolean;
  created_at: string;
  workspace_count: number;
  message_count: number;
}

export interface AdminStats {
  total_users: number;
  total_workspaces: number;
  total_messages: number;
  admin_count: number;
  connected_agents: number;
}

export interface ImpersonateResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  user_email: string;
  user_name: string;
}

export async function getAdminUsers(token: string): Promise<AdminUser[]> {
  return api('/api/v1/admin/users', { token });
}

export async function getAdminStats(token: string): Promise<AdminStats> {
  return api('/api/v1/admin/stats', { token });
}

export async function deleteUser(token: string, userId: string): Promise<{ status: string }> {
  return api(`/api/v1/admin/users/${userId}`, { method: 'DELETE', token });
}

export async function impersonateUser(token: string, userId: string): Promise<ImpersonateResponse> {
  return api(`/api/v1/admin/impersonate/${userId}`, { method: 'POST', token });
}

export async function toggleUserAdmin(token: string, userId: string): Promise<{ status: string; is_admin: boolean }> {
  return api(`/api/v1/admin/users/${userId}/toggle-admin`, { method: 'POST', token });
}

export interface AdminSettings {
  registration_enabled: boolean;
}

export async function getAdminSettings(token: string): Promise<AdminSettings> {
  return api('/api/v1/admin/settings', { token });
}

export async function updateAdminSettings(token: string, settings: Partial<AdminSettings>): Promise<AdminSettings> {
  return api('/api/v1/admin/settings', { method: 'PATCH', token, body: settings });
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new ApiError(res.status, error.detail || 'Login failed');
  }

  return res.json();
}

// Agent types for registration
export type AgentType = 'augment' | 'claude' | 'cursor' | 'windsurf' | 'gemini' | 'other';

export interface RegisterResponse {
  user: User;
  workspace: {
    id: string;
    name: string;
    settings: Record<string, unknown>;
  };
  api_key: {
    id: string;
    key: string;
    name: string;
  };
}

export async function register(
  name: string,
  email: string,
  password: string,
  agentType?: AgentType
): Promise<RegisterResponse> {
  return api('/api/v1/auth/register', {
    method: 'POST',
    body: { name, email, password, agent_type: agentType },
  });
}

export async function getMe(token: string): Promise<User> {
  return api('/api/v1/auth/me', { token });
}

export async function updateMe(
  token: string,
  data: { name?: string; avatar_url?: string; settings?: UserSettings }
): Promise<User> {
  return api('/api/v1/auth/me', { method: 'PUT', token, body: data });
}

export async function changePassword(token: string, currentPassword: string, newPassword: string): Promise<void> {
  return api('/api/v1/auth/change-password', {
    method: 'POST',
    token,
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

/**
 * Get current user in IAP mode (no token needed - IAP cookie handles auth)
 */
export async function getMeIAP(): Promise<User> {
  const res = await fetch(`${API_URL}/api/v1/auth/me`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // Include IAP cookies
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Not authenticated' }));
    throw new ApiError(res.status, error.detail || 'Not authenticated');
  }

  return res.json();
}

// Workspaces (simplified from Projects - no channels, one workspace = one chat)
export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
  settings: Record<string, unknown>;
  archived: boolean;
  created_at: string;
  updated_at: string;
  workspace_type?: string;
  agent_purpose?: string | null;
  agent_config?: Record<string, unknown> | null;
}

// Legacy alias for backwards compatibility during migration
export type Project = Workspace;

export async function getWorkspaces(
  token: string,
  options?: { archived?: boolean }
): Promise<{ workspaces: Workspace[]; total: number }> {
  const params = new URLSearchParams();
  if (options?.archived !== undefined) {
    params.set('archived', String(options.archived));
  }
  const query = params.toString();
  return api(`/api/v1/workspaces${query ? `?${query}` : ''}`, { token });
}

// Legacy alias
export async function getProjects(
  token: string,
  options?: { archived?: boolean }
): Promise<{ projects: Workspace[]; total: number }> {
  const res = await getWorkspaces(token, options);
  return { projects: res.workspaces, total: res.total };
}

export async function getWorkspace(token: string, workspaceId: string): Promise<Workspace> {
  return api(`/api/v1/workspaces/${workspaceId}`, { token });
}

// Legacy alias
export async function getProject(token: string, projectId: string): Promise<Workspace> {
  return getWorkspace(token, projectId);
}

export async function createWorkspace(
  token: string,
  name: string,
  options?: {
    workspace_type?: string;
    agent_purpose?: string;
    agent_config?: Record<string, unknown>;
  },
): Promise<Workspace> {
  return api('/api/v1/workspaces', {
    method: 'POST',
    body: { name, ...options },
    token,
  });
}

export interface AgentTemplate {
  id: string;
  label: string;
  description: string;
}

export async function getAgentTemplates(token: string): Promise<{ templates: Record<string, AgentTemplate> }> {
  return api('/api/v1/workspaces/agent-templates', { token });
}

export async function startAgent(token: string, workspaceId: string): Promise<{ status: string; container?: string; container_id?: string; message?: string }> {
  return api(`/api/v1/workspaces/${workspaceId}/agent/start`, { method: 'POST', token });
}

export async function stopAgent(token: string, workspaceId: string): Promise<{ status: string }> {
  return api(`/api/v1/workspaces/${workspaceId}/agent/stop`, { method: 'POST', token });
}

export async function getAgentContainerStatus(token: string, workspaceId: string): Promise<{ status: string; running: boolean; container?: string }> {
  return api(`/api/v1/workspaces/${workspaceId}/agent/container-status`, { token });
}

// Legacy alias
export async function createProject(token: string, name: string): Promise<Workspace> {
  return createWorkspace(token, name);
}

export async function deleteWorkspace(token: string, workspaceId: string): Promise<void> {
  return api(`/api/v1/workspaces/${workspaceId}`, { method: 'DELETE', token });
}

// Legacy alias
export async function deleteProject(token: string, projectId: string): Promise<void> {
  return deleteWorkspace(token, projectId);
}

export async function updateWorkspace(
  token: string,
  workspaceId: string,
  data: { name?: string; settings?: Record<string, unknown>; archived?: boolean }
): Promise<Workspace> {
  return api(`/api/v1/workspaces/${workspaceId}`, { method: 'PATCH', body: data, token });
}

// Legacy alias
export async function updateProject(
  token: string,
  projectId: string,
  data: { name?: string; settings?: Record<string, unknown>; archived?: boolean }
): Promise<Workspace> {
  return updateWorkspace(token, projectId, data);
}

export async function archiveWorkspace(token: string, workspaceId: string): Promise<Workspace> {
  return updateWorkspace(token, workspaceId, { archived: true });
}

// Legacy alias
export async function archiveProject(token: string, projectId: string): Promise<Workspace> {
  return archiveWorkspace(token, projectId);
}

export async function unarchiveWorkspace(token: string, workspaceId: string): Promise<Workspace> {
  return updateWorkspace(token, workspaceId, { archived: false });
}

// Legacy alias
export async function unarchiveProject(token: string, projectId: string): Promise<Workspace> {
  return unarchiveWorkspace(token, projectId);
}

// Messages (now directly on workspace, no channel layer)
export interface Message {
  id: string;
  workspace_id: string;
  user_id: string | null;
  agent_name: string | null;
  sender_name: string | null;
  sender_avatar_url: string | null;
  content: string;
  message_metadata: Record<string, unknown>;
  created_at: string;
  message_type: string;
}

export async function getMessages(
  token: string,
  workspaceId: string
): Promise<{ messages: Message[]; has_more: boolean; total: number }> {
  return api(`/api/v1/workspaces/${workspaceId}/messages`, { token });
}

export async function sendMessage(
  token: string,
  workspaceId: string,
  content: string,
  messageType: string = 'chat'
): Promise<Message> {
  return api(`/api/v1/workspaces/${workspaceId}/messages`, {
    method: 'POST',
    body: { content, message_type: messageType },
    token,
  });
}

// API Keys
export interface ApiKey {
  id: string;
  name: string;
  key?: string; // Only present on creation
  user_id?: string; // Set for user-level keys
  workspace_id?: string; // Set for workspace-level keys
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

// User-level API keys (work for all workspaces)
export async function getUserApiKeys(token: string): Promise<{ api_keys: ApiKey[]; total: number }> {
  return api(`/api/v1/users/me/api-keys`, { token });
}

export async function createUserApiKey(token: string, name: string): Promise<ApiKey> {
  return api(`/api/v1/users/me/api-keys`, { method: 'POST', body: { name }, token });
}

export async function deleteUserApiKey(token: string, keyId: string): Promise<void> {
  return api(`/api/v1/users/me/api-keys/${keyId}`, { method: 'DELETE', token });
}

export async function regenerateUserApiKey(token: string, keyId: string): Promise<ApiKey> {
  return api(`/api/v1/users/me/api-keys/${keyId}/regenerate`, { method: 'POST', token });
}

// Workspace-level API keys (legacy, for backward compatibility)
export async function getApiKeys(token: string, workspaceId: string): Promise<{ api_keys: ApiKey[]; total: number }> {
  return api(`/api/v1/workspaces/${workspaceId}/api-keys`, { token });
}

export async function createApiKey(token: string, workspaceId: string, name: string): Promise<ApiKey> {
  return api(`/api/v1/workspaces/${workspaceId}/api-keys`, { method: 'POST', body: { name }, token });
}

export async function deleteApiKey(token: string, workspaceId: string, keyId: string): Promise<void> {
  return api(`/api/v1/workspaces/${workspaceId}/api-keys/${keyId}`, { method: 'DELETE', token });
}

// Agent Status
export interface AgentStatus {
  status: 'connected' | 'idle' | 'offline';
  last_activity: string | null;
  seconds_since_activity?: number;
  message: string;
}

export async function getAgentStatus(token: string, workspaceId: string): Promise<AgentStatus> {
  return api(`/api/v1/workspaces/${workspaceId}/agent-status`, { token });
}

// Dashboard
export interface DashboardStats {
  total_messages: number;
  messages_this_week: number;
  active_workspaces: number;
  total_workspaces: number;
}

export interface DailyActivityItem {
  date: string;
  count: number;
}

export interface DailyActivityResponse {
  activity: DailyActivityItem[];
}

export interface WorkspaceActivityItem {
  id: string;
  name: string;
  message_count: number;
  last_activity: string | null;
}

// Legacy alias
export type ProjectActivityItem = WorkspaceActivityItem;

export interface BusiestWorkspacesResponse {
  workspaces: WorkspaceActivityItem[];
}

// Legacy alias
export type BusiestProjectsResponse = { projects: WorkspaceActivityItem[] };

export async function getDashboardStats(token: string): Promise<DashboardStats> {
  return api('/api/v1/dashboard/stats', { token });
}

export async function getDailyActivity(token: string, days: number = 90): Promise<DailyActivityResponse> {
  return api(`/api/v1/dashboard/activity?days=${days}`, { token });
}

export async function getBusiestWorkspaces(token: string, limit: number = 6): Promise<BusiestWorkspacesResponse> {
  return api(`/api/v1/dashboard/busiest-workspaces?limit=${limit}`, { token });
}

// Legacy alias
export async function getBusiestProjects(token: string, limit: number = 6): Promise<BusiestProjectsResponse> {
  const res = await getBusiestWorkspaces(token, limit);
  return { projects: res.workspaces };
}

// --- Feedback ---

export interface Feedback {
  id: string;
  subject: string;
  message: string;
  status: string;
  created_at: string;
}

export interface AdminFeedback extends Feedback {
  user_id: string;
  user_email: string;
  user_name: string;
}

export async function submitFeedback(token: string, subject: string, message: string): Promise<Feedback> {
  return api('/api/v1/feedback', { method: 'POST', body: { subject, message }, token });
}

export async function getAdminFeedback(token: string, status?: string): Promise<AdminFeedback[]> {
  const url = status ? `/api/v1/feedback/admin?status_filter=${status}` : '/api/v1/feedback/admin';
  return api(url, { token });
}

export async function updateFeedbackStatus(token: string, feedbackId: string, status: string): Promise<AdminFeedback> {
  return api(`/api/v1/feedback/admin/${feedbackId}`, { method: 'PATCH', body: { status }, token });
}

// --- StashAI ---

export interface StashLink {
  id: string;
  user_id: string;
  url: string;
  title: string | null;
  description: string | null;
  thumbnail_url: string | null;
  tags: string[];
  status: 'unread' | 'read' | 'archived';
  notes: string | null;
  summary: string | null;
  ai_title: string | null;
  ai_tags: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface AiModelOption {
  id: string;
  label: string;
}

export interface AiProvidersResponse {
  providers: Record<string, AiModelOption[]>;
}

export async function getAiModels(token: string): Promise<AiProvidersResponse> {
  return api('/api/v1/stash/ai-models', { token });
}

export interface StashLinkListResponse {
  links: StashLink[];
  total: number;
}

export interface UrlMetadata {
  url: string;
  title: string | null;
  description: string | null;
  thumbnail_url: string | null;
}

export async function fetchUrlMetadata(token: string, url: string): Promise<UrlMetadata> {
  return api(`/api/v1/stash/fetch-metadata?url=${encodeURIComponent(url)}`, { token });
}

export async function createStashLink(
  token: string,
  data: { url: string; title?: string; description?: string; tags?: string[]; notes?: string }
): Promise<StashLink> {
  return api('/api/v1/stash', { method: 'POST', body: data, token });
}

export async function listStashLinks(
  token: string,
  params?: { status?: string; tag?: string; q?: string; limit?: number; offset?: number }
): Promise<StashLinkListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.tag) qs.set('tag', params.tag);
  if (params?.q) qs.set('q', params.q);
  if (params?.limit) qs.set('limit', String(params.limit));
  if (params?.offset) qs.set('offset', String(params.offset));
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return api(`/api/v1/stash${query}`, { token });
}

export async function updateStashLink(
  token: string,
  linkId: string,
  data: { title?: string; description?: string; tags?: string[]; status?: string; notes?: string }
): Promise<StashLink> {
  return api(`/api/v1/stash/${linkId}`, { method: 'PATCH', body: data, token });
}

export async function deleteStashLink(token: string, linkId: string): Promise<void> {
  return api(`/api/v1/stash/${linkId}`, { method: 'DELETE', token });
}
