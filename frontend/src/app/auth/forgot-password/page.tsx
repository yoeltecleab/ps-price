"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setUnknown(false);
    try {
      const result = await api<{ sent: boolean }>("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (result.sent) {
        setSent(true);
      } else {
        setUnknown(true);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 space-y-6">
      <h1 className="font-display text-2xl font-bold text-ink">Reset password</h1>
      {sent ? (
        <p className="text-sm text-muted">A reset link was sent to {email}.</p>
      ) : unknown ? (
        <p className="text-sm text-muted">No account found for that email address.</p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <Button type="submit" className="w-full" loading={loading}>
            Send reset link
          </Button>
        </form>
      )}
      <Link href="/auth/login" className="text-sm text-accent hover:underline">
        Back to sign in
      </Link>
    </div>
  );
}
