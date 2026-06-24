"use client";

import { useState } from "react";
import { BookmarkSimple, Bell } from "@phosphor-icons/react";
import Link from "next/link";
import type { NotificationEmail } from "@/lib/types";
import { Button } from "./Button";

export function BulkActionBar({
  count,
  onAddToLibrary,
  onDeployWatch,
  libraryLoading,
  watchLoading,
  showLibrary = true,
  showWatch = true,
  notificationEmails = [],
}: {
  count: number;
  onAddToLibrary?: () => void;
  onDeployWatch: (notificationEmailId: number) => void;
  libraryLoading?: boolean;
  watchLoading?: boolean;
  showLibrary?: boolean;
  showWatch?: boolean;
  notificationEmails?: NotificationEmail[];
}) {
  const verified = notificationEmails.filter((e) => e.verified);
  const [emailId, setEmailId] = useState<number | "">(
    verified.find((e) => e.is_primary)?.id ?? verified[0]?.id ?? "",
  );

  if (count === 0) return null;

  return (
    <div className="sticky bottom-4 z-40 holo-panel-strong rounded-[var(--radius-xl)] border border-accent/30 p-4 flex flex-col sm:flex-row sm:items-end gap-3 shadow-2xl">
      <p className="font-data text-xs uppercase tracking-widest text-accent shrink-0">
        {count} selected
      </p>
      {showWatch ? (
        <div className="flex-1 min-w-0">
          {verified.length ? (
            <label className="block">
              <span className="font-data text-xs uppercase tracking-wider text-muted mb-2 block">
                Alert email
              </span>
              <select
                value={emailId}
                onChange={(e) => setEmailId(Number(e.target.value))}
                className="h-10 w-full rounded-[var(--radius-sm)] holo-panel px-3 font-data text-sm text-ink"
              >
                {verified.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label ? `${row.label} · ` : ""}
                    {row.email}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="text-sm text-muted">
              <Link href="/account" className="text-accent hover:underline">
                Add a verified notification email
              </Link>{" "}
              to deploy watches.
            </p>
          )}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2 shrink-0">
        {showLibrary && onAddToLibrary ? (
          <Button variant="secondary" onClick={onAddToLibrary} loading={libraryLoading}>
            <BookmarkSimple className="size-4" />
            Add to library
          </Button>
        ) : null}
        {showWatch ? (
          <Button
            onClick={() => emailId && onDeployWatch(emailId)}
            loading={watchLoading}
            disabled={!emailId}
          >
            <Bell className="size-4" weight="fill" />
            Deploy watch
          </Button>
        ) : null}
      </div>
    </div>
  );
}
