'use client';

/**
 * Scheduled tasks bottom sheet — mobile-first.
 *
 * Opens from the clock icon in the workspace chat header. List view with
 * enabled-dot toggles; tapping a row (or +) slides to an edit form using
 * preset pills + native iOS time/day pickers. A live "Next:" preview is
 * computed server-side by the same croniter that fires the task.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeftIcon,
  BoltIcon,
  ChevronRightIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '@/lib/auth';
import { useToast } from '@/hooks/use-toast';
import {
  ScheduledTask,
  createScheduledTask,
  deleteScheduledTask,
  getScheduledTasks,
  previewSchedule,
  runScheduledTaskNow,
  updateScheduledTask,
} from '@/lib/api';

type Preset = 'hourly' | 'daily' | 'weekdays' | 'weekly' | 'cron';

const PRESETS: { id: Preset; label: string }[] = [
  { id: 'hourly', label: 'Hourly' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekdays', label: 'Weekdays' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'cron', label: 'Cron' },
];

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function buildCron(preset: Preset, time: string, weekday: number, custom: string): string {
  const [h, m] = time.split(':').map((n) => parseInt(n, 10));
  switch (preset) {
    case 'hourly':
      return '0 * * * *';
    case 'daily':
      return `${m} ${h} * * *`;
    case 'weekdays':
      return `${m} ${h} * * 1-5`;
    case 'weekly':
      return `${m} ${h} * * ${weekday}`;
    case 'cron':
      return custom.trim();
  }
}

/** Best-effort reverse of buildCron so editing shows the right preset. */
function parseCron(cron: string): { preset: Preset; time: string; weekday: number } {
  const parts = cron.trim().split(/\s+/);
  const pad = (n: string) => n.padStart(2, '0');
  if (parts.length === 5) {
    const [m, h, dom, mon, dow] = parts;
    const timeOk = /^\d+$/.test(m) && /^\d+$/.test(h);
    if (cron === '0 * * * *') return { preset: 'hourly', time: '09:00', weekday: 1 };
    if (timeOk && dom === '*' && mon === '*') {
      const time = `${pad(h)}:${pad(m)}`;
      if (dow === '*') return { preset: 'daily', time, weekday: 1 };
      if (dow === '1-5') return { preset: 'weekdays', time, weekday: 1 };
      if (/^\d$/.test(dow)) return { preset: 'weekly', time, weekday: parseInt(dow, 10) };
    }
  }
  return { preset: 'cron', time: '09:00', weekday: 1 };
}

function humanSchedule(task: ScheduledTask): string {
  const { preset, time, weekday } = parseCron(task.cron_expression);
  switch (preset) {
    case 'hourly': return 'Every hour';
    case 'daily': return `Daily at ${time}`;
    case 'weekdays': return `Weekdays at ${time}`;
    case 'weekly': return `${WEEKDAYS[weekday]}s at ${time}`;
    default: return task.cron_expression;
  }
}

function countdown(iso: string | null): string {
  if (!iso) return 'paused';
  const diffMs = new Date(iso + 'Z').getTime() - Date.now();
  if (diffMs <= 0) return 'now';
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `in ${mins}m`;
  if (mins < 48 * 60) return `in ${Math.round(mins / 60)}h`;
  return `in ${Math.round(mins / (60 * 24))}d`;
}

