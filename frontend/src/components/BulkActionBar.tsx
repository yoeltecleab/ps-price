"use client";

import { useState } from "react";
import { BookmarkSimple, Bell } from "@phosphor-icons/react";
import { Button } from "./Button";
import { Input } from "./Input";

export function BulkActionBar({
  count,
  onAddToLibrary,
  onDeployWatch,
  libraryLoading,
  watchLoading,
  showLibrary = true,
  showWatch = true,
}: {
  count: number;
  onAddToLibrary?: () => void;
  onDeployWatch: (email: string) => void;
  libraryLoading?: boolean;
  watchLoading?: boolean;
  showLibrary?: boolean;
  showWatch?: boolean;
}) {
  const [email, setEmail] = useState("");

  if (count === 0) return null;

  return (
    <div className="sticky bottom-4 z-40 holo-panel-strong rounded-[var(--radius-xl)] border border-accent/30 p-4 flex flex-col sm:flex-row sm:items-end gap-3 shadow-2xl">
      <p className="font-data text-xs uppercase tracking-widest text-accent shrink-0">
        {count} selected
      </p>
      {showWatch ? (
        <div className="flex-1 min-w-0">
          <Input
            label="Alert email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
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
            onClick={() => onDeployWatch(email.trim())}
            loading={watchLoading}
            disabled={!email.trim()}
          >
            <Bell className="size-4" weight="fill" />
            Deploy watch
          </Button>
        ) : null}
      </div>
    </div>
  );
}
