'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import {
  Cog6ToothIcon,
  PaperAirplaneIcon,
  LightBulbIcon,
} from '@heroicons/react/24/outline';
import { LightBulbIcon as LightBulbIconSolid } from '@heroicons/react/24/solid';
import { useToast } from '@/hooks/use-toast';
import { useWebSocket } from '@/hooks/use-websocket';
import { useNotificationSound } from '@/hooks/use-notification-sound';
import { useAuth } from '@/lib/auth';
import { useChatShortcuts } from '@/lib/chat-shortcuts';
import { OnboardingCard } from '@/components/OnboardingCard';
import NewWorkspaceCard from '@/components/NewWorkspaceCard';
import Modal from '@/components/Common/Modal';
import Button from '@/components/Common/Button';
import MarkdownMessage from '@/components/chat/MarkdownMessage';
import {
  getWorkspace,
  getMessages,
  sendMessage,
  getAgentStatus,
  updateWorkspace,
  Workspace,
  Message,
  AgentStatus,
} from '@/lib/api';
import WorkspaceSettings from './WorkspaceSettings';
import WorkspaceSwitcher from '@/components/WorkspaceSwitcher';

export default function WorkspacePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const isNewWorkspace = searchParams.get('new') === 'true';
  const router = useRouter();
  const { user, token, isLoading, formatTime } = useAuth();
  const { toast } = useToast();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [showAgentNameModal, setShowAgentNameModal] = useState(false);
  const [customAgentName, setCustomAgentName] = useState('');
  const [showNewWorkspaceCard, setShowNewWorkspaceCard] = useState(isNewWorkspace);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Notification sound
  const { playSound } = useNotificationSound();

  // Chat shortcuts
  const { pendingShortcut, clearPendingShortcut, setIsInChatContext } = useChatShortcuts();

  // Set chat context when on this page
  useEffect(() => {
    setIsInChatContext(true);
    return () => setIsInChatContext(false);
  }, [setIsInChatContext]);

  // Force layout reset when mobile keyboard closes (iOS/Android)
  // This fixes the gap between input and mobile nav after sending messages
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    let lastHeight = vv.height;
    const handleResize = () => {
      // Keyboard closed: viewport got significantly taller
      if (vv.height > lastHeight + 100) {
        // Force page scroll reset after keyboard animation completes
        setTimeout(() => {
          window.scrollTo(0, 0);
        }, 50);
      }
      lastHeight = vv.height;
    };

    vv.addEventListener('resize', handleResize);
    return () => vv.removeEventListener('resize', handleResize);
  }, []);

  // Handle pending shortcut from popup
  useEffect(() => {
    if (pendingShortcut) {
      setNewMessage(pendingShortcut);
      clearPendingShortcut();
      textareaRef.current?.focus();
    }
  }, [pendingShortcut, clearPendingShortcut]);

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === message.id)) return prev;
      if (message.agent_name) playSound();
      return [...prev, message];
    });
  }, [playSound]);

  // WebSocket connection - now uses workspaceId directly
  const { isConnected, reconnect } = useWebSocket({
    workspaceId: workspaceId,
    token,
    onMessage: handleWebSocketMessage,
  });

  // Catch up on messages when tab becomes visible
  useEffect(() => {
    if (!token || !workspaceId) return;

    const handleVisibilityChange = async () => {
      if (document.visibilityState === 'visible') {
        try {
          const res = await getMessages(token, workspaceId);
          setMessages((prev) => {
            const existingIds = new Set(prev.map((m) => m.id));
            const newMessages = res.messages.filter((m: Message) => !existingIds.has(m.id));
            if (newMessages.length > 0) {
              const merged = [...prev, ...newMessages].sort(
                (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
              );
              return merged;
            }
            return prev;
          });
        } catch (err) {
          console.error('Failed to catch up on messages:', err);
        }

        if (!isConnected) {
          reconnect();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [token, workspaceId, isConnected, reconnect]);

  // Auth redirect
  useEffect(() => {
    if (!isLoading && !token) router.push('/login');
  }, [isLoading, token, router]);

  // Load workspace
  useEffect(() => {
    if (!token || !workspaceId) return;

    getWorkspace(token, workspaceId).then(setWorkspace).catch(() => {
      toast({ variant: 'destructive', title: 'Failed to load workspace' });
    });

    // Load messages
    getMessages(token, workspaceId).then((res) => setMessages(res.messages));
  }, [token, workspaceId, toast]);

  // Poll agent status every 10 seconds
  useEffect(() => {
    if (!token || !workspaceId) return;

    const fetchStatus = async () => {
      try {
        const status = await getAgentStatus(token, workspaceId);
        setAgentStatus(status);
      } catch (err) {
        console.error('Failed to fetch agent status:', err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [token, workspaceId]);

  // Scroll to bottom on new messages
  // Using 'instant' instead of 'smooth' to avoid animation race conditions
  // with mobile keyboard open/close and viewport resizing
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
  }, [messages]);

  // Auto-resize textarea
  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [newMessage]);

  const handleSendMessage = async () => {
    if (!token || !newMessage.trim()) return;
    // Blur input to trigger onBlur handler which fixes mobile layout after keyboard closes
    textareaRef.current?.blur();
    try {
      const message = await sendMessage(token, workspaceId, newMessage.trim());
      setMessages([...messages, message]);
      setNewMessage('');
    } catch {
      toast({ variant: 'destructive', title: 'Failed to send message' });
    }
  };

  const handleSaveAgentName = async () => {
    if (!token || !workspace || !customAgentName.trim()) return;
    try {
      const newSettings = { ...workspace.settings, agent_name: customAgentName.trim() };
      const updated = await updateWorkspace(token, workspaceId, { settings: newSettings });
      setWorkspace(updated);
      setShowAgentNameModal(false);
      toast({ title: 'Agent name updated' });
    } catch {
      toast({ variant: 'destructive', title: 'Failed to update agent name' });
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  // Get agent name: "His Dudeness" when dude mode is on, otherwise custom name or "AI Agent"
  const dudeMode = (workspace?.settings?.dude_mode as boolean) ?? false;
  const planMode = (workspace?.settings?.plan_mode as boolean) ?? false;
  const storedAgentName = workspace?.settings?.agent_name as string | undefined;
  const agentName = dudeMode ? 'His Dudeness' : (storedAgentName || 'AI Agent');
  const agentInitial = dudeMode ? '🍹' : 'A';

  // Toggle plan mode
  const handleTogglePlanMode = async () => {
    if (!token || !workspace) return;
    try {
      const newPlanMode = !planMode;
      const newSettings = { ...workspace.settings, plan_mode: newPlanMode };
      const updated = await updateWorkspace(token, workspaceId, { settings: newSettings });
      setWorkspace(updated);
      toast({ title: newPlanMode ? '💡 Plan Mode enabled' : 'Plan Mode disabled' });

      // Send system message when plan mode is turned OFF (so agent knows)
      // This message is hidden from UI but visible to the agent
      if (!newPlanMode && messages.length > 0) {
        await sendMessage(
          token,
          workspaceId,
          '[Plan mode disabled - ready to implement]',
          'system'
        );
        // Don't add to local state - system messages are hidden from UI
      }
    } catch {
      toast({ variant: 'destructive', title: 'Failed to toggle Plan Mode' });
    }
  };

  return (
    <div className="fixed inset-x-0 top-0 bottom-20 flex flex-col overflow-x-hidden lg:static lg:-mx-8 lg:-my-6 lg:h-[calc(100dvh-4rem-1.5rem)] lg:w-auto lg:max-w-none">
      {/* Header */}
      <div className="shrink-0 border-b border-gray-700 bg-gray-800/50 px-4 py-4 lg:px-6">
        <div className="flex items-center justify-between">
          {/* Workspace Name & Status */}
          <div className="flex flex-col">
            <WorkspaceSwitcher
              currentWorkspaceId={workspaceId}
              currentWorkspaceName={workspace?.name || 'Loading...'}
            />
            <div className="flex items-center gap-1.5 text-sm text-gray-400">
              <button
                onClick={() => {
                  setCustomAgentName(agentName);
                  setShowAgentNameModal(true);
                }}
                className="flex items-center gap-1 hover:text-indigo-400 transition-colors"
                title="Click to rename agent"
              >
                {agentName}
                {agentStatus && (
                  <span
                    className={`ml-1 h-2 w-2 rounded-full ${
                      agentStatus.status === 'connected'
                        ? 'bg-green-500'
                        : agentStatus.status === 'idle'
                        ? 'bg-yellow-500'
                        : 'bg-gray-500'
                    }`}
                    title={agentStatus.message}
                  />
                )}
              </button>
              {/* Plan Mode Toggle */}
              <button
                onClick={handleTogglePlanMode}
                className={`ml-1 transition-colors ${
                  planMode ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'
                }`}
                title={planMode ? 'Plan Mode ON - Click to disable' : 'Plan Mode OFF - Click to enable'}
              >
                {planMode ? (
                  <LightBulbIconSolid className="h-4 w-4" />
                ) : (
                  <LightBulbIcon className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {/* Right side: Avatars + Settings */}
          <div className="flex items-center gap-3">
            {/* Participant Avatars */}
            <div className="flex -space-x-2">
              {/* User Avatar */}
              <div className="relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 border-gray-800 bg-gray-700 text-sm font-semibold text-gray-200">
                {user?.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user?.name || 'You'}
                    className="h-full w-full rounded-full object-cover"
                  />
                ) : (
                  user?.name?.[0]?.toUpperCase() || 'U'
                )}
              </div>
              {/* Agent Avatar */}
              <div className="relative z-0 flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border-2 border-gray-800 bg-gradient-to-br from-indigo-500 to-purple-600 text-sm">
                {dudeMode ? (
                  <img
                    src="/the-dude-avatar.png"
                    alt="The Dude"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  'AI'
                )}
              </div>
            </div>

            <Button
              buttonType="ghost"
              buttonSize="sm"
              onClick={() => setShowSettings(true)}
            >
              <Cog6ToothIcon className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Onboarding Card - outside scrollable area */}
      <OnboardingCard workspaceId={workspaceId} hasMessages={messages.length > 0} />

      {/* New Workspace Card - shown when user creates a new workspace */}
      {showNewWorkspaceCard && workspace && (
        <div className="shrink-0 px-4 lg:px-6">
          <div className="mx-auto lg:max-w-4xl">
            <NewWorkspaceCard
              workspaceId={workspaceId}
              workspaceName={workspace.name}
              hasMessages={messages.length > 0}
              onDismiss={() => {
                setShowNewWorkspaceCard(false);
                // Remove ?new=true from URL without reload
                router.replace(`/workspaces/${workspaceId}`, { scroll: false });
              }}
            />
          </div>
        </div>
      )}

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-x-hidden overflow-y-auto overscroll-contain">
        <div className="mx-auto w-full space-y-4 p-4 lg:max-w-4xl lg:p-6">
          {messages.length === 0 ? (
            <p className="py-16 text-center text-base text-gray-500">
              No messages yet. Start the conversation!
            </p>
          ) : (
            messages.filter((m) => m.message_type !== 'system').map((message) => {
              const isAgent = !!message.agent_name;
              // Use proper agent name based on dude mode, not the API key name
              const senderName = isAgent ? agentName : (message.sender_name || user?.name || 'You');
              const senderInitial = isAgent ? agentInitial : (senderName?.[0]?.toUpperCase() || 'U');

              return (
                <div
                  key={message.id}
                  className={`rounded-xl p-4 ${
                    isAgent
                      ? 'bg-gray-800/70 border border-gray-700/50'
                      : 'bg-gray-800/40 border border-gray-700/30'
                  }`}
                >
                  <div className="flex gap-3">
                    {isAgent && dudeMode ? (
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-purple-600">
                        <img
                          src="/the-dude-avatar.png"
                          alt="The Dude"
                          className="h-full w-full object-cover"
                        />
                      </div>
                    ) : message.sender_avatar_url ? (
                      <img
                        src={message.sender_avatar_url}
                        alt={senderName || 'User'}
                        className="h-9 w-9 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
                        isAgent
                          ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white'
                          : 'bg-gray-600 text-gray-200'
                      }`}>
                        {senderInitial}
                      </div>
                    )}

                    <div className="min-w-0 flex-1 overflow-hidden">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className={`font-semibold ${
                          isAgent ? 'text-indigo-300' : 'text-gray-100'
                        }`}>
                          {senderName}
                        </span>
                        <span className="text-xs text-gray-500">
                          {formatTime(message.created_at)}
                        </span>
                      </div>

                      <div className="mt-1.5">
                        <MarkdownMessage content={message.content} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Message Input - Fixed at Bottom */}
      <div className="shrink-0 overflow-hidden border-t border-gray-700 bg-gray-800/50 px-2 py-2 sm:px-4 sm:py-3 lg:px-6 lg:py-4">
        <div className="mx-auto flex w-full items-end gap-1.5 sm:gap-2 lg:max-w-4xl lg:gap-3">
          <textarea
            ref={textareaRef}
            placeholder="Type a message..."
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            onBlur={() => {
              // Force iOS to recalculate layout after keyboard closes
              // This fixes the issue where the input stays "floating" in the middle
              setTimeout(() => {
                window.scrollTo(0, 0);
              }, 100);
            }}
            rows={1}
            className="min-h-[40px] max-h-[200px] min-w-0 flex-1 resize-none rounded-lg border border-gray-600 bg-gray-700 px-2.5 py-2 text-base leading-relaxed text-white placeholder-gray-500 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:min-h-[44px] sm:px-3 sm:py-2.5 lg:min-h-[48px] lg:px-4 lg:py-3"
          />
          <Button
            buttonType="primary"
            onClick={handleSendMessage}
            className="h-[40px] w-[40px] shrink-0 p-0 sm:h-[44px] sm:w-[44px] lg:h-[48px] lg:w-auto lg:px-4"
          >
            <PaperAirplaneIcon className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* Settings Modal */}
      <Modal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        title="Workspace Settings"
        size="lg"
      >
        <WorkspaceSettings
          workspaceId={workspaceId}
          token={token}
          workspace={workspace}
          onWorkspaceUpdate={setWorkspace}
        />
      </Modal>

      {/* Agent Name Modal */}
      <Modal
        open={showAgentNameModal}
        onClose={() => setShowAgentNameModal(false)}
        title="Rename Agent"
        size="sm"
      >
        <div className="space-y-4 py-2">
          <input
            type="text"
            placeholder="Agent name"
            value={customAgentName}
            onChange={(e) => setCustomAgentName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveAgentName()}
            autoFocus
            className="w-full rounded-lg border border-gray-600 bg-gray-700/80 px-4 py-3 text-white placeholder-gray-400 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <div className="flex justify-end gap-2">
            <Button buttonType="ghost" onClick={() => setShowAgentNameModal(false)}>
              Cancel
            </Button>
            <Button buttonType="primary" onClick={handleSaveAgentName}>
              Save
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

