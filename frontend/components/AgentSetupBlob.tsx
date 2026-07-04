'use client';

import { useState } from 'react';
import { ClipboardDocumentIcon, CheckIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface AgentSetupBlobProps {
  apiKey: string;
  workspaceId: string;
  apiUrl?: string;
  onCopied?: () => void;
}

// Get the backend URL for config commands
function getBackendUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    return apiUrl;
  }
  return 'https://api.mai-tai.dev';
}

export default function AgentSetupBlob({ apiKey, workspaceId, apiUrl, onCopied }: AgentSetupBlobProps) {
  const [copied, setCopied] = useState(false);
  const backendUrl = apiUrl || getBackendUrl();

  // Build the markdown blob that agents will execute
  // Written to be friendly to agents of varying capabilities
  const setupBlob = `## Mai-Tai MCP Server Setup

You are setting up the mai-tai MCP server. Mai-tai lets humans chat with you in real-time through a web interface while you work on their codebase.

**Before you begin:** Make sure you are in the project root directory (where the code repository lives, e.g., where .git is located).

### Step 1: Save global config (one-time setup)
This saves your API credentials. Run this once - it works for all your projects.

\`\`\`bash
mkdir -p ~/.config/mai-tai && cat > ~/.config/mai-tai/config << 'EOF'
MAI_TAI_API_URL=${backendUrl}
MAI_TAI_API_KEY=${apiKey}
EOF
\`\`\`

### Step 2: Link this project to the workspace
Run this from your project root to associate it with this mai-tai workspace.

\`\`\`bash
echo "MAI_TAI_WORKSPACE_ID=${workspaceId}" > .env.mai-tai
\`\`\`

### Step 3: Add the MCP server to your agent
You need to register the mai-tai MCP server with your agent. The exact command depends on which agent you're using. Here are examples:

**Claude Code:**
\`\`\`bash
claude mcp add --transport stdio mai-tai -- uvx --refresh mai-tai-mcp
\`\`\`

**Gemini CLI:**
\`\`\`bash
gemini mcp add --transport stdio mai-tai -- uvx --refresh mai-tai-mcp
\`\`\`

**Other agents:** Use your agent's equivalent command to add an MCP server. The server command is: \`uvx --refresh mai-tai-mcp\`

Note: You should know how to add MCP servers for your own platform - consult your agent's documentation if needed.

### Step 4: Restart and connect
Restart your agent session, then say "start mai tai mode" to connect to the chat.

Once connected, the human can send you messages through the mai-tai web interface!`;

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(setupBlob);
      setCopied(true);
      onCopied?.();
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = setupBlob;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      onCopied?.();
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-4">
      {/* Security note for humans */}
      <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-3">
        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 text-warning mt-0.5" />
        <div className="text-sm">
          <p className="font-medium text-warning">Important</p>
          <p className="mt-1 text-warning/80">
            You&apos;re responsible for running your coding agent in a trusted environment.
            Consider using a container, VM, or your agent&apos;s built-in sandboxing features.
          </p>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-foreground">Paste this to your coding agent</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Make sure you&apos;re in your project root, then copy and paste this to your AI coding agent:
        </p>
      </div>

      {/* The blob display */}
      <div className="relative">
        <div className="max-h-72 overflow-y-auto rounded-lg border border-border bg-background/80 p-4">
          <pre className="whitespace-pre-wrap font-mono text-sm text-success">
            {setupBlob}
          </pre>
        </div>

        {/* Gradient fade at bottom */}
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-8 rounded-b-lg bg-gradient-to-t from-background/90 to-transparent" />
      </div>

      {/* Copy button */}
      <button
        onClick={copyToClipboard}
        className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition ${
          copied
            ? 'bg-success text-foreground'
            : 'bg-primary text-primary-foreground hover:bg-primary/90'
        }`}
      >
        {copied ? (
          <>
            <CheckIcon className="h-5 w-5" />
            Copied to clipboard!
          </>
        ) : (
          <>
            <ClipboardDocumentIcon className="h-5 w-5" />
            Copy to Clipboard
          </>
        )}
      </button>

      <p className="text-center text-xs text-faint">
        Works with Claude Code, Gemini CLI, and other MCP-compatible agents
      </p>
    </div>
  );
}

