import type { StatusKind } from '../api/types';

interface StatusBadgeProps {
  status: StatusKind | string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  return <span className={`status-badge status-${normalized}`}>{label || status}</span>;
}
