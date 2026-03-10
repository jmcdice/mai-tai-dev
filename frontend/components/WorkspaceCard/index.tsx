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
  'from-indigo-600 to-purple-700',
  'from-purple-600 to-pink-700',
  'from-blue-600 to-indigo-700',
  'from-cyan-600 to-blue-700',
  'from-teal-600 to-cyan-700',
  'from-emerald-600 to-teal-700',
  'from-violet-600 to-purple-700',
  'from-fuchsia-600 to-pink-700',
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
          className={`relative transform-gpu cursor-pointer overflow-hidden rounded-xl bg-gray-800 ring-1 transition duration-300 ${
            showDetail
              ? 'scale-[1.02] shadow-lg ring-gray-500'
              : 'scale-100 shadow ring-gray-700'
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
              <CpuChipIcon className="h-16 w-16 text-white opacity-30" />
            ) : (
              <ChatBubbleLeftRightIcon className="h-16 w-16 text-white opacity-30" />
            )}
          </div>

          {/* Status badges - top */}
          <div className="absolute left-0 right-0 top-0 flex items-center justify-between p-2">
            <div className={`rounded-full border px-2 py-1 ${
              workspaceType === 'agent'
                ? 'border-purple-400/30 bg-purple-500/30'
                : 'border-white/20 bg-black/30'
            }`}>
              <span className="text-xs font-medium text-white">
                {badge || (workspaceType === 'agent' ? 'Agent' : 'Workspace')}
              </span>
            </div>
            {archived && (
              <div className="flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/20 px-2 py-1">
                <ArchiveBoxIcon className="h-3 w-3 text-amber-400" />
                <span className="text-xs font-medium text-amber-400">Archived</span>
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
                  'linear-gradient(180deg, rgba(17, 24, 39, 0.2) 0%, rgba(17, 24, 39, 0.95) 100%)',
              }}
            >
              <h3 className="mb-1 text-lg font-bold text-white line-clamp-2">
                {name}
              </h3>
              {description && (
                <p className="mb-2 text-xs text-gray-300 line-clamp-2">
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
              <h3 className="text-sm font-semibold text-white line-clamp-2">
                {name}
              </h3>
              <div className="mt-1 flex items-center gap-1 text-xs text-gray-400">
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

