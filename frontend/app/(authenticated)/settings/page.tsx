'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getMe, updateMe, changePassword, getUserApiKeys, createUserApiKey, deleteUserApiKey, regenerateUserApiKey, getAiModels, ApiError, UserSettings, UserShortcut, ApiKey, AiModelOption } from '@/lib/api';
import { CheckCircleIcon, XCircleIcon, UserCircleIcon, KeyIcon, Cog6ToothIcon, PlusIcon, PencilIcon, TrashIcon, BoltIcon, ClipboardDocumentIcon, EyeIcon, EyeSlashIcon, ArrowPathIcon, SparklesIcon } from '@heroicons/react/24/solid';
import { defaultShortcuts, MAX_SHORTCUTS, MAX_LABEL_LENGTH, MAX_TEXT_LENGTH } from '@/lib/chat-shortcuts';
import { events, USER_UPDATED } from '@/lib/events';

// Common timezones for the dropdown
const COMMON_TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Dubai',
  'Australia/Sydney',
  'Pacific/Auckland',
];

type Tab = 'profile' | 'password' | 'preferences' | 'shortcuts' | 'api-keys' | 'ai';

const tabs: { id: Tab; name: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'profile', name: 'Profile', icon: UserCircleIcon },
  { id: 'password', name: 'Password', icon: KeyIcon },
  { id: 'preferences', name: 'Preferences', icon: Cog6ToothIcon },
  { id: 'shortcuts', name: 'Shortcuts', icon: BoltIcon },
  { id: 'api-keys', name: 'API Keys', icon: KeyIcon },
  { id: 'ai', name: 'AI', icon: SparklesIcon },
];

