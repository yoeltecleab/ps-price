"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { safeRedirectPath } from "@/lib/safeRedirect";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  buildLoginOptions,
  credentialToJson,
  isPasskeyUserCancelled,
} from "@/lib/webauthn";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeRedirectPath(params.get("next"), "/");
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      await refresh();
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handlePasskey() {
    setLoading(true);
    setError(null);
    try {
      const options = await api<Record<string, unknown>>("/api/auth/passkey/login/options", {
        method: "POST",
        body: JSON.stringify({ email: email || null }),
      });
      const credential = (await navigator.credentials.get(
        buildLoginOptions(options),
      )) as PublicKeyCredential | null;
      if (!credential) return;
      await api("/api/auth/passkey/login/verify", {
        method: "POST",
        body: JSON.stringify({ credential: credentialToJson(credential) }),
      });
      await refresh();
      router.push(next);
    } catch (err) {
      if (!isPasskeyUserCancelled(err)) {
        setError(err instanceof Error ? err.message : "Passkey sign-in failed");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-muted">Access your library, alerts, and notification emails.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error ? <p className="text-sm text-error">{error}</p> : null}
        <Button type="submit" className="w-full" loading={loading}>
          Sign in
        </Button>
      </form>
      <Button type="button" variant="secondary" className="w-full" onClick={handlePasskey} loading={loading}>
        Sign in with passkey
      </Button>
      <p className="text-sm text-muted text-center">
        No account?{" "}
        <Link href={`/auth/register?next=${encodeURIComponent(next)}`} className="text-accent hover:underline">
          Create one
        </Link>
      </p>
      <p className="text-center">
        <Link href="/auth/forgot-password" className="text-xs text-muted hover:text-accent">
          Forgot password?
        </Link>
      </p>
    </div>
  );
}
