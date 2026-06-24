"use client";

import { X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { parseDollarsToCents } from "@/lib/format";
import type { NotificationEmail, Watch } from "@/lib/types";
import { AlertEmailSelect } from "./AlertEmailSelect";
import { Button } from "./Button";
import { WatchAlertFields } from "./WatchAlertFields";

export function WatchEditModal({
  watch,
  notificationEmails,
  onClose,
  onSaved,
  onEmailsUpdated,
}: {
  watch: Watch;
  notificationEmails: NotificationEmail[];
  onClose: () => void;
  onSaved: (watch: Watch) => void;
  onEmailsUpdated?: () => void | Promise<void>;
}) {
  const verified = notificationEmails.filter((e) => e.verified);
  const [emailId, setEmailId] = useState<number | "">(
    watch.notification_email_id ??
      verified.find((e) => e.email === watch.email)?.id ??
      verified[0]?.id ??
      "",
  );
  const [targetPrice, setTargetPrice] = useState(
    watch.target_price_cents != null ? (watch.target_price_cents / 100).toFixed(2) : "",
  );
  const [notifyAnyDrop, setNotifyAnyDrop] = useState(Boolean(watch.notify_on_any_drop));
  const [minDropDollars, setMinDropDollars] = useState(
    watch.min_drop_cents != null ? (watch.min_drop_cents / 100).toFixed(2) : "",
  );
  const [minDropPercent, setMinDropPercent] = useState(
    watch.min_drop_percent != null ? String(watch.min_drop_percent) : "",
  );
  const [enabled, setEnabled] = useState(Boolean(watch.enabled));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!emailId) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await api<Watch>(`/api/watches/${watch.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          notification_email_id: emailId,
          target_price_cents: parseDollarsToCents(targetPrice),
          notify_on_any_drop: notifyAnyDrop,
          min_drop_cents: parseDollarsToCents(minDropDollars),
          min_drop_percent: minDropPercent ? Number(minDropPercent) : null,
          enabled,
        }),
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save alert");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div
        role="dialog"
        aria-labelledby="watch-edit-title"
        className="w-full max-w-lg holo-panel-strong rounded-[var(--radius-xl)] border border-border/60 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border/50 px-5 py-4">
          <h2 id="watch-edit-title" className="font-display text-lg font-bold text-ink">
            Edit price alert
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--radius-sm)] p-2 text-muted hover:text-ink hover:bg-surface/80"
            aria-label="Close"
          >
            <X className="size-5" />
          </button>
        </div>
        <form onSubmit={handleSave} className="p-5 space-y-5">
          <AlertEmailSelect
            emails={notificationEmails}
            value={emailId}
            onChange={setEmailId}
            onEmailsUpdated={onEmailsUpdated}
          />
          <WatchAlertFields
            targetPrice={targetPrice}
            onTargetPriceChange={setTargetPrice}
            notifyAnyDrop={notifyAnyDrop}
            onNotifyAnyDropChange={setNotifyAnyDrop}
            minDropDollars={minDropDollars}
            onMinDropDollarsChange={setMinDropDollars}
            minDropPercent={minDropPercent}
            onMinDropPercentChange={setMinDropPercent}
          />
          <label className="flex items-center gap-2.5 font-data text-xs text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="size-4 rounded border-border accent-primary"
            />
            Alert active
          </label>
          {error ? <p className="text-sm text-error">{error}</p> : null}
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={loading} disabled={!emailId}>
              Save changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
