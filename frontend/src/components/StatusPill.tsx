"use client";

import { useEffect, useState } from "react";

export function StatusPill() {
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    fetch("/healthz")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, []);

  if (status === "loading") {
    return (
      <span className="font-data text-[12px] uppercase tracking-wider text-muted px-3 py-1.5 rounded-full holo-panel">
        Syncing…
      </span>
    );
  }

  return (
    <span
      className={[
        "font-data text-[12px] uppercase tracking-wider px-3 py-1.5 rounded-full holo-panel flex items-center gap-2",
        status === "ok" ? "text-success" : "text-error",
      ].join(" ")}
    >
      <span
        className={[
          "size-1.5 rounded-full",
          status === "ok" ? "bg-success animate-pulse" : "bg-error",
        ].join(" ")}
      />
      {status === "ok" ? "Live feed" : "Offline"}
    </span>
  );
}
