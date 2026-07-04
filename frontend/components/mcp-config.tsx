'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Copy, Check, Terminal, AlertTriangle } from 'lucide-react';

type AgentTool = 'claude-code' | 'augment-cli' | 'gemini-cli' | 'openai-codex' | 'claude-desktop' | 'other';

interface McpConfigProps {
  apiKey?: string;
  workspaceId?: string;
  /** @deprecated Use workspaceId instead */
  projectId?: string;
  onCopied?: () => void;
}

// Get the backend URL for MCP config
function getBackendUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    return apiUrl;
  }
  return 'https://api.mai-tai.dev';
}

const AGENT_TOOLS: { id: AgentTool; name: string; icon: string }[] = [
  { id: 'claude-code', name: 'Claude Code', icon: '🤖' },
  { id: 'augment-cli', name: 'Augment Code', icon: '⚡' },
  { id: 'gemini-cli', name: 'Gemini CLI', icon: '💎' },
  { id: 'openai-codex', name: 'OpenAI Codex', icon: '🧠' },
  { id: 'claude-desktop', name: 'Claude Desktop', icon: '🖥️' },
  { id: 'other', name: 'Other / Manual', icon: '📋' },
];

// Reusable code block component
function CodeBlock({
  code,
  copyId,
  copiedSection,
  onCopy
}: {
  code: string;
  copyId: string;
  copiedSection: string | null;
  onCopy: (text: string, id: string) => void;
}) {
  return (
    <div className="relative group">
      <pre className="overflow-x-auto rounded-lg bg-background dark:bg-background p-4 pr-12 font-mono text-sm text-foreground border border-border">
        <code>{code}</code>
      </pre>
      <Button
        size="sm"
        variant="ghost"
        className="absolute right-2 top-2 opacity-60 hover:opacity-100 transition-opacity"
        onClick={() => onCopy(code, copyId)}
      >
        {copiedSection === copyId ? (
          <Check className="h-4 w-4 text-success" />
        ) : (
          <Copy className="h-4 w-4 text-muted-foreground" />
        )}
      </Button>
    </div>
  );
}

// Step component for numbered instructions
function Step({
  number,
  title,
  description,
  children
}: {
  number: number;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3">
        <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-primary/20 text-primary text-sm font-semibold">
          {number}
        </span>
        <div className="flex-1 min-w-0">
          <h5 className="text-sm font-semibold text-foreground">{title}</h5>
          {description && (
            <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
          )}
        </div>
      </div>
      <div className="ml-9 space-y-3">
        {children}
      </div>
    </div>
  );
}

// Warning callout component
function WarningCallout({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 p-3 rounded-lg bg-warning/10 border border-warning/20">
      <AlertTriangle className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
      <div className="space-y-1">
        <h6 className="text-sm font-medium text-warning">{title}</h6>
        <p className="text-sm text-warning/70">{children}</p>
      </div>
    </div>
  );
}

// Info callout component
function InfoCallout({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm text-muted-foreground">
      {children}
    </p>
  );
}

