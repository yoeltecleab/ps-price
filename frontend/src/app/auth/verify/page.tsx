"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { safeRedirectPath } from "@/lib/safeRedirect";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/Button";

export default function VerifyEmailPage() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");
  const next = safeRedirectPath(params.get("next"), "/");
  const { user, refresh } = useAuth();
  const [message, setMessage] = useState("Checking verification status…");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    void (async () => {
      try {
        await api("/api/auth/verify-email", {
          method: "POST",
          body: JSON.stringify({ token }),
        });
        await refresh();
        setMessage("Email verified. Redirecting…");
        router.replace(next);
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Verification failed");
      }
    })();
  }, [token, refresh, router, next]);

  async function resend() {
    setLoading(true);
    try {
      await api("/api/auth/resend-verification", { method: "POST" });
      setMessage("Verification email sent. Check your inbox.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not resend");
    } finally {
      setLoading(false);
    }
  }

  if (token) {
    return (
      <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 text-center">
        <p className="text-muted">{message}</p>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 space-y-4 text-center">
      <h1 className="font-display text-2xl font-bold text-ink">Verify your email</h1>
      <p className="text-sm text-muted">
        {user?.email_verified
          ? "Your email is verified."
          : `We sent a verification link to ${user?.email || "your inbox"}.`}
      </p>
      {!user?.email_verified ? (
        <Button onClick={resend} loading={loading}>
          Resend verification email
        </Button>
      ) : (
        <Button onClick={() => router.push(next)}>Continue</Button>
      )}
    </div>
  );
}
