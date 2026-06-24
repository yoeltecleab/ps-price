"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Notification } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Skeleton } from "@/components/Skeleton";

const statusVariant = (
  status: string,
): "success" | "error" | "warning" | "default" => {
  if (status === "sent") return "success";
  if (status === "failed") return "error";
  if (status === "skipped") return "warning";
  return "default";
};

export default function NotificationsPage() {
  const { user, loading: authLoading, requireVerified } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<Notification[]>("/api/notifications?limit=100");
      setNotifications(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load activity");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user?.email_verified) {
      requireVerified("/notifications");
      setLoading(false);
      return;
    }
    void load();
  }, [authLoading, user, load, requireVerified]);

  function toggleSelect(id: number, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function deleteOne(id: number) {
    try {
      await api(`/api/notifications/${id}`, { method: "DELETE" });
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function deleteSelected() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setDeleting(true);
    try {
      await api("/api/notifications/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ ids }),
      });
      setNotifications((prev) => prev.filter((n) => !ids.includes(n.id)));
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk delete failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <header className="mb-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Activity log</h1>
          <p className="mt-1 text-sm text-muted">
            Notification attempts and delivery status.
          </p>
        </div>
        {selected.size > 0 ? (
          <Button variant="secondary" onClick={deleteSelected} loading={deleting}>
            <Trash2 className="size-4" />
            Remove {selected.size} selected
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          className="mb-4 rounded-[var(--radius-md)] border border-error/30 bg-error/10 px-4 py-3 text-sm text-error"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="grid gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No activity yet"
          description="When price watches trigger or test emails are sent, they appear here."
          actionLabel="Set up a watch"
          actionHref="/watches"
        />
      ) : (
        <ul className="grid gap-3" role="list">
          {notifications.map((n) => (
            <li
              key={n.id}
              className={[
                "p-4 rounded-[var(--radius-lg)] bg-surface border border-border animate-fade-in",
                selected.has(n.id) ? "ring-2 ring-accent/40" : "",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-4">
                <label className="flex items-start gap-3 min-w-0 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected.has(n.id)}
                    onChange={(e) => toggleSelect(n.id, e.target.checked)}
                    className="mt-1 size-4 accent-accent shrink-0"
                    aria-label={`Select notification ${n.id}`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">{n.subject}</p>
                    <p className="mt-1 text-xs text-muted">
                      {n.game_name ?? "System"} · {n.email}
                    </p>
                    <p className="mt-2 text-xs text-muted line-clamp-2">{n.body}</p>
                    {n.error ? (
                      <p className="mt-2 text-xs text-error">{n.error}</p>
                    ) : null}
                  </div>
                </label>
                <div className="shrink-0 flex flex-col items-end gap-2">
                  <Badge variant={statusVariant(n.status)}>{n.status}</Badge>
                  <span className="text-xs text-muted">{formatDateTime(n.created_at)}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteOne(n.id)}
                    aria-label="Remove notification"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
