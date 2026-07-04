'use client';

import { CpuChipIcon } from '@heroicons/react/24/outline';

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-gradient text-3xl font-bold">Agents</h1>
        <p className="mt-2 text-muted-foreground">Manage your AI agents and their configurations.</p>
      </div>

      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/50 p-16 text-center">
        <CpuChipIcon className="h-16 w-16 text-faint" />
        <h2 className="mt-6 text-xl font-semibold text-muted-foreground">Coming Soon</h2>
        <p className="mt-2 max-w-md text-faint">
          Agent management will allow you to configure AI agents, set their capabilities, and monitor their activity across your projects.
        </p>
      </div>
    </div>
  );
}

