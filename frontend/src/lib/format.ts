export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
  });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function centsToDisplay(cents: number | null, currency = "USD"): string {
  if (cents === null) return "—";
  if (cents === 0) return "Free";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}

export function parseDollarsToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = parseFloat(trimmed.replace(/[^0-9.]/g, ""));
  if (Number.isNaN(parsed)) return null;
  return Math.round(parsed * 100);
}

export function discountPercent(
  current: number | null,
  original: number | null,
): number | null {
  if (!current || !original || original <= current) return null;
  return Math.round(((original - current) / original) * 100);
}