export function McpConfig({ apiKey, workspaceId, projectId, onCopied }: McpConfigProps) {
  const [copiedSection, setCopiedSection] = useState<string | null>(null);
  const [selectedTool, setSelectedTool] = useState<AgentTool>('claude-code');
  const backendUrl = getBackendUrl();

  // Support both workspaceId and legacy projectId
  const wsId = workspaceId || projectId || '<YOUR_WORKSPACE_ID>';
  const hasApiKey = apiKey && apiKey !== '<YOUR_API_KEY>';

  // Global config - full shell command to create the file
  const globalConfigCommand = `mkdir -p ~/.config/mai-tai && cat > ~/.config/mai-tai/config << 'EOF'
MAI_TAI_API_URL=${backendUrl}
MAI_TAI_API_KEY=${apiKey || '<YOUR_API_KEY>'}
EOF`;

  // Per-project config - shell command to create the file
  const projectConfigCommand = `echo "MAI_TAI_WORKSPACE_ID=${wsId}" > .env.mai-tai`;

  // Claude Code commands - simplified, config files provide env vars
  const claudeCodeCommand = `claude mcp add --transport stdio mai-tai -- uvx --refresh mai-tai-mcp`;
  const claudeStartCommand = `claude --dangerously-skip-permissions`;

  // Augment CLI commands
  const augmentAddCommand = `auggie mcp add mai-tai --command uvx --args "--refresh mai-tai-mcp"`;
  const augmentStartCommand = `auggie`;

  // Gemini CLI commands
  const geminiAddCommand = `gemini mcp add mai-tai uvx --refresh mai-tai-mcp --trust`;
  const geminiStartCommand = `gemini --yolo`;

  // OpenAI Codex commands
  const codexAddCommand = `codex mcp add mai-tai -- uvx --refresh mai-tai-mcp`;
  const codexStartCommand = `codex`;

  // JSON config for desktop apps - still needs env vars since it's a static config file
  const claudeConfig = {
    mcpServers: {
      "mai-tai": {
        command: "uvx",
        args: ["--refresh", "mai-tai-mcp"],
        env: {
          MAI_TAI_API_URL: backendUrl,
          MAI_TAI_API_KEY: apiKey || '<YOUR_API_KEY>',
          MAI_TAI_WORKSPACE_ID: wsId
        }
      }
    }
  };
  const configString = JSON.stringify(claudeConfig, null, 2);

  const copyToClipboard = async (text: string, section: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedSection(section);
      onCopied?.();
      setTimeout(() => setCopiedSection(null), 2000);
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedSection(section);
      onCopied?.();
      setTimeout(() => setCopiedSection(null), 2000);
    }
  };

  return (
    <div className="min-w-0 space-y-8">
      {/* Global Config Section - only show if we have an API key */}
      {hasApiKey && (
        <section className="space-y-4">
          <div>
            <h3 className="text-base font-semibold flex items-center gap-2">
              🔑 Step 1: Global Config (one-time setup)
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              Run this command to save your API key. This works for all your projects.
            </p>
          </div>
          <CodeBlock
            code={globalConfigCommand}
            copyId="global-config"
            copiedSection={copiedSection}
            onCopy={copyToClipboard}
          />
          <InfoCallout>
            Copy and run this now — your API key won&apos;t be shown again!
          </InfoCallout>
        </section>
      )}

      {/* Per-Project Config Section */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            📁 {hasApiKey ? 'Step 2: ' : ''}Project Config
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            Run this in your project directory to link it to this workspace.
          </p>
        </div>
        <CodeBlock
          code={projectConfigCommand}
          copyId="project-config"
          copiedSection={copiedSection}
          onCopy={copyToClipboard}
        />
        <InfoCallout>
          Each project gets its own workspace. Run this from your project root (where your code lives).
        </InfoCallout>
      </section>

      {/* Tool Selector */}
      <section className="space-y-3">
        <h3 className="text-base font-semibold">{hasApiKey ? 'Step 3: ' : ''}Configure your AI tool</h3>
        <div className="flex flex-wrap gap-2">
          {AGENT_TOOLS.map((tool) => (
            <Button
              key={tool.id}
              size="sm"
              variant={selectedTool === tool.id ? 'default' : 'outline'}
              onClick={() => setSelectedTool(tool.id)}
              className="text-sm"
            >
              <span className="mr-1.5">{tool.icon}</span>
              {tool.name}
            </Button>
          ))}
        </div>
      </section>

      {/* Claude Code CLI */}
      {selectedTool === 'claude-code' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5 text-primary" />
            <h3 className="text-base font-semibold">Claude Code Setup</h3>
          </div>

          <Step
            number={1}
            title="Add the MCP server"
            description="Run this once to register mai-tai with Claude Code"
          >
            <CodeBlock
              code={claudeCodeCommand}
              copyId="claude-add"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <InfoCallout>
              Requires <a href="https://docs.astral.sh/uv/" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">uv</a> to be installed. Config files provide the API key and workspace ID.
            </InfoCallout>
          </Step>

          <Step
            number={2}
            title="Start Claude Code"
            description="Run from your project directory"
          >
            <CodeBlock
              code={claudeStartCommand}
              copyId="claude-start"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <WarningCallout title="About --dangerously-skip-permissions">
              This flag lets Claude work autonomously without prompting for each action. Required for mai-tai mode. Only use in trusted environments.
            </WarningCallout>
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              Once Claude is running, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}

      {/* Augment CLI */}
      {selectedTool === 'augment-cli' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5 text-primary" />
            <h3 className="text-base font-semibold">Augment Code Setup</h3>
          </div>

          <Step
            number={1}
            title="Add the MCP server"
            description="Run this once to register mai-tai with Augment Code"
          >
            <CodeBlock
              code={augmentAddCommand}
              copyId="augment-add"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <InfoCallout>
              Requires <a href="https://docs.astral.sh/uv/" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">uv</a> to be installed. Config files provide the API key and workspace ID.
            </InfoCallout>
          </Step>

          <Step
            number={2}
            title="Start Augment Code"
            description="Run from your project directory"
          >
            <CodeBlock
              code={augmentStartCommand}
              copyId="augment-start"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              Once Auggie is running, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}

      {/* Gemini CLI */}
      {selectedTool === 'gemini-cli' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">💎</span>
            <h3 className="text-base font-semibold">Gemini CLI Setup</h3>
          </div>

          <Step
            number={1}
            title="Add the MCP server"
            description="Run this once to register mai-tai with Gemini CLI"
          >
            <CodeBlock
              code={geminiAddCommand}
              copyId="gemini-add"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <WarningCallout title="About --trust">
              This flag is saved in your config and bypasses tool confirmation prompts. Required for mai-tai mode. Only use in trusted environments.
            </WarningCallout>
            <InfoCallout>
              Requires <a href="https://docs.astral.sh/uv/" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">uv</a> to be installed. Config files provide the API key and workspace ID.
            </InfoCallout>
          </Step>

          <Step
            number={2}
            title="Start Gemini CLI"
            description="Run from your project directory"
          >
            <CodeBlock
              code={geminiStartCommand}
              copyId="gemini-start"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <WarningCallout title="About --yolo">
              This flag lets Gemini work autonomously without prompting for each action. Required for mai-tai mode. Only use in trusted environments.
            </WarningCallout>
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              Once Gemini is running, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}

      {/* OpenAI Codex CLI */}
      {selectedTool === 'openai-codex' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">🧠</span>
            <h3 className="text-base font-semibold">OpenAI Codex Setup</h3>
          </div>

          <Step
            number={1}
            title="Add the MCP server"
            description="Run this once to register mai-tai with OpenAI Codex"
          >
            <CodeBlock
              code={codexAddCommand}
              copyId="codex-add"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
            <InfoCallout>
              Requires <a href="https://docs.astral.sh/uv/" target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">uv</a> to be installed. Config files provide the API key and workspace ID.
            </InfoCallout>
          </Step>

          <Step
            number={2}
            title="Start Codex"
            description="Run from your project directory"
          >
            <CodeBlock
              code={codexStartCommand}
              copyId="codex-start"
              copiedSection={copiedSection}
              onCopy={copyToClipboard}
            />
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              Once Codex is running, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}

      {/* Claude Desktop (JSON) */}
      {selectedTool === 'claude-desktop' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">🖥️</span>
            <h3 className="text-base font-semibold">Claude Desktop Setup</h3>
          </div>

          <InfoCallout>
            Claude Desktop uses a static JSON config file, so you&apos;ll need to include the env vars directly. For CLI tools, use the config file approach above instead.
          </InfoCallout>

          <Step
            number={1}
            title="Add to your MCP config file"
            description="Merge this into your claude_desktop_config.json"
          >
            <div className="relative group">
              <pre className="overflow-x-auto overflow-y-auto max-h-48 rounded-lg bg-background dark:bg-background p-4 pr-12 font-mono text-sm text-foreground border border-border">
                <code>{configString}</code>
              </pre>
              <Button
                size="sm"
                variant="ghost"
                className="absolute right-2 top-2 opacity-60 hover:opacity-100 transition-opacity"
                onClick={() => copyToClipboard(configString, 'desktop-config')}
              >
                {copiedSection === 'desktop-config' ? (
                  <Check className="h-4 w-4 text-success" />
                ) : (
                  <Copy className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
          </Step>

          <Step
            number={2}
            title="Restart Claude Desktop"
            description="Quit and reopen the app to load the new config"
          >
            <InfoCallout>
              After restarting, you should see mai-tai in the MCP servers list.
            </InfoCallout>
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              In a new conversation, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}

      {/* Other / Manual */}
      {selectedTool === 'other' && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">📋</span>
            <h3 className="text-base font-semibold">Manual Configuration</h3>
          </div>

          <InfoCallout>
            For CLI tools, run the config commands in Steps 1 &amp; 2 above. The MCP server reads from <code className="rounded bg-card px-1 py-0.5 text-secondary">~/.config/mai-tai/config</code> and <code className="rounded bg-card px-1 py-0.5 text-secondary">.env.mai-tai</code> automatically.
          </InfoCallout>

          <Step
            number={1}
            title="JSON config (for desktop apps)"
            description="Use this if your tool requires a static JSON config"
          >
            <div className="relative group">
              <pre className="overflow-x-auto overflow-y-auto max-h-48 rounded-lg bg-background dark:bg-background p-4 pr-12 font-mono text-sm text-foreground border border-border">
                <code>{configString}</code>
              </pre>
              <Button
                size="sm"
                variant="ghost"
                className="absolute right-2 top-2 opacity-60 hover:opacity-100 transition-opacity"
                onClick={() => copyToClipboard(configString, 'manual-config')}
              >
                {copiedSection === 'manual-config' ? (
                  <Check className="h-4 w-4 text-success" />
                ) : (
                  <Copy className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
              <code className="rounded-md bg-card px-2 py-1 text-sm text-secondary">MAI_TAI_API_URL</code>
              <code className="rounded-md bg-card px-2 py-1 text-sm text-secondary">MAI_TAI_API_KEY</code>
              <code className="rounded-md bg-card px-2 py-1 text-sm text-secondary">MAI_TAI_WORKSPACE_ID</code>
            </div>
          </Step>

          <Step
            number={2}
            title="Restart your AI client"
            description="Reload the config to connect to mai-tai"
          >
            <InfoCallout>
              After restarting, you should see mai-tai in the MCP servers list.
            </InfoCallout>
          </Step>

          <Step
            number={3}
            title="Start mai-tai mode"
            description="Tell your agent to connect to the chat"
          >
            <InfoCallout>
              Once your agent is running, type <code className="rounded-md bg-card px-1.5 py-0.5 text-sm text-secondary">start mai tai mode</code> to connect to this project&apos;s chat.
            </InfoCallout>
          </Step>
        </section>
      )}
    </div>
  );
}

