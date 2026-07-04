'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getWorkspace, getMessages, Workspace, Message } from '@/lib/api';
import MarkdownMessage from '@/components/chat/MarkdownMessage';

export default function PrintChatPage() {
  const { id: workspaceId } = useParams<{ id: string }>();
  const { token, user, formatTime } = useAuth();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get agent name: "His Dudeness" when dude mode is on, otherwise custom name or "AI Agent"
  const dudeMode = (workspace?.settings?.dude_mode as boolean) ?? false;
  const storedAgentName = workspace?.settings?.agent_name as string | undefined;
  const agentName = dudeMode ? 'His Dudeness' : (storedAgentName || 'AI Agent');

  useEffect(() => {
    if (!token || !workspaceId) return;

    const loadData = async () => {
      try {
        const [ws, msgs] = await Promise.all([
          getWorkspace(token, workspaceId),
          getMessages(token, workspaceId),
        ]);
        setWorkspace(ws);
        setMessages(msgs.messages);
      } catch (err) {
        setError('Failed to load chat data');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [token, workspaceId]);

  // Auto-trigger print dialog once loaded
  useEffect(() => {
    if (!isLoading && !error && messages.length > 0) {
      // Small delay to ensure rendering is complete
      const timer = setTimeout(() => {
        window.print();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isLoading, error, messages.length]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="text-faint">Loading chat...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="text-destructive">{error}</div>
      </div>
    );
  }

  const exportDate = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <>
      {/* Print-specific styles - keep dark theme for PDF export */}
      <style jsx global>{`
        @media print {
          html, body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
          }
          .no-print { display: none !important; }
          .message { break-inside: avoid; }
          .print-container {
            min-height: 0 !important;
            height: auto !important;
            background: #1a1a2e !important;
          }
        }
        @media screen {
          body {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0f23 100%);
            min-height: 100vh;
          }
        }
      `}</style>

      <div className="print-container min-h-screen bg-gradient-to-br from-background via-card to-background p-4 text-foreground lg:p-8">
        {/* Header */}
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 border-b border-border pb-4">
            <h1 className="text-2xl font-bold text-white">{workspace?.name}</h1>
            <p className="timestamp mt-1 text-sm text-muted-foreground">
              Exported on {exportDate} • {messages.length} messages
            </p>
          </div>

          {/* Print button (hidden when printing) */}
          <div className="no-print mb-6 flex gap-4">
            <button
              onClick={() => window.print()}
              className="rounded-lg bg-primary px-4 py-2 text-white hover:bg-primary/90"
            >
              Print / Save as PDF
            </button>
            <button
              onClick={() => window.close()}
              className="rounded-lg border border-border-strong px-4 py-2 text-muted-foreground hover:bg-card"
            >
              Close
            </button>
          </div>

          {/* Messages */}
          <div className="space-y-4">
            {messages.map((message) => {
              const isAgent = !!message.agent_name;
              const senderName = isAgent ? agentName : (message.sender_name || user?.name || 'User');
              const senderInitial = senderName?.[0]?.toUpperCase() || 'U';
              const avatarUrl = isAgent && dudeMode
                ? '/the-dude-avatar.png'
                : message.sender_avatar_url;

              return (
                <div
                  key={message.id}
                  className={`message message-bubble rounded-xl p-4 ${
                    isAgent
                      ? 'border border-border/50 bg-card/70'
                      : 'border border-border/30 bg-card/40'
                  }`}
                >
                  <div className="flex gap-3">
                    {isAgent && dudeMode ? (
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-primary to-accent2">
                        <img
                          src="/the-dude-avatar.png"
                          alt="The Dude"
                          className="h-full w-full object-cover"
                        />
                      </div>
                    ) : avatarUrl ? (
                      <img
                        src={avatarUrl}
                        alt={senderName}
                        className="h-9 w-9 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
                        isAgent
                          ? 'bg-gradient-to-br from-primary to-accent2 text-white'
                          : 'bg-surface2 text-foreground'
                      }`}>
                        {senderInitial}
                      </div>
                    )}

                    <div className="min-w-0 flex-1 overflow-hidden">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className={`sender-name font-semibold ${
                          isAgent ? 'sender-name-agent text-primary' : 'text-foreground'
                        }`}>
                          {senderName}
                        </span>
                        <span className="timestamp text-xs text-faint">
                          {formatTime(message.created_at)}
                        </span>
                      </div>
                      <div className="message-text mt-1.5">
                        <MarkdownMessage content={message.content} maxLength={0} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="mt-8 border-t border-border pt-4 text-center text-sm text-faint">
            Exported from Mai-Tai • mai-tai.dev
          </div>
        </div>
      </div>
    </>
  );
}