interface Props {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

export default function SchedulesSheet({ workspaceId, open, onClose }: Props) {
  const { token, user } = useAuth();
  const { toast } = useToast();
  const tz =
    user?.settings?.timezone ||
    (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC');

  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [editing, setEditing] = useState<ScheduledTask | 'new' | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [preset, setPreset] = useState<Preset>('daily');
  const [time, setTime] = useState('09:00');
  const [weekday, setWeekday] = useState(1);
  const [customCron, setCustomCron] = useState('0 9 * * *');
  const [wakeAgent, setWakeAgent] = useState(true);
  const [preview, setPreview] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!token) return;
    getScheduledTasks(token, workspaceId)
      .then((res) => setTasks(res.tasks))
      .catch(() => {});
  }, [token, workspaceId]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  // Live next-run preview from the server's croniter
  useEffect(() => {
    if (!open || editing === null || !token) return;
    const cron = buildCron(preset, time, weekday, customCron);
    if (!cron) return;
    const t = setTimeout(() => {
      previewSchedule(token, cron, tz)
        .then((res) => {
          const next = res.next_runs[0];
          if (next) {
            setPreview(
              new Date(next + 'Z').toLocaleString(undefined, {
                weekday: 'short', hour: 'numeric', minute: '2-digit',
              })
            );
          }
        })
        .catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(t);
  }, [open, editing, preset, time, weekday, customCron, token, tz]);

  const openEditor = (task: ScheduledTask | 'new') => {
    if (task === 'new') {
      setName('');
      setPrompt('');
      setPreset('daily');
      setTime('09:00');
      setWeekday(1);
      setCustomCron('0 9 * * *');
      setWakeAgent(true);
    } else {
      setName(task.name);
      setPrompt(task.prompt);
      const parsed = parseCron(task.cron_expression);
      setPreset(parsed.preset);
      setTime(parsed.time);
      setWeekday(parsed.weekday);
      setCustomCron(task.cron_expression);
      setWakeAgent(task.wake_agent);
    }
    setPreview(null);
    setEditing(task);
  };

  const save = async () => {
    if (!token || !name.trim() || !prompt.trim()) return;
    setIsBusy(true);
    const data = {
      name: name.trim(),
      prompt: prompt.trim(),
      cron_expression: buildCron(preset, time, weekday, customCron),
      timezone: tz,
      wake_agent: wakeAgent,
    };
    try {
      if (editing === 'new') {
        await createScheduledTask(token, workspaceId, data);
      } else if (editing) {
        await updateScheduledTask(token, workspaceId, editing.id, data);
      }
      setEditing(null);
      refresh();
    } catch (e) {
      toast({ title: 'Could not save schedule', description: String((e as Error).message || e), variant: 'destructive' });
    } finally {
      setIsBusy(false);
    }
  };

  const toggle = async (task: ScheduledTask) => {
    if (!token) return;
    setTasks((ts) => ts.map((t) => (t.id === task.id ? { ...t, enabled: !t.enabled } : t)));
    try {
      await updateScheduledTask(token, workspaceId, task.id, { enabled: !task.enabled });
      refresh();
    } catch {
      refresh();
    }
  };

  const remove = async () => {
    if (!token || !editing || editing === 'new') return;
    setIsBusy(true);
    try {
      await deleteScheduledTask(token, workspaceId, editing.id);
      setEditing(null);
      refresh();
    } finally {
      setIsBusy(false);
    }
  };

  const runNow = async () => {
    if (!token || !editing || editing === 'new') return;
    setIsBusy(true);
    try {
      await runScheduledTaskNow(token, workspaceId, editing.id);
      toast({ title: 'Fired', description: 'The prompt was delivered to the agent.' });
      setEditing(null);
      refresh();
    } catch (e) {
      toast({ title: 'Could not run task', description: String((e as Error).message || e), variant: 'destructive' });
    } finally {
      setIsBusy(false);
    }
  };

  if (!open) return null;

  const inputCls =
    'w-full rounded-lg border border-border-strong bg-surface2 px-3 py-2.5 text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none';

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Sheet */}
      <div className="relative flex max-h-[85vh] w-full flex-col rounded-t-2xl border border-border bg-card shadow-xl sm:max-w-lg sm:rounded-2xl">
        {/* Grabber (mobile affordance) */}
        <div className="flex justify-center pt-2 sm:hidden">
          <div className="h-1 w-10 rounded-full bg-border-strong" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3">
          {editing !== null ? (
            <button onClick={() => setEditing(null)} className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
              <ArrowLeftIcon className="h-5 w-5" />
              <span className="text-sm">Schedules</span>
            </button>
          ) : (
            <h2 className="text-lg font-semibold text-foreground">Schedules</h2>
          )}
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-contain px-4 pb-6">
          {editing === null ? (
            <>
              {/* List */}
              {tasks.length === 0 ? (
                <p className="py-10 text-center text-sm text-faint">
                  No schedules yet. Recurring prompts fire into this chat and your agent picks them up automatically.
                </p>
              ) : (
                <div className="space-y-2">
                  {tasks.map((task) => (
                    <div key={task.id} className="flex items-center gap-3 rounded-xl border border-border bg-surface2/60 px-3 py-3">
                      {/* Enabled dot */}
                      <button
                        onClick={() => toggle(task)}
                        aria-label={task.enabled ? 'Pause schedule' : 'Resume schedule'}
                        className="flex h-8 w-8 shrink-0 items-center justify-center"
                      >
                        <span className={`h-3.5 w-3.5 rounded-full ${task.enabled ? 'bg-green-500' : 'bg-border-strong'}`} />
                      </button>
                      {/* Row body — tap to edit */}
                      <button onClick={() => openEditor(task)} className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left">
                        <div className="min-w-0">
                          <p className={`truncate font-medium ${task.enabled ? 'text-foreground' : 'text-muted-foreground'}`}>{task.name}</p>
                          <p className="truncate text-xs text-faint">
                            {humanSchedule(task)}
                            {task.enabled ? ` · ${countdown(task.next_run_at)}` : ' · paused'}
                          </p>
                        </div>
                        <ChevronRightIcon className="h-4 w-4 shrink-0 text-faint" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <button
                onClick={() => openEditor('new')}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong py-3 text-sm text-muted-foreground hover:border-primary hover:text-foreground"
              >
                <PlusIcon className="h-4 w-4" /> New schedule
              </button>
            </>
          ) : (
            <>
              {/* Editor */}
              <div className="space-y-4">
                <input
                  type="text"
                  placeholder="Name — e.g. Morning report"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className={inputCls}
                />
                <textarea
                  placeholder="What should the agent do when this fires? Written exactly like a chat message."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  className={`${inputCls} resize-none`}
                />

                {/* Preset pills */}
                <div className="flex gap-1.5">
                  {PRESETS.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setPreset(p.id)}
                      className={`flex-1 rounded-lg px-1 py-2 text-xs font-medium transition ${
                        preset === p.id
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-surface2 text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>

                {/* Preset-specific controls (native pickers on iOS) */}
                {preset === 'weekly' && (
                  <select value={weekday} onChange={(e) => setWeekday(parseInt(e.target.value, 10))} className={inputCls}>
                    {WEEKDAYS.map((d, i) => (
                      <option key={d} value={i}>{d}</option>
                    ))}
                  </select>
                )}
                {(preset === 'daily' || preset === 'weekdays' || preset === 'weekly') && (
                  <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={inputCls} />
                )}
                {preset === 'cron' && (
                  <input
                    type="text"
                    value={customCron}
                    onChange={(e) => setCustomCron(e.target.value)}
                    placeholder="0 9 * * 1-5"
                    className={`${inputCls} font-mono`}
                  />
                )}

                {preview && <p className="text-xs text-faint">Next: {preview} ({tz})</p>}

                {/* Wake agent */}
                <label className="flex items-center justify-between rounded-xl border border-border bg-surface2/60 px-3 py-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">Wake agent if stopped</p>
                    <p className="text-xs text-faint">Otherwise the message waits until the agent is next running</p>
                  </div>
                  <input type="checkbox" checked={wakeAgent} onChange={(e) => setWakeAgent(e.target.checked)} className="h-5 w-5 accent-[var(--primary,#6366f1)]" />
                </label>

                <button
                  onClick={save}
                  disabled={isBusy || !name.trim() || !prompt.trim()}
                  className="w-full rounded-xl bg-primary py-3 font-medium text-primary-foreground disabled:opacity-50"
                >
                  {editing === 'new' ? 'Create schedule' : 'Save changes'}
                </button>

                {editing !== 'new' && (
                  <div className="flex gap-2">
                    <button
                      onClick={runNow}
                      disabled={isBusy}
                      className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-border-strong py-3 text-sm text-foreground disabled:opacity-50"
                    >
                      <BoltIcon className="h-4 w-4" /> Run now
                    </button>
                    <button
                      onClick={remove}
                      disabled={isBusy}
                      className="flex items-center justify-center gap-2 rounded-xl border border-red-500/40 px-4 py-3 text-sm text-red-400 disabled:opacity-50"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
