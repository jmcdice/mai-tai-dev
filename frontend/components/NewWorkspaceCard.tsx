'use client';

import { useState, useEffect } from 'react';
import { XMarkIcon, ClipboardDocumentIcon, CheckIcon, PlusIcon, BoltIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline';
import { SparklesIcon, KeyIcon } from '@heroicons/react/24/solid';
import { useAuth } from '@/lib/auth';
import { createUserApiKey } from '@/lib/api';
import AgentSetupBlob from '@/components/AgentSetupBlob';

interface NewWorkspaceCardProps {
  workspaceId: string;
  workspaceName: string;
  workspaceType?: string;
  hasMessages?: boolean;
  onDismiss: () => void;
}

type SetupTab = 'quick' | 'full';

// Get the backend URL for config commands
function getBackendUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    return apiUrl;
  }
  return 'https://api.mai-tai.dev';
}

export default function NewWorkspaceCard({ workspaceId, workspaceName, workspaceType, hasMessages = false, onDismiss }: NewWorkspaceCardProps) {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<SetupTab>('quick');
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  // API key generation state
  const [isGeneratingKey, setIsGeneratingKey] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);

  // Auto-dismiss when messages appear (agent is connected and chatting)
  useEffect(() => {
    if (hasMessages) {
      onDismiss();
    }
  }, [hasMessages, onDismiss]);

  const backendUrl = getBackendUrl();
  const projectConfigCommand = `echo "MAI_TAI_WORKSPACE_ID=${workspaceId}" > .env.mai-tai`;

  const copyToClipboard = async (text: string, section: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedSection(section);
      setTimeout(() => setCopiedSection(null), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedSection(section);
      setTimeout(() => setCopiedSection(null), 2000);
    }
  };

  const handleGenerateApiKey = async () => {
    if (!token) return;
    setIsGeneratingKey(true);
    setKeyError(null);
    try {
      const keyName = `${workspaceName} - ${new Date().toLocaleDateString()}`;
      const newKey = await createUserApiKey(token, keyName);
      setGeneratedKey(newKey.key || null);
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : 'Failed to generate API key');
    } finally {
      setIsGeneratingKey(false);
    }
  };

  // Code block component for consistent styling (used in Quick Setup tab)
  const CodeBlock = ({ code, copyId, label }: { code: string; copyId: string; label?: string }) => (
    <div className="rounded-lg border border-gray-700 bg-gray-900/80 p-3">
      {label && (
        <p className="mb-2 text-xs font-medium text-gray-400">{label}</p>
      )}
      <div className="flex items-start justify-between gap-2">
        <pre className="flex-1 overflow-x-auto font-mono text-sm text-green-300 whitespace-pre-wrap break-all">
          <code>{code}</code>
        </pre>
        <button
          onClick={() => copyToClipboard(code, copyId)}
          className="flex-shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-gray-700 hover:text-white"
          title="Copy"
        >
          {copiedSection === copyId ? (
            <CheckIcon className="h-4 w-4 text-green-400" />
          ) : (
            <ClipboardDocumentIcon className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );

  // Agent workspace: show a simple "starting up" message
  if (workspaceType === 'agent') {
    return (
      <div className="mb-6 rounded-xl border border-purple-500/30 bg-gradient-to-r from-purple-500/10 to-indigo-500/10 p-4 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-purple-500/20">
              <SparklesIcon className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">
                {workspaceName} is starting up!
              </h3>
              <p className="mt-1 text-sm text-gray-400">
                Your agent is spinning up and will be right with you. This usually takes a few seconds.
              </p>
              <div className="mt-3 flex items-center gap-2 text-sm text-purple-300">
                <span className="h-2 w-2 rounded-full bg-purple-400 animate-pulse" />
                Connecting...
              </div>
            </div>
          </div>
          <button
            onClick={onDismiss}
            className="rounded-lg p-1 text-gray-400 transition hover:bg-gray-700 hover:text-white"
            title="Dismiss"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-xl border border-green-500/30 bg-gradient-to-r from-green-500/10 to-indigo-500/10 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-green-500/20">
            <SparklesIcon className="h-5 w-5 text-green-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">
              Workspace &quot;{workspaceName}&quot; created!
            </h3>
            <p className="mt-1 text-sm text-gray-400">
              Configure your AI agent to connect to this workspace.
            </p>
          </div>
        </div>
        <button
          onClick={onDismiss}
          className="rounded-lg p-1 text-gray-400 transition hover:bg-gray-700 hover:text-white"
          title="Dismiss"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="mt-4 flex gap-2 border-b border-gray-700 pb-2">
        <button
          onClick={() => setActiveTab('quick')}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            activeTab === 'quick'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:bg-gray-700 hover:text-white'
          }`}
        >
          <BoltIcon className="h-4 w-4" />
          Quick Setup
        </button>
        <button
          onClick={() => setActiveTab('full')}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            activeTab === 'full'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:bg-gray-700 hover:text-white'
          }`}
        >
          <WrenchScrewdriverIcon className="h-4 w-4" />
          Full Setup
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-4 space-y-4">
        {activeTab === 'quick' && (
          <>
            <p className="text-sm text-gray-400">
              Already have mai-tai configured on this machine? Just add the workspace ID:
            </p>
            <CodeBlock
              code={projectConfigCommand}
              copyId="quick-env"
              label="Run in your project directory:"
            />
            <p className="text-xs text-gray-500">
              Need to set up from scratch?{' '}
              <button
                onClick={() => setActiveTab('full')}
                className="text-indigo-400 hover:underline"
              >
                Use Full Setup →
              </button>
            </p>
          </>
        )}

        {activeTab === 'full' && (
          <>
            {/* Step 1: API Key Generation */}
            {!generatedKey ? (
              <div className="space-y-3">
                <p className="text-sm text-gray-400">
                  New machine or first time using mai-tai? First, generate an API key:
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={handleGenerateApiKey}
                    disabled={isGeneratingKey}
                    className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
                  >
                    <PlusIcon className="h-4 w-4" />
                    {isGeneratingKey ? 'Generating...' : 'Generate New API Key'}
                  </button>
                  <span className="text-sm text-gray-500">or</span>
                  <a
                    href="/settings?tab=api-keys"
                    className="text-sm text-indigo-400 hover:underline"
                  >
                    View existing keys →
                  </a>
                </div>
                {keyError && (
                  <p className="text-sm text-red-400">{keyError}</p>
                )}
              </div>
            ) : (
              /* Step 2: Show AgentSetupBlob with generated key */
              <AgentSetupBlob
                apiKey={generatedKey}
                workspaceId={workspaceId}
                apiUrl={backendUrl}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

