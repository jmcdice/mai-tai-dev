'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  LinkIcon,
  PlusIcon,
  TrashIcon,
  CheckIcon,
  ArchiveBoxIcon,
} from '@heroicons/react/24/outline';
import { BookmarkIcon as BookmarkIconSolid } from '@heroicons/react/24/solid';
import { useAuth } from '@/lib/auth';
import Modal from '@/components/Common/Modal';
import {
  StashLink,
  listStashLinks,
  createStashLink,
  updateStashLink,
  deleteStashLink,
} from '@/lib/api';

const STATUS_TABS = [
  { value: '', label: 'All' },
  { value: 'unread', label: 'Unread' },
  { value: 'read', label: 'Read' },
  { value: 'archived', label: 'Archived' },
];

function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace('www.', '');
  } catch {
    return url;
  }
}

function getFavicon(url: string): string {
  try {
    const { protocol, hostname } = new URL(url);
    return `${protocol}//${hostname}/favicon.ico`;
  } catch {
    return '';
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function StashPage() {
  const { token } = useAuth();
  const [links, setLinks] = useState<StashLink[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addUrl, setAddUrl] = useState('');
  const [addTags, setAddTags] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [addError, setAddError] = useState('');

  const fetchLinks = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const res = await listStashLinks(token, {
        status: statusFilter || undefined,
        limit: 100,
      });
      setLinks(res.links);
      setTotal(res.total);
    } catch (e) {
      console.error('Failed to load stash:', e);
    } finally {
      setIsLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => {
    fetchLinks();
  }, [fetchLinks]);

  const handleAdd = async () => {
    if (!token || !addUrl.trim()) return;
    setIsAdding(true);
    setAddError('');
    try {
      const tags = addTags.split(',').map((t) => t.trim()).filter(Boolean);
      await createStashLink(token, { url: addUrl.trim(), tags });
      setAddUrl('');
      setAddTags('');
      setShowAddModal(false);
      fetchLinks();
    } catch (e: any) {
      setAddError(e.message || 'Failed to save link');
    } finally {
      setIsAdding(false);
    }
  };

  const handleStatusChange = async (link: StashLink, newStatus: string) => {
    if (!token) return;
    try {
      const updated = await updateStashLink(token, link.id, { status: newStatus as any });
      setLinks((prev) => prev.map((l) => (l.id === link.id ? updated : l)));
    } catch {}
  };

  const handleDelete = async (linkId: string) => {
    if (!token) return;
    try {
      await deleteStashLink(token, linkId);
      setLinks((prev) => prev.filter((l) => l.id !== linkId));
      setTotal((prev) => prev - 1);
    } catch {}
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white lg:text-3xl">Stash</h1>
          <p className="text-xs text-gray-500 mt-0.5">{total} saved</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition"
        >
          <PlusIcon className="h-4 w-4" />
          Add
        </button>
      </div>

      {/* Status + tag filter tabs */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={`flex-shrink-0 rounded-full px-3 py-1 text-xs font-medium transition ${
              statusFilter === tab.value
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Links */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
        </div>
      ) : links.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-gray-800 bg-gray-900/30 p-10 text-center">
          <BookmarkIconSolid className="h-10 w-10 text-gray-700" />
          <p className="mt-3 text-sm text-gray-500">
            Nothing stashed yet — tap Add to save your first link
          </p>
        </div>
      ) : (
        <div className="max-w-full overflow-x-hidden space-y-2">
          {links.map((link) => (
            <LinkCard
              key={link.id}
              link={link}
              onStatusChange={handleStatusChange}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Add Modal */}
      <Modal
        open={showAddModal}
        onClose={() => {
          setShowAddModal(false);
          setAddUrl('');
          setAddTags('');
          setAddError('');
        }}
        title="Save a Link"
        size="sm"
        onOk={handleAdd}
        okText="Save to Stash"
        okDisabled={!addUrl.trim()}
        okLoading={isAdding}
        onCancel={() => {
          setShowAddModal(false);
          setAddUrl('');
          setAddTags('');
          setAddError('');
        }}
      >
        <div className="space-y-3">
          <div>
            <input
              type="url"
              placeholder="Paste a URL..."
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              autoFocus
            />
          </div>
          <div>
            <input
              type="text"
              placeholder="Tags (comma-separated, optional)"
              value={addTags}
              onChange={(e) => setAddTags(e.target.value)}
              className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          {addError && <p className="text-sm text-red-400">{addError}</p>}
        </div>
      </Modal>
    </div>
  );
}

function truncateTitle(text: string, max = 80): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + '…';
}

function LinkCard({
  link,
  onStatusChange,
  onDelete,
}: {
  link: StashLink;
  onStatusChange: (link: StashLink, status: string) => void;
  onDelete: (id: string) => void;
}) {
  const domain = getDomain(link.url);
  const favicon = getFavicon(link.url);
  const [favError, setFavError] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Prefer AI title over OG title
  const displayTitle = link.ai_title || link.title || domain;

  return (
    <div
      className={`w-full overflow-hidden rounded-xl border transition ${
        link.status === 'archived'
          ? 'border-gray-800 bg-gray-900/20 opacity-60'
          : 'border-gray-700/60 bg-gray-800/40'
      }`}
    >
      {/* Main content area — tappable */}
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block px-3.5 pt-3 pb-1"
      >
        {/* Title */}
        <p className={`text-[15px] font-semibold leading-snug line-clamp-2 ${
          link.status === 'read' ? 'text-gray-400' : 'text-white'
        }`}>
          {displayTitle}
        </p>

        {/* Source row: favicon + domain + time + issue number */}
        <div className="mt-1.5 flex items-center gap-1.5">
          {!favError ? (
            <img
              src={favicon}
              alt=""
              className="h-3.5 w-3.5 rounded-sm opacity-50"
              onError={() => setFavError(true)}
            />
          ) : (
            <LinkIcon className="h-3.5 w-3.5 text-gray-600" />
          )}
          <span className="text-xs text-gray-500 truncate">{domain}</span>
          <span className="text-xs text-gray-700">·</span>
          <span className="text-xs text-gray-600 flex-shrink-0">{timeAgo(link.created_at)}</span>
          <span className="text-xs text-gray-700">·</span>
          <span className="text-xs text-indigo-500/70 flex-shrink-0 font-mono">#{String(link.issue_number).padStart(4, '0')}</span>
        </div>
      </a>

      {/* AI Summary — always visible when present, collapsed to 2 lines */}
      {link.summary && (
        <div className="px-3.5 pt-1.5">
          <p
            onClick={() => setExpanded(!expanded)}
            className={`text-xs text-gray-400 leading-relaxed cursor-pointer ${
              expanded ? '' : 'line-clamp-2'
            }`}
          >
            {link.summary}
          </p>
        </div>
      )}

      {/* Tags */}
      {link.tags.length > 0 && (
        <div className="px-3.5 pt-1.5 flex flex-wrap gap-1">
          {link.tags.map(t => (
            <span key={t} className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-400/80">
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Action bar */}
      <div className="flex items-center border-t border-gray-700/40 mt-2">
        {link.status === 'unread' && (
          <button
            onClick={() => onStatusChange(link, 'read')}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-xs text-gray-500 hover:text-green-400 hover:bg-green-900/10 transition"
          >
            <CheckIcon className="h-3.5 w-3.5" />
            Read
          </button>
        )}
        {link.status !== 'archived' ? (
          <button
            onClick={() => onStatusChange(link, 'archived')}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-700/30 transition"
          >
            <ArchiveBoxIcon className="h-3.5 w-3.5" />
            Archive
          </button>
        ) : (
          <button
            onClick={() => onStatusChange(link, 'unread')}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-700/30 transition"
          >
            <BookmarkIconSolid className="h-3.5 w-3.5" />
            Restore
          </button>
        )}
        {confirmDelete ? (
          <>
            <button
              onClick={() => onDelete(link.id)}
              className="flex flex-1 items-center justify-center gap-1 py-2 text-xs text-red-400 bg-red-900/20 hover:bg-red-900/40 transition"
            >
              Sure?
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="flex flex-1 items-center justify-center py-2 text-xs text-gray-500 hover:text-gray-300 transition"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-xs text-gray-500 hover:text-red-400 hover:bg-red-900/10 transition"
          >
            <TrashIcon className="h-3.5 w-3.5" />
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
