"use client";

import { CaretDown, Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { NotificationEmail } from "@/lib/types";
import { Button } from "./Button";
import { Input } from "./Input";

export function AlertEmailSelect({
  emails,
  value,
  onChange,
  onEmailsUpdated,
}: {
  emails: NotificationEmail[];
  value: number | "";
  onChange: (id: number) => void;
  onEmailsUpdated?: () => void | Promise<void>;
}) {
  const verified = emails.filter((e) => e.verified);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = verified.find((e) => e.id === value);

  async function handleAddEmail(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const row = await api<NotificationEmail>("/api/auth/notification-emails", {
        method: "POST",
        body: JSON.stringify({ email: newEmail, label: label || null }),
      });
      setNewEmail("");
      setLabel("");
      setAdding(false);
      await onEmailsUpdated?.();
      setNotice("Verification email sent — check your inbox.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add email");
    } finally {
      setLoading(false);
    }
  }

  if (!verified.length && !adding) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">Add a verified email to receive price alerts.</p>
        <Button type="button" variant="secondary" size="sm" onClick={() => setAdding(true)}>
          <Plus className="size-4" />
          Add alert email
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <span className="font-data text-xs uppercase tracking-wider text-muted block">
        Alert email
      </span>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-11 w-full items-center justify-between gap-2 rounded-[var(--radius-md)] border border-border/70 bg-surface/80 px-3.5 text-left shadow-inner transition hover:border-accent/40"
        >
          <span className="min-w-0 truncate font-data text-sm text-ink">
            {selected
              ? `${selected.label ? `${selected.label} · ` : ""}${selected.email}`
              : "Choose email"}
          </span>
          <CaretDown
            className={`size-4 shrink-0 text-muted transition ${open ? "rotate-180" : ""}`}
            aria-hidden
          />
        </button>
        {open ? (
          <ul
            className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-[var(--radius-md)] border border-border/70 bg-surface p-1 shadow-xl"
            role="listbox"
          >
            {verified.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={row.id === value}
                  onClick={() => {
                    onChange(row.id);
                    setOpen(false);
                  }}
                  className={`w-full rounded-[var(--radius-sm)] px-3 py-2.5 text-left font-data text-sm transition hover:bg-accent/10 ${
                    row.id === value ? "bg-accent/15 text-accent" : "text-ink"
                  }`}
                >
                  {row.label ? (
                    <span className="block text-xs uppercase tracking-wide text-muted">
                      {row.label}
                    </span>
                  ) : null}
                  <span className="block truncate">{row.email}</span>
                </button>
              </li>
            ))}
            <li className="border-t border-border/50 mt-1 pt-1">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  setAdding(true);
                }}
                className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2.5 font-data text-sm text-accent hover:bg-accent/10"
              >
                <Plus className="size-4" />
                Add new email
              </button>
            </li>
          </ul>
        ) : null}
      </div>

      {adding ? (
        <form onSubmit={handleAddEmail} className="space-y-3 rounded-[var(--radius-md)] border border-border/50 p-3">
          <Input
            label="Email"
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <Input
            label="Label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Work, personal…"
          />
          {error ? <p className="text-xs text-error">{error}</p> : null}
          {notice ? <p className="text-xs text-accent">{notice}</p> : null}
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={loading}>
              Send verification
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
          <p className="text-xs text-muted">Check your inbox to verify before alerts can send.</p>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="font-data text-xs text-accent hover:underline"
        >
          + Add another email
        </button>
      )}
    </div>
  );
}