export default function SettingsPage() {
  const { token, refreshUser } = useAuth();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab>(tabParam && ['profile', 'password', 'preferences', 'shortcuts', 'api-keys', 'ai'].includes(tabParam) ? tabParam : 'profile');
  const [name, setName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [email, setEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isPasswordLoading, setIsPasswordLoading] = useState(false);
  const [isPreferencesLoading, setIsPreferencesLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [preferencesMessage, setPreferencesMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [timezone, setTimezone] = useState<string>('');
  const [timeFormat, setTimeFormat] = useState<'12h' | '24h'>('12h');
  const [shortcuts, setShortcuts] = useState<UserShortcut[]>([]);
  const [editingShortcut, setEditingShortcut] = useState<UserShortcut | null>(null);
  const [isAddingShortcut, setIsAddingShortcut] = useState(false);
  const [newShortcutLabel, setNewShortcutLabel] = useState('');
  const [newShortcutText, setNewShortcutText] = useState('');

  // API Keys state
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [isApiKeysLoading, setIsApiKeysLoading] = useState(false);
  const [apiKeysMessage, setApiKeysMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [newApiKeyName, setNewApiKeyName] = useState('');
  const [isCreatingApiKey, setIsCreatingApiKey] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);

  // AI settings state
  const [aiProvider, setAiProvider] = useState('');
  const [aiModel, setAiModel] = useState('');
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiOllamaBaseUrl, setAiOllamaBaseUrl] = useState('http://localhost:11434');
  const [showAiApiKey, setShowAiApiKey] = useState(false);
  const [aiProviderModels, setAiProviderModels] = useState<Record<string, AiModelOption[]>>({});
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [aiMessage, setAiMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (token) {
      getMe(token).then((user) => {
        setName(user.name);
        setEmail(user.email);
        setAvatarUrl(user.avatar_url || '');
        setTimezone(user.settings?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone);
        setTimeFormat(user.settings?.time_format || '12h');
        setShortcuts(user.settings?.shortcuts || []);
        // AI settings
        setAiProvider(user.settings?.stash_llm_provider || '');
        setAiModel(user.settings?.stash_llm_model || '');
        setAiApiKey(user.settings?.stash_llm_api_key || '');
        setAiOllamaBaseUrl(user.settings?.stash_ollama_base_url || 'http://localhost:11434');
      });
    }
  }, [token]);

  // Load API keys when tab is active
  useEffect(() => {
    if (token && activeTab === 'api-keys') {
      setIsApiKeysLoading(true);
      getUserApiKeys(token)
        .then((res) => setApiKeys(res.api_keys))
        .catch(() => setApiKeysMessage({ type: 'error', text: 'Failed to load API keys' }))
        .finally(() => setIsApiKeysLoading(false));
    }
  }, [token, activeTab]);

  // Load AI models when tab is active
  useEffect(() => {
    if (token && activeTab === 'ai') {
      getAiModels(token)
        .then((res) => setAiProviderModels(res.providers))
        .catch(() => setAiMessage({ type: 'error', text: 'Failed to load AI models' }));
    }
  }, [token, activeTab]);

  const handleAiSave = async () => {
    if (!token) return;
    setIsAiLoading(true);
    setAiMessage(null);
    try {
      await updateMe(token, {
        settings: {
          timezone,
          time_format: timeFormat,
          shortcuts: shortcuts.length > 0 ? shortcuts : null,
          stash_llm_provider: aiProvider || null,
          stash_llm_model: aiModel || null,
          stash_llm_api_key: aiApiKey || null,
          stash_ollama_base_url: aiProvider === 'ollama' ? aiOllamaBaseUrl : null,
        },
      });
      await refreshUser();
      setAiMessage({ type: 'success', text: 'AI settings saved!' });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save AI settings';
      setAiMessage({ type: 'error', text: msg });
    } finally {
      setIsAiLoading(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!token || !newApiKeyName.trim()) return;
    setIsCreatingApiKey(true);
    setApiKeysMessage(null);
    try {
      const newKey = await createUserApiKey(token, newApiKeyName.trim());
      setApiKeys([...apiKeys, newKey]);
      setNewlyCreatedKey(newKey.key || null);
      setNewApiKeyName('');
      setApiKeysMessage({ type: 'success', text: 'API key created! Copy it now - it won\'t be shown again.' });
    } catch (err) {
      setApiKeysMessage({ type: 'error', text: err instanceof ApiError ? err.message : 'Failed to create API key' });
    } finally {
      setIsCreatingApiKey(false);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    if (!token) return;
    if (!confirm('Are you sure you want to delete this API key? This cannot be undone.')) return;
    try {
      await deleteUserApiKey(token, keyId);
      setApiKeys(apiKeys.filter((k) => k.id !== keyId));
      setApiKeysMessage({ type: 'success', text: 'API key deleted' });
    } catch (err) {
      setApiKeysMessage({ type: 'error', text: err instanceof ApiError ? err.message : 'Failed to delete API key' });
    }
  };

  const handleRegenerateApiKey = async (keyId: string, keyName: string) => {
    if (!token) return;
    if (!confirm(`Regenerate "${keyName}"? The old key will stop working immediately.`)) return;
    try {
      const newKey = await regenerateUserApiKey(token, keyId);
      setNewlyCreatedKey(newKey.key || null);
      setApiKeysMessage({ type: 'success', text: 'API key regenerated! Copy it now - it won\'t be shown again.' });
    } catch (err) {
      setApiKeysMessage({ type: 'error', text: err instanceof ApiError ? err.message : 'Failed to regenerate API key' });
    }
  };

  const copyToClipboard = async (text: string, keyId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKeyId(keyId);
      setTimeout(() => setCopiedKeyId(null), 2000);
    } catch {
      // Fallback
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedKeyId(keyId);
      setTimeout(() => setCopiedKeyId(null), 2000);
    }
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setIsLoading(true);
    setMessage(null);

    try {
      await updateMe(token, { name, avatar_url: avatarUrl || undefined });
      setMessage({ type: 'success', text: 'Profile updated successfully!' });
      // Notify components that user profile changed (e.g., chat page avatar)
      events.emit(USER_UPDATED);
      // Also refresh the auth context user
      refreshUser();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to update profile';
      setMessage({ type: 'error', text: msg });
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: 'error', text: 'New passwords do not match' });
      return;
    }

    if (newPassword.length < 6) {
      setPasswordMessage({ type: 'error', text: 'Password must be at least 6 characters' });
      return;
    }

    setIsPasswordLoading(true);
    setPasswordMessage(null);

    try {
      await changePassword(token, currentPassword, newPassword);
      setPasswordMessage({ type: 'success', text: 'Password changed successfully!' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to change password';
      setPasswordMessage({ type: 'error', text: msg });
    } finally {
      setIsPasswordLoading(false);
    }
  };

  const handlePreferencesSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setIsPreferencesLoading(true);
    setPreferencesMessage(null);

    try {
      await updateMe(token, {
        settings: {
          timezone,
          time_format: timeFormat,
          shortcuts: shortcuts.length > 0 ? shortcuts : null,
        },
      });
      await refreshUser();
      setPreferencesMessage({ type: 'success', text: 'Preferences saved!' });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save preferences';
      setPreferencesMessage({ type: 'error', text: msg });
    } finally {
      setIsPreferencesLoading(false);
    }
  };

  const saveShortcuts = async (newShortcuts: UserShortcut[]) => {
    if (!token) return;
    setIsPreferencesLoading(true);
    setPreferencesMessage(null);
    try {
      await updateMe(token, {
        settings: {
          timezone,
          time_format: timeFormat,
          shortcuts: newShortcuts.length > 0 ? newShortcuts : null,
        },
      });
      await refreshUser();
      setPreferencesMessage({ type: 'success', text: 'Shortcuts saved!' });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save shortcuts';
      setPreferencesMessage({ type: 'error', text: msg });
    } finally {
      setIsPreferencesLoading(false);
    }
  };

  const handleAddShortcut = async () => {
    if (!newShortcutLabel.trim() || !newShortcutText.trim()) return;

    // If user has no custom shortcuts, copy defaults first
    let baseShortcuts = shortcuts;
    if (shortcuts.length === 0) {
      baseShortcuts = defaultShortcuts.map((s) => ({
        ...s,
        id: crypto.randomUUID(),
      }));
    }

    if (baseShortcuts.length >= MAX_SHORTCUTS) return;

    const newShortcut: UserShortcut = {
      id: crypto.randomUUID(),
      label: newShortcutLabel.slice(0, MAX_LABEL_LENGTH),
      text: newShortcutText.slice(0, MAX_TEXT_LENGTH),
    };

    const newShortcuts = [...baseShortcuts, newShortcut];
    setShortcuts(newShortcuts);
    setNewShortcutLabel('');
    setNewShortcutText('');
    setIsAddingShortcut(false);
    await saveShortcuts(newShortcuts);
  };

  const handleDeleteShortcut = async (id: string) => {
    const newShortcuts = shortcuts.filter((s) => s.id !== id);
    setShortcuts(newShortcuts);
    await saveShortcuts(newShortcuts);
  };

  const handleEditShortcut = (shortcut: UserShortcut) => {
    setEditingShortcut(shortcut);
    setNewShortcutLabel(shortcut.label);
    setNewShortcutText(shortcut.text);
  };

  const handleSaveEdit = async () => {
    if (!editingShortcut || !newShortcutLabel.trim() || !newShortcutText.trim()) return;

    const newShortcuts = shortcuts.map((s) =>
      s.id === editingShortcut.id
        ? { ...s, label: newShortcutLabel.slice(0, MAX_LABEL_LENGTH), text: newShortcutText.slice(0, MAX_TEXT_LENGTH) }
        : s
    );
    setShortcuts(newShortcuts);
    setEditingShortcut(null);
    setNewShortcutLabel('');
    setNewShortcutText('');
    await saveShortcuts(newShortcuts);
  };

  const handleCancelEdit = () => {
    setEditingShortcut(null);
    setIsAddingShortcut(false);
    setNewShortcutLabel('');
    setNewShortcutText('');
  };

  // Get display shortcuts (user's or defaults)
  const displayShortcuts = shortcuts.length > 0 ? shortcuts : defaultShortcuts;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-gradient text-3xl font-bold">Settings</h1>
        <p className="mt-2 text-gray-400">Manage your profile and account settings.</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        {/* Mobile dropdown */}
        <div className="sm:hidden">
          <select
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value as Tab)}
            className="w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white"
          >
            {tabs.map((tab) => (
              <option key={tab.id} value={tab.id}>{tab.name}</option>
            ))}
          </select>
        </div>
        {/* Desktop tabs */}
        <nav className="hidden sm:flex sm:space-x-8" aria-label="Tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 border-b-2 px-1 py-4 text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-indigo-500 text-indigo-400'
                    : 'border-transparent text-gray-400 hover:border-gray-500 hover:text-gray-300'
                }`}
              >
                <Icon className="h-5 w-5" />
                {tab.name}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <h2 className="mb-4 text-xl font-semibold text-white">Profile</h2>

          {message && (
            <div className={`mb-4 flex max-w-lg items-center gap-2 rounded-lg p-3 ${message.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {message.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {message.text}
            </div>
          )}

          <form onSubmit={handleProfileSubmit} className="max-w-lg space-y-4">
            {/* Avatar Preview */}
            <div className="flex items-center gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-gray-600 bg-gray-700">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="Avatar" className="h-full w-full object-cover" />
                ) : (
                  <span className="text-2xl font-bold text-gray-400">{name.charAt(0).toUpperCase()}</span>
                )}
              </div>
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-300">Avatar URL</label>
                <input
                  type="url"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="https://github.com/username.png"
                  className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300">Email</label>
              <input
                type="email"
                value={email}
                disabled
                className="mt-1 w-full cursor-not-allowed rounded-lg border border-gray-600 bg-gray-600 px-4 py-2 text-gray-400"
              />
              <p className="mt-1 text-xs text-gray-500">Email cannot be changed</p>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : 'Save Profile'}
            </button>
          </form>
        </div>
      )}

      {/* Password Tab */}
      {activeTab === 'password' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <h2 className="mb-4 text-xl font-semibold text-white">Change Password</h2>

          {passwordMessage && (
            <div className={`mb-4 flex max-w-lg items-center gap-2 rounded-lg p-3 ${passwordMessage.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {passwordMessage.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {passwordMessage.text}
            </div>
          )}

          <form onSubmit={handlePasswordSubmit} className="max-w-lg space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300">Current Password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300">Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={isPasswordLoading}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isPasswordLoading ? 'Changing...' : 'Change Password'}
            </button>
          </form>
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <h2 className="mb-4 text-xl font-semibold text-white">Preferences</h2>

          {preferencesMessage && (
            <div className={`mb-4 flex max-w-lg items-center gap-2 rounded-lg p-3 ${preferencesMessage.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {preferencesMessage.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {preferencesMessage.text}
            </div>
          )}

          <form onSubmit={handlePreferencesSubmit} className="max-w-lg space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300">Timezone</label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              >
                {COMMON_TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>{tz.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500">Used for displaying timestamps</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300">Time Format</label>
              <div className="mt-2 flex gap-4">
                <label className="flex items-center gap-2 text-gray-300">
                  <input
                    type="radio"
                    name="timeFormat"
                    value="12h"
                    checked={timeFormat === '12h'}
                    onChange={() => setTimeFormat('12h')}
                    className="h-4 w-4 border-gray-600 bg-gray-700 text-indigo-600 focus:ring-indigo-500"
                  />
                  12-hour (3:30 PM)
                </label>
                <label className="flex items-center gap-2 text-gray-300">
                  <input
                    type="radio"
                    name="timeFormat"
                    value="24h"
                    checked={timeFormat === '24h'}
                    onChange={() => setTimeFormat('24h')}
                    className="h-4 w-4 border-gray-600 bg-gray-700 text-indigo-600 focus:ring-indigo-500"
                  />
                  24-hour (15:30)
                </label>
              </div>
            </div>

            <button
              type="submit"
              disabled={isPreferencesLoading}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isPreferencesLoading ? 'Saving...' : 'Save Preferences'}
            </button>
          </form>
        </div>
      )}

      {/* Shortcuts Tab */}
      {activeTab === 'shortcuts' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">Quick Shortcuts</h2>
              <p className="mt-1 text-gray-400">Customize the shortcuts shown in the Quick menu on mobile</p>
            </div>
            {!isAddingShortcut && !editingShortcut && displayShortcuts.length < MAX_SHORTCUTS && (
              <button
                type="button"
                onClick={() => setIsAddingShortcut(true)}
                className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
              >
                <PlusIcon className="h-4 w-4" />
                Add Shortcut
              </button>
            )}
          </div>

          {/* Add/Edit Form */}
          {(isAddingShortcut || editingShortcut) && (
            <div className="mt-6 rounded-lg border border-gray-600 bg-gray-700/50 p-4">
              <h3 className="mb-4 font-medium text-white">
                {editingShortcut ? 'Edit Shortcut' : 'New Shortcut'}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300">Label</label>
                  <p className="mb-1 text-xs text-gray-500">Short name shown in the Quick menu</p>
                  <input
                    type="text"
                    value={newShortcutLabel}
                    onChange={(e) => setNewShortcutLabel(e.target.value)}
                    maxLength={MAX_LABEL_LENGTH}
                    placeholder="e.g., Deploy to prod"
                    className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-gray-500">{newShortcutLabel.length}/{MAX_LABEL_LENGTH}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300">Message Text</label>
                  <p className="mb-1 text-xs text-gray-500">The full message that will be sent to the chat</p>
                  <textarea
                    value={newShortcutText}
                    onChange={(e) => setNewShortcutText(e.target.value)}
                    maxLength={MAX_TEXT_LENGTH}
                    rows={4}
                    placeholder="e.g., Please deploy the current changes to production and let me know when it's done..."
                    className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-gray-500">{newShortcutText.length}/{MAX_TEXT_LENGTH}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={editingShortcut ? handleSaveEdit : handleAddShortcut}
                    disabled={!newShortcutLabel.trim() || !newShortcutText.trim()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {editingShortcut ? 'Save Changes' : 'Add Shortcut'}
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelEdit}
                    className="rounded-lg bg-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition hover:bg-gray-500"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Shortcuts List */}
          <div className="mt-6 space-y-3">
            {displayShortcuts.map((shortcut, index) => {
              const isDefault = shortcuts.length === 0;
              return (
                <div
                  key={shortcut.id}
                  className="flex items-start justify-between rounded-lg border border-gray-700 bg-gray-800 p-4"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-700 text-xs font-medium text-gray-400">
                        {index + 1}
                      </span>
                      <p className="font-medium text-white">{shortcut.label}</p>
                      {isDefault && (
                        <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">Default</span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-gray-400">{shortcut.text}</p>
                  </div>
                  <div className="ml-4 flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (isDefault) {
                          // Copy ALL defaults to user shortcuts, then edit the selected one
                          const copiedDefaults = defaultShortcuts.map((s) => ({
                            ...s,
                            id: crypto.randomUUID(),
                          }));
                          setShortcuts(copiedDefaults);
                          // Find the copied version of the shortcut we want to edit
                          const copiedShortcut = copiedDefaults[index];
                          handleEditShortcut(copiedShortcut);
                        } else {
                          handleEditShortcut(shortcut);
                        }
                      }}
                      className="rounded p-1.5 text-gray-400 transition hover:bg-gray-700 hover:text-white"
                      title="Edit"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    {!isDefault && (
                      <button
                        type="button"
                        onClick={() => handleDeleteShortcut(shortcut.id)}
                        className="rounded p-1.5 text-gray-400 transition hover:bg-gray-700 hover:text-red-400"
                        title="Delete"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Info text */}
          {shortcuts.length === 0 && (
            <p className="mt-4 text-center text-sm text-gray-500">
              These are the default shortcuts. Click edit to customize them.
            </p>
          )}

          {/* Status message */}
          {preferencesMessage && (
            <div className={`mt-4 flex items-center gap-2 rounded-lg p-3 ${preferencesMessage.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {preferencesMessage.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {preferencesMessage.text}
            </div>
          )}

          {/* Loading indicator */}
          {isPreferencesLoading && (
            <p className="mt-4 text-center text-sm text-gray-400">Saving...</p>
          )}
        </div>
      )}

      {/* API Keys Tab */}
      {activeTab === 'api-keys' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-white">API Keys</h2>
            <p className="mt-1 text-gray-400">
              Manage your API keys for connecting AI agents to Mai-Tai.
              Your API key works for all your workspaces.
            </p>
          </div>

          {apiKeysMessage && (
            <div className={`mb-4 flex items-center gap-2 rounded-lg p-3 ${apiKeysMessage.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {apiKeysMessage.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {apiKeysMessage.text}
            </div>
          )}

          {/* Newly created key - show prominently */}
          {newlyCreatedKey && (
            <div className="mb-6 rounded-lg border border-green-500/30 bg-green-500/10 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-green-400">🔑 New API Key Created</p>
                  <p className="mt-1 text-sm text-gray-400">Copy this now - it won&apos;t be shown again!</p>
                </div>
                <button
                  onClick={() => setNewlyCreatedKey(null)}
                  className="text-gray-400 hover:text-white"
                >
                  <XCircleIcon className="h-5 w-5" />
                </button>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <code className="flex-1 rounded bg-gray-900 px-3 py-2 font-mono text-sm text-green-300 break-all">
                  {newlyCreatedKey}
                </code>
                <button
                  onClick={() => copyToClipboard(newlyCreatedKey, 'new')}
                  className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-500"
                >
                  {copiedKeyId === 'new' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}

          {/* Create new key */}
          <div className="mb-6 rounded-lg border border-gray-700 bg-gray-800 p-4">
            <h3 className="mb-3 font-medium text-white">Create New API Key</h3>
            <div className="flex gap-3">
              <input
                type="text"
                value={newApiKeyName}
                onChange={(e) => setNewApiKeyName(e.target.value)}
                placeholder="Key name (e.g., 'My Laptop')"
                className="flex-1 rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
              />
              <button
                onClick={handleCreateApiKey}
                disabled={!newApiKeyName.trim() || isCreatingApiKey}
                className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isCreatingApiKey ? 'Creating...' : 'Create Key'}
              </button>
            </div>
          </div>

          {/* Existing keys */}
          <div className="space-y-3">
            <h3 className="font-medium text-white">Your API Keys</h3>
            {isApiKeysLoading ? (
              <p className="text-gray-400">Loading...</p>
            ) : apiKeys.length === 0 ? (
              <p className="text-gray-400">No API keys yet. Create one above to get started.</p>
            ) : (
              apiKeys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 p-4"
                >
                  <div>
                    <p className="font-medium text-white">{key.name || 'Unnamed Key'}</p>
                    <p className="text-sm text-gray-400">
                      Created {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at && ` • Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleRegenerateApiKey(key.id, key.name || 'Unnamed Key')}
                      className="rounded p-2 text-gray-400 transition hover:bg-gray-700 hover:text-indigo-400"
                      title="Regenerate API key"
                    >
                      <ArrowPathIcon className="h-5 w-5" />
                    </button>
                    <button
                      onClick={() => handleDeleteApiKey(key.id)}
                      className="rounded p-2 text-gray-400 transition hover:bg-gray-700 hover:text-red-400"
                      title="Delete API key"
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Info box */}
          <div className="mt-6 rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-4">
            <h4 className="font-medium text-indigo-300">💡 How to use your API key</h4>
            <p className="mt-2 text-sm text-gray-300">
              Your API key works for all your workspaces. When configuring your AI agent:
            </p>
            <ol className="mt-2 list-inside list-decimal space-y-1 text-sm text-gray-300">
              <li>Add your API key to your global config (~/.config/mai-tai/config)</li>
              <li>Add the workspace ID to each project (.env.mai-tai)</li>
              <li>Configure your AI agent to use the mai-tai MCP server</li>
            </ol>
          </div>
        </div>
      )}

      {/* AI Tab */}
      {activeTab === 'ai' && (
        <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-white">AI Settings</h2>
            <p className="mt-1 text-gray-400">
              Configure an LLM to automatically generate summaries, titles, and tags when you save links to Stash.
            </p>
          </div>

          {aiMessage && (
            <div className={`mb-4 flex items-center gap-2 rounded-lg p-3 ${aiMessage.type === 'success' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'}`}>
              {aiMessage.type === 'success' ? <CheckCircleIcon className="h-5 w-5" /> : <XCircleIcon className="h-5 w-5" />}
              {aiMessage.text}
            </div>
          )}

          <div className="max-w-lg space-y-4">
            {/* Provider */}
            <div>
              <label className="block text-sm font-medium text-gray-300">Provider</label>
              <select
                value={aiProvider}
                onChange={(e) => {
                  setAiProvider(e.target.value);
                  setAiModel(''); // Reset model when provider changes
                }}
                className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
              >
                <option value="">Select a provider...</option>
                {Object.keys(aiProviderModels).map((p) => (
                  <option key={p} value={p}>
                    {p === 'anthropic' ? 'Anthropic' : p === 'openai' ? 'OpenAI' : p === 'google' ? 'Google' : p === 'ollama' ? 'Ollama (Local)' : p}
                  </option>
                ))}
              </select>
            </div>

            {/* Model */}
            {aiProvider && (
              <div>
                <label className="block text-sm font-medium text-gray-300">Model</label>
                <select
                  value={aiModel}
                  onChange={(e) => setAiModel(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Select a model...</option>
                  {(aiProviderModels[aiProvider] || []).map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </div>
            )}

            {/* API Key (not for Ollama) */}
            {aiProvider && aiProvider !== 'ollama' && (
              <div>
                <label className="block text-sm font-medium text-gray-300">API Key</label>
                <div className="relative mt-1">
                  <input
                    type={showAiApiKey ? 'text' : 'password'}
                    value={aiApiKey}
                    onChange={(e) => setAiApiKey(e.target.value)}
                    placeholder={aiProvider === 'anthropic' ? 'sk-ant-...' : aiProvider === 'openai' ? 'sk-...' : 'API key...'}
                    className="w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 pr-10 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAiApiKey(!showAiApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  >
                    {showAiApiKey ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-500">Your key is stored securely and only used for Stash enrichment.</p>
              </div>
            )}

            {/* Ollama base URL */}
            {aiProvider === 'ollama' && (
              <div>
                <label className="block text-sm font-medium text-gray-300">Ollama Base URL</label>
                <input
                  type="url"
                  value={aiOllamaBaseUrl}
                  onChange={(e) => setAiOllamaBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434"
                  className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-white placeholder-gray-400 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={handleAiSave}
                disabled={isAiLoading}
                className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isAiLoading ? 'Saving...' : 'Save AI Settings'}
              </button>
              {aiProvider && (
                <button
                  onClick={() => {
                    setAiProvider('');
                    setAiModel('');
                    setAiApiKey('');
                  }}
                  className="rounded-lg bg-gray-600 px-4 py-2 font-medium text-gray-300 transition hover:bg-gray-500"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Info box */}
          <div className="mt-6 rounded-lg border border-violet-500/30 bg-violet-500/10 p-4">
            <h4 className="font-medium text-violet-300">How it works</h4>
            <p className="mt-2 text-sm text-gray-300">
              When you save a link to Stash, the selected LLM will automatically analyze the page and generate:
            </p>
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-gray-300">
              <li>A clean, human-readable title</li>
              <li>A 1-2 sentence summary</li>
              <li>Relevant tags for easy filtering</li>
            </ul>
            <p className="mt-2 text-sm text-gray-500">
              For cost-effective usage, we recommend Haiku 4.5, GPT-5 Mini, or Gemini 2.5 Flash.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

