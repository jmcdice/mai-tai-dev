'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDownIcon, ChevronRightIcon, ArrowTopRightOnSquareIcon, TrashIcon, ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline';
import { useToast } from '@/hooks/use-toast';
import { useNotificationSound } from '@/hooks/use-notification-sound';
import Button from '@/components/Common/Button';
import Modal from '@/components/Common/Modal';
import {
  updateWorkspace,
  archiveWorkspace,
  unarchiveWorkspace,
  deleteWorkspace,
  startAgent,
  stopAgent,
  getAgentContainerStatus,
  Workspace,
} from '@/lib/api';
import { events, WORKSPACE_UPDATED } from '@/lib/events';

interface WorkspaceSettingsProps {
  workspaceId: string;
  token: string | null;
  workspace: Workspace | null;
  onWorkspaceUpdate: (workspace: Workspace) => void;
}

export default function WorkspaceSettings({
  workspaceId,
  token,
  workspace,
  onWorkspaceUpdate,
}: WorkspaceSettingsProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [showMcpConfig, setShowMcpConfig] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showProjectContextModal, setShowProjectContextModal] = useState(false);
  const [projectContext, setProjectContext] = useState('');
  const { enabled: soundEnabled, setEnabled: setSoundEnabled } = useNotificationSound();

  // Agent container state
  const [agentRunning, setAgentRunning] = useState<boolean | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const isAgentWorkspace = workspace?.workspace_type === 'agent';

  const fetchAgentStatus = useCallback(async () => {
    if (!token || !isAgentWorkspace) return;
    try {
      const status = await getAgentContainerStatus(token, workspaceId);
      setAgentRunning(status.running);
    } catch {
      setAgentRunning(null);
    }
  }, [token, workspaceId, isAgentWorkspace]);

  useEffect(() => {
    fetchAgentStatus();
  }, [fetchAgentStatus]);

  const handleStartAgent = async () => {
    if (!token) return;
    setAgentLoading(true);
    try {
      const result = await startAgent(token, workspaceId);
      if (result.status === 'started' || result.status === 'already_running') {
        setAgentRunning(true);
        toast({ title: 'Agent started' });
      } else {
        toast({ variant: 'destructive', title: result.message || 'Failed to start agent' });
      }
    } catch {
      toast({ variant: 'destructive', title: 'Failed to start agent' });
    } finally {
      setAgentLoading(false);
    }
  };

  const handleStopAgent = async () => {
    if (!token) return;
    setAgentLoading(true);
    try {
      await stopAgent(token, workspaceId);
      setAgentRunning(false);
      toast({ title: 'Agent stopped' });
    } catch {
      toast({ variant: 'destructive', title: 'Failed to stop agent' });
    } finally {
      setAgentLoading(false);
    }
  };

  // Dude Mode state from workspace settings (defaults to OFF)
  const dudeMode = (workspace?.settings?.dude_mode as boolean) ?? false;

  // Simple command to link this workspace to a project
  const projectConfigCommand = `echo "MAI_TAI_WORKSPACE_ID=${workspaceId}" > .env.mai-tai`;

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText(projectConfigCommand);
      setCopied(true);
      toast({ title: 'Copied to clipboard!' });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ variant: 'destructive', title: 'Failed to copy' });
    }
  };

  const handleToggleDudeMode = async () => {
    if (!token || !workspace) return;
    try {
      const newSettings = { ...workspace.settings, dude_mode: !dudeMode };
      const updated = await updateWorkspace(token, workspaceId, { settings: newSettings });
      onWorkspaceUpdate(updated);
      toast({ title: !dudeMode ? 'Dude Mode enabled 🍹' : 'Dude Mode disabled' });
    } catch {
      toast({ variant: 'destructive', title: 'Failed to update Dude Mode' });
    }
  };

  const handleToggleArchive = async () => {
    if (!token || !workspace) return;
    try {
      const updated = workspace.archived
        ? await unarchiveWorkspace(token, workspaceId)
        : await archiveWorkspace(token, workspaceId);
      onWorkspaceUpdate(updated);
      toast({ title: updated.archived ? 'Workspace archived' : 'Workspace unarchived' });
    } catch {
      toast({ variant: 'destructive', title: 'Failed to update workspace' });
    }
  };

  const handleRenameWorkspace = async () => {
    if (!token || !workspace || !newWorkspaceName.trim()) return;
    try {
      const updated = await updateWorkspace(token, workspaceId, { name: newWorkspaceName.trim() });
      onWorkspaceUpdate(updated);
      setShowRenameModal(false);
      setNewWorkspaceName('');
      toast({ title: 'Workspace renamed' });
      // Notify sidebar to refresh
      events.emit(WORKSPACE_UPDATED);
    } catch {
      toast({ variant: 'destructive', title: 'Failed to rename workspace' });
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!token || !workspace) return;
    if (deleteConfirmText !== workspace.name) return;

    setIsDeleting(true);
    try {
      await deleteWorkspace(token, workspaceId);
      toast({ title: 'Workspace deleted' });
      // Notify sidebar to refresh and redirect to workspaces list
      events.emit(WORKSPACE_UPDATED);
      router.push('/workspaces');
    } catch {
      toast({ variant: 'destructive', title: 'Failed to delete workspace' });
      setIsDeleting(false);
    }
  };

  const handleExportChat = () => {
    // Open print-friendly view in new tab
    window.open(`/workspaces/${workspaceId}/print`, '_blank');
  };

  const handleSaveProjectContext = async () => {
    if (!token || !workspace) return;
    try {
      const newSettings = { ...workspace.settings, project_context: projectContext.trim() };
      const updated = await updateWorkspace(token, workspaceId, { settings: newSettings });
      onWorkspaceUpdate(updated);
      setShowProjectContextModal(false);
      toast({ title: 'Project context saved' });
    } catch {
      toast({ variant: 'destructive', title: 'Failed to save project context' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Agent Container Section - only for agent workspaces */}
      {isAgentWorkspace && (
        <>
          <div>
            <h3 className="mb-2 text-base font-semibold text-white">Agent Container</h3>
            <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
              <div className="flex items-center gap-3">
                <span
                  className={`h-3 w-3 rounded-full ${
                    agentRunning === null
                      ? 'bg-gray-500'
                      : agentRunning
                      ? 'bg-green-500 animate-pulse'
                      : 'bg-red-500'
                  }`}
                />
                <div>
                  <p className="font-medium text-white">
                    {agentRunning === null
                      ? 'Checking...'
                      : agentRunning
                      ? 'Running'
                      : 'Stopped'}
                  </p>
                  <p className="text-sm text-gray-400">
                    {agentRunning
                      ? 'Agent is active and connected'
                      : 'Agent container is not running'}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                {agentRunning ? (
                  <Button
                    buttonType="danger"
                    buttonSize="sm"
                    onClick={handleStopAgent}
                    disabled={agentLoading}
                  >
                    {agentLoading ? 'Stopping...' : 'Stop'}
                  </Button>
                ) : (
                  <Button
                    buttonType="primary"
                    buttonSize="sm"
                    onClick={handleStartAgent}
                    disabled={agentLoading}
                  >
                    {agentLoading ? 'Starting...' : 'Start'}
                  </Button>
                )}
              </div>
            </div>
          </div>
          <div className="border-t border-gray-700" />
        </>
      )}

      {/* Notifications Section */}
      <div>
        <h3 className="mb-2 text-base font-semibold text-white">Notifications</h3>
        <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
          <div>
            <p className="font-medium text-white">Sound notifications</p>
            <p className="text-sm text-gray-400">Play a sound when new messages arrive</p>
          </div>
          <Button
            buttonType={soundEnabled ? 'primary' : 'ghost'}
            buttonSize="sm"
            onClick={() => setSoundEnabled(!soundEnabled)}
          >
            {soundEnabled ? 'On' : 'Off'}
          </Button>
        </div>
      </div>

      <div className="border-t border-gray-700" />

      {/* Dude Mode Section */}
      <div>
        <h3 className="mb-2 text-base font-semibold text-white">Agent Personality</h3>
        <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
          <div>
            <p className="font-medium text-white">Dude Mode</p>
            <p className="text-sm text-gray-400">Agent responds in the style of The Dude, man.</p>
          </div>
          <Button
            buttonType={dudeMode ? 'primary' : 'ghost'}
            buttonSize="sm"
            onClick={handleToggleDudeMode}
          >
            {dudeMode ? 'On' : 'Off'}
          </Button>
        </div>
      </div>

      <div className="border-t border-gray-700" />

      {/* Connect Project (Collapsible) */}
      <div>
        <button
          onClick={() => setShowMcpConfig(!showMcpConfig)}
          className="flex items-center justify-between w-full text-left mb-2"
        >
          <h3 className="text-base font-semibold text-white">Connect a Project</h3>
          {showMcpConfig ? (
            <ChevronDownIcon className="h-5 w-5 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-5 w-5 text-gray-400" />
          )}
        </button>
        {showMcpConfig && (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">
              Run this command in your project directory to link it to this workspace:
            </p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-lg border border-gray-700 bg-gray-900 p-4 pr-12 font-mono text-sm text-gray-100">
                <code>{projectConfigCommand}</code>
              </pre>
              <Button
                buttonType={copied ? 'success' : 'ghost'}
                buttonSize="sm"
                className="absolute right-2 top-2"
                onClick={copyCommand}
              >
                {copied ? (
                  <CheckIcon className="h-4 w-4" />
                ) : (
                  <ClipboardDocumentIcon className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-sm text-gray-500">
              Then start your AI agent and say <code className="rounded bg-gray-800 px-1.5 py-0.5 text-indigo-400">start mai tai mode</code>
            </p>
          </div>
        )}
      </div>

      <div className="border-t border-gray-700" />

      {/* Workspace Settings */}
      <div>
        <h3 className="mb-2 text-base font-semibold text-white">Workspace</h3>
        <div className="space-y-2">
          {/* Export Chat */}
          <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
            <div>
              <p className="font-medium text-white">Export Chat</p>
              <p className="text-sm text-gray-400">Open print-friendly view to save as PDF</p>
            </div>
            <Button
              buttonType="primary"
              buttonSize="sm"
              onClick={handleExportChat}
            >
              <ArrowTopRightOnSquareIcon className="mr-1.5 h-4 w-4" />
              Export
            </Button>
          </div>

          {/* Rename Workspace */}
          <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
            <div>
              <p className="font-medium text-white">Rename Workspace</p>
              <p className="text-sm text-gray-400">Change the name of this workspace</p>
            </div>
            <Button
              buttonType="ghost"
              buttonSize="sm"
              onClick={() => {
                setNewWorkspaceName(workspace?.name || '');
                setShowRenameModal(true);
              }}
            >
              Rename
            </Button>
          </div>

          {/* Project Context */}
          <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
            <div>
              <p className="font-medium text-white">Project Context</p>
              <p className="text-sm text-gray-400">Add notes the AI agent should always know</p>
            </div>
            <Button
              buttonType={(workspace?.settings?.project_context as string) ? 'primary' : 'ghost'}
              buttonSize="sm"
              onClick={() => {
                setProjectContext((workspace?.settings?.project_context as string) || '');
                setShowProjectContextModal(true);
              }}
            >
              {(workspace?.settings?.project_context as string) ? 'Edit' : 'Add'}
            </Button>
          </div>

          {/* Archive Workspace */}
          <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 p-3">
            <div>
              <p className="font-medium text-white">
                {workspace?.archived ? 'Unarchive Workspace' : 'Archive Workspace'}
              </p>
              <p className="text-sm text-gray-400">
                {workspace?.archived
                  ? 'Restore this workspace to active status'
                  : 'Hide this workspace from the main list'}
              </p>
            </div>
            <Button
              buttonType={workspace?.archived ? 'primary' : 'ghost'}
              buttonSize="sm"
              onClick={handleToggleArchive}
            >
              {workspace?.archived ? 'Unarchive' : 'Archive'}
            </Button>
          </div>

          {/* Delete Workspace */}
          <div className="flex items-center justify-between rounded-lg border border-red-900/50 bg-red-950/30 p-3">
            <div>
              <p className="font-medium text-red-400">Delete Workspace</p>
              <p className="text-sm text-gray-400">
                Permanently delete this workspace and all its data
              </p>
            </div>
            <Button
              buttonType="danger"
              buttonSize="sm"
              onClick={() => setShowDeleteModal(true)}
            >
              <TrashIcon className="mr-1.5 h-4 w-4" />
              Delete
            </Button>
          </div>
        </div>
      </div>

      {/* Rename Workspace Modal */}
      <Modal
        open={showRenameModal}
        onClose={() => setShowRenameModal(false)}
        title="Rename Workspace"
        size="sm"
      >
        <div className="space-y-4 py-2">
          <input
            type="text"
            placeholder="Workspace name"
            value={newWorkspaceName}
            onChange={(e) => setNewWorkspaceName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleRenameWorkspace()}
            autoFocus
            className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <div className="flex justify-end gap-2">
            <Button buttonType="ghost" onClick={() => setShowRenameModal(false)}>
              Cancel
            </Button>
            <Button buttonType="primary" onClick={handleRenameWorkspace}>
              Save
            </Button>
          </div>
        </div>
      </Modal>

      {/* Project Context Modal */}
      <Modal
        open={showProjectContextModal}
        onClose={() => setShowProjectContextModal(false)}
        title="Project Context"
        size="sm"
      >
        <div className="space-y-4 py-2">
          <p className="text-sm text-gray-400">
            Add notes about this project that the AI agent should always keep in mind.
          </p>
          <div className="relative">
            <textarea
              placeholder={'e.g., "Use dev.sh for deployments. Python 3.11, FastAPI backend. Always run tests before committing."'}
              value={projectContext}
              onChange={(e) => setProjectContext(e.target.value.slice(0, 500))}
              autoFocus
              rows={4}
              className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
            />
            <span className="absolute bottom-2 right-2 text-xs text-gray-500">
              {projectContext.length}/500
            </span>
          </div>
          <div className="flex justify-end gap-2">
            <Button buttonType="ghost" onClick={() => setShowProjectContextModal(false)}>
              Cancel
            </Button>
            <Button buttonType="primary" onClick={handleSaveProjectContext}>
              Save
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Workspace Modal */}
      <Modal
        open={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setDeleteConfirmText('');
        }}
        title="Delete Workspace"
        size="sm"
      >
        <div className="space-y-4 py-2">
          <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-3">
            <p className="text-sm text-red-400">
              This action cannot be undone. This will permanently delete the workspace
              <strong className="text-white"> {workspace?.name}</strong> and all its messages,
              API keys, and settings.
            </p>
          </div>
          <div>
            <label className="mb-2 block text-sm text-gray-400">
              Type <strong className="text-white">{workspace?.name}</strong> to confirm:
            </label>
            <input
              type="text"
              placeholder={workspace?.name}
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && deleteConfirmText === workspace?.name && handleDeleteWorkspace()}
              autoFocus
              className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              buttonType="ghost"
              onClick={() => {
                setShowDeleteModal(false);
                setDeleteConfirmText('');
              }}
            >
              Cancel
            </Button>
            <Button
              buttonType="danger"
              onClick={handleDeleteWorkspace}
              disabled={deleteConfirmText !== workspace?.name || isDeleting}
            >
              {isDeleting ? 'Deleting...' : 'Delete Workspace'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

