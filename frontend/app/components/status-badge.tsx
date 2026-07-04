/**
 * Status badge component.
 */

interface StatusBadgeProps {
  status: 'online' | 'offline' | 'loading';
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const colors = {
    online: 'bg-success/15 text-success',
    offline: 'bg-destructive/15 text-destructive',
    loading: 'bg-warning/15 text-warning',
  };

  return (
    <span className={`px-2 py-1 rounded-full text-sm ${colors[status]}`}>
      {label || status}
    </span>
  );
}

