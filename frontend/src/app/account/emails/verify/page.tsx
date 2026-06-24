"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/Button";

export default function VerifyNotificationEmailPage() {
  const params = useSearchParams();
  const emailId = Number(params.get("id"));
  const token = params.get("token") || "";
  const [message, setMessage] = useState("Verifying notification email…");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (!emailId || !token) {
      setMessage("Invalid verification link.");
      return;
    }
    void (async () => {
      try {
        await api(`/api/auth/notification-emails/verify-public?id=${emailId}`, {
          method: "POST",
          body: JSON.stringify({ token }),
        });
        setOk(true);
        setMessage("Notification email verified.");
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Verification failed");
      }
    })();
  }, [emailId, token]);

  return (
    <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 space-y-4 text-center">
      <h1 className="font-display text-2xl font-bold text-ink">Email verification</h1>
      <p className="text-sm text-muted">{message}</p>
      {ok ? (
        <Link href="/account">
          <Button>Back to account</Button>
        </Link>
      ) : null}
    </div>
  );
}
