'use client';

import { useState, useEffect } from 'react';
import { XMarkIcon, RocketLaunchIcon } from '@heroicons/react/24/outline';
import AgentSetupBlob from '@/components/AgentSetupBlob';
import { loadOnboardingData, clearOnboardingData, type OnboardingData } from '@/lib/onboarding';

interface OnboardingCardProps {
  /** @deprecated Use workspaceId */
  projectId?: string;
  workspaceId?: string;
  hasMessages?: boolean;
  onDismiss?: () => void;
}

export function OnboardingCard({ projectId, workspaceId, hasMessages = false, onDismiss }: OnboardingCardProps) {
  const [onboardingData, setOnboardingData] = useState<OnboardingData | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // Support both workspaceId and legacy projectId
  const wsId = workspaceId || projectId;

  useEffect(() => {
    // Check for onboarding data in sessionStorage (stored encoded)
    const data = loadOnboardingData();
    if (data) {
      const dataWsId = data.workspaceId || data.projectId;
      // Only show if this is the right workspace
      if (dataWsId === wsId) {
        setOnboardingData(data as OnboardingData & { apiKey: string });
      }
    }
  }, [wsId]);

  // Auto-dismiss when messages appear (agent is connected and chatting)
  useEffect(() => {
    if (hasMessages && onboardingData) {
      clearOnboardingData();
      setDismissed(true);
      onDismiss?.();
    }
  }, [hasMessages, onboardingData, onDismiss]);

  const handleDismiss = () => {
    setDismissed(true);
    // Clear the onboarding data
    sessionStorage.removeItem('mai-tai-onboarding');
    onDismiss?.();
  };

  if (!onboardingData || dismissed) {
    return null;
  }

  return (
    <div className="mx-4 mt-4 mb-4 shrink-0 rounded-xl border border-indigo-500/30 bg-gradient-to-br from-indigo-500/10 to-purple-500/10 p-4 sm:p-6 lg:mx-6">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-500/20">
            <RocketLaunchIcon className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">🍹 Welcome to Mai-Tai!</h2>
            <p className="text-sm text-gray-400">Connect your agent to start chatting</p>
          </div>
        </div>
        <button
          onClick={handleDismiss}
          className="rounded-full p-1 text-gray-400 hover:bg-gray-700 hover:text-white"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      {/* Agent Setup */}
      <div className="rounded-lg bg-gray-800/50 p-4">
        <AgentSetupBlob
          apiKey={onboardingData.apiKey || ''}
          workspaceId={wsId || ''}
        />
      </div>

      {/* Dismiss hint */}
      <p className="mt-4 text-center text-xs text-gray-500">
        Once your agent connects, this card will disappear. You can also{' '}
        <button onClick={handleDismiss} className="text-indigo-400 hover:underline">
          dismiss it now
        </button>
        .
      </p>
    </div>
  );
}

