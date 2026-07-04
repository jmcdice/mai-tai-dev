'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Transition } from '@headlessui/react';
import {
  ChatBubbleLeftRightIcon,
  ClockIcon,
  ArchiveBoxIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';

interface WorkspaceCardProps {
  id: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt?: string;
  colorIndex?: number;
  archived?: boolean;
  badge?: string;
  workspaceType?: string;
}

// Jellyseerr-style gradient backgrounds for variety
const gradients = [
  'from-primary to-accent2',
  'from-accent2 to-accent2',
  'from-info to-primary',
  'from-info to-info',
  'from-success to-info',
  'from-success to-success',
  'from-accent2 to-accent2',
  'from-fuchsia-600 to-accent2',
];

export default function WorkspaceCard({
  id,
  name,
  description,
  createdAt,
  colorIndex,
  archived = false,
  badge,
  workspaceType,
}: WorkspaceCardProps) {
  const [showDetail, setShowDetail] = useState(false);

  // Use colorIndex or hash the id for consistent color
  const gradientIndex =
    colorIndex !== undefined
      ? colorIndex % gradients.length
      : Math.abs(id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) %
        gradients.length;

  const gradient = gradients[gradientIndex];

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="w-full">
      <Link href={`/workspaces/${id}`}>
        <div
          className={`relative transform-gpu cursor-pointer overflow-hidden rounded-xl bg-card ring-1 transition duration-300 ${
            showDetail
              ? 'scale-[1.02] shadow-lg ring-border-strong'
              : 'scale-100 shadow ring-border'
          }`}
          style={{ paddingBottom: '75%' }} /* 4:3 aspect ratio */
          onMouseEnter={() => setShowDetail(true)}
          onMouseLeave={() => setShowDetail(false)}
          onTouchStart={() => setShowDetail(true)}
          onTouchEnd={() => setTimeout(() => setShowDetail(false), 2000)}
        >
          {/* Background gradient */}
          <div
            className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-80`}
          />

          {/* Pattern overlay for visual interest */}
          <div
            className="absolute inset-0 opacity-10"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
            }}
          />

          {/* Icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            {workspaceType === 'agent' ? (
              <CpuChipIcon className="h-16 w-16 text-foreground opacity-30" />
            ) : (
              <ChatBubbleLeftRightIcon className="h-16 w-16 text-foreground opacity-30" />
            )}
          </div>

          {/* Status badges - top */}
          <div className="absolute left-0 right-0 top-0 flex items-center justify-between p-2">
            <div className={`rounded-full border px-2 py-1 ${
              workspaceType === 'agent'
                ? 'border-secondary/30 bg-secondary/30'
                : 'border-white/20 bg-black/30'
            }`}>
              <span className="text-xs font-medium text-foreground">
                {badge || (workspaceType === 'agent' ? 'Agent' : 'Workspace')}
              </span>
            </div>
            {archived && (
              <div className="flex items-center gap-1 rounded-full border border-warning/30 bg-warning/20 px-2 py-1">
                <ArchiveBoxIcon className="h-3 w-3 text-warning" />
                <span className="text-xs font-medium text-warning">Archived</span>
              </div>
            )}
          </div>

          {/* Hover overlay with details */}
          <Transition
            show={showDetail}
            enter="transition-opacity duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div
              className="absolute inset-0 flex flex-col justify-end p-3"
              style={{
                background:
                  'linear-gradient(180deg, hsl(var(--background) / 0.2) 0%, hsl(var(--background) / 0.95) 100%)',
              }}
            >
              <h3 className="mb-1 text-lg font-bold text-foreground line-clamp-2">
                {name}
              </h3>
              {description && (
                <p className="mb-2 text-xs text-muted-foreground line-clamp-2">
                  {description}
                </p>
              )}
            </div>
          </Transition>

          {/* Default state - just title at bottom */}
          <Transition
            show={!showDetail}
            enter="transition-opacity duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 pt-8">
              <h3 className="text-sm font-semibold text-foreground line-clamp-2">
                {name}
              </h3>
              <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                <ClockIcon className="h-3 w-3" />
                <span>{formatDate(createdAt)}</span>
              </div>
            </div>
          </Transition>
        </div>
      </Link>
    </div>
  );
}

