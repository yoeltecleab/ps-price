"use client";

import { BookmarkSimple, Bell } from "@phosphor-icons/react";
import { useState } from "react";
import type { NotificationEmail } from "@/lib/types";
import { AlertEmailSelect } from "./AlertEmailSelect";
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
  onEmailsUpdated,
}: {
  count: number;
  onAddToLibrary?: () => void;
  onDeployWatch: (notificationEmailId: number) => void;
  libraryLoading?: boolean;
  watchLoading?: boolean;
  showLibrary?: boolean;
  showWatch?: boolean;
  notificationEmails?: NotificationEmail[];
  onEmailsUpdated?: () => void | Promise<void>;
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
          <AlertEmailSelect
            emails={notificationEmails}
            value={emailId}
            onChange={setEmailId}
            onEmailsUpdated={onEmailsUpdated}
          />
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
