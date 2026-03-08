'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { useToast } from '@/hooks/use-toast';
import { createWorkspace, Workspace } from '@/lib/api';
import { loadOnboardingData, storeOnboardingData, type OnboardingData } from '@/lib/onboarding';
import { SetupSteps } from './SetupSteps';
import AgentSetupBlob from '@/components/AgentSetupBlob';
import Button from '@/components/Common/Button';
import { RocketLaunchIcon, ChatBubbleLeftRightIcon, ClipboardDocumentIcon } from '@heroicons/react/24/outline';
import { CheckIcon } from '@heroicons/react/24/solid';

const STEPS = [
  { title: 'Create Workspace', description: 'Name your workspace' },
  { title: 'Configure Agent', description: 'Connect your AI tool' },
  { title: 'Start Chatting', description: 'Send your first message' },
];

interface OnboardingFlowProps {
  onComplete?: (workspace: Workspace) => void;
}

export default function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const router = useRouter();
  const { token } = useAuth();
  const { toast } = useToast();

  const [currentStep, setCurrentStep] = useState(1);
  const [workspaceName, setWorkspaceName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createdWorkspace, setCreatedWorkspace] = useState<Workspace | null>(null);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [commandCopied, setCommandCopied] = useState(false);

  // Check for API key from registration (stored encoded in sessionStorage)
  useEffect(() => {
    const data = loadOnboardingData();
    if (data?.apiKey) {
      setApiKey(data.apiKey);
    }
  }, []);

  const handleCreateWorkspace = async () => {
    if (!token || !workspaceName.trim()) return;
    setIsCreating(true);

    try {
      // Create the workspace (no API key creation - user already has a user-level key from registration)
      const workspace = await createWorkspace(token, workspaceName.trim());
      setCreatedWorkspace(workspace);

      // Update sessionStorage with the new workspace ID (keep existing API key)
      const data: OnboardingData = loadOnboardingData() || {};
      data.workspaceId = workspace.id;
      storeOnboardingData(data);

      // Move to step 2
      setCurrentStep(2);
      toast({ title: 'Workspace created!', description: `"${workspace.name}" is ready` });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to create workspace',
        description: error instanceof Error ? error.message : 'Please try again',
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopyCommand = async () => {
    try {
      await navigator.clipboard.writeText('Start mai tai mode');
      setCommandCopied(true);
      setTimeout(() => setCommandCopied(false), 2000);
    } catch {
      // Fallback
      const textArea = document.createElement('textarea');
      textArea.value = 'Start mai tai mode';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCommandCopied(true);
      setTimeout(() => setCommandCopied(false), 2000);
    }
  };

  const handleGoToWorkspace = () => {
    if (createdWorkspace) {
      onComplete?.(createdWorkspace);
      router.push(`/workspaces/${createdWorkspace.id}`);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-white">🍹 Welcome to Mai-Tai!</h1>
        <p className="mt-2 text-gray-400">
          Connect your AI coding agent and chat in real-time.
        </p>
        <p className="mt-1 text-sm text-gray-500">
          Each workspace is a chat room for you and your AI agent — create one for each codebase.
        </p>
      </div>

      {/* Step indicator */}
      <SetupSteps currentStep={currentStep} steps={STEPS} />

      {/* Step content */}
      <div className="min-w-0 overflow-hidden rounded-xl border border-gray-700 bg-gray-800/50 p-4 backdrop-blur-sm sm:p-6">
        {/* Step 1: Create Workspace */}
        {currentStep === 1 && (
          <div className="space-y-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/20">
                <RocketLaunchIcon className="h-5 w-5 text-indigo-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Create Your First Workspace</h2>
                <p className="text-sm text-gray-400">Give it a name like your repo (e.g., &quot;frontend&quot;, &quot;backend-api&quot;)</p>
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                type="text"
                placeholder="Workspace name"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !isCreating && workspaceName.trim() && handleCreateWorkspace()}
                autoFocus
                className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:flex-1"
              />
              <Button
                buttonType="primary"
                onClick={handleCreateWorkspace}
                disabled={!workspaceName.trim() || isCreating}
                className="w-full sm:w-auto"
              >
                {isCreating ? 'Creating...' : 'Create Workspace'}
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Configure Agent */}
        {currentStep === 2 && createdWorkspace && apiKey && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-500/20">
                <CheckIcon className="h-5 w-5 text-green-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Workspace &quot;{createdWorkspace.name}&quot; created!</h2>
                <p className="text-sm text-gray-400">Now configure your AI agent to connect</p>
              </div>
            </div>

            <AgentSetupBlob
              apiKey={apiKey}
              workspaceId={createdWorkspace.id}
              onCopied={() => toast({ title: 'Copied to clipboard!' })}
            />

            <div className="flex justify-end">
              <Button buttonType="primary" onClick={() => setCurrentStep(3)}>
                Next: Start Chatting →
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Start Chatting */}
        {currentStep === 3 && createdWorkspace && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-500/20">
                <ChatBubbleLeftRightIcon className="h-5 w-5 text-indigo-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">You&apos;re All Set!</h2>
                <p className="text-sm text-gray-400">Open your coding agent and send this message:</p>
              </div>
            </div>

            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-4">
              <div className="flex items-center justify-between">
                <code className="text-lg font-semibold text-indigo-300">Start mai tai mode</code>
                <Button
                  buttonType={commandCopied ? 'success' : 'ghost'}
                  buttonSize="sm"
                  onClick={handleCopyCommand}
                >
                  {commandCopied ? (
                    <>
                      <CheckIcon className="mr-1 h-4 w-4" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <ClipboardDocumentIcon className="mr-1 h-4 w-4" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
              <p className="mt-2 text-sm text-gray-400">
                This activates mai-tai mode — your agent will chat with you here in real-time!
              </p>
            </div>

            <div className="flex justify-end">
              <Button buttonType="primary" onClick={handleGoToWorkspace}>
                Go to Workspace Chat →
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

