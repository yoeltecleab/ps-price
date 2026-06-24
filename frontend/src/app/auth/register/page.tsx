"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { safeRedirectPath } from "@/lib/safeRedirect";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  buildRegistrationOptions,
  credentialToJson,
  isPasskeyUserCancelled,
  suggestPasskeyName,
} from "@/lib/webauthn";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type SignupMode = "password" | "passkey";

export default function RegisterPage() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeRedirectPath(params.get("next"), "/auth/verify");
  const { refresh } = useAuth();
  const [mode, setMode] = useState<SignupMode>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          display_name: displayName || null,
        }),
      });
      await refresh();
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handlePasskeySignup() {
    setLoading(true);
    setError(null);
    try {
      const options = await api<Record<string, unknown>>("/api/auth/register/passkey/options", {
        method: "POST",
        body: JSON.stringify({
          email,
          display_name: displayName || null,
        }),
      });
      const credential = (await navigator.credentials.create(
        buildRegistrationOptions(options),
      )) as PublicKeyCredential | null;
      if (!credential) return;
      await api("/api/auth/register/passkey/verify", {
        method: "POST",
        body: JSON.stringify({
          credential: credentialToJson(credential),
          friendly_name: suggestPasskeyName(credential),
        }),
      });
      await refresh();
      router.push(next);
    } catch (err) {
      if (!isPasskeyUserCancelled(err)) {
        setError(err instanceof Error ? err.message : "Passkey sign-up failed");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">Create account</h1>
        <p className="mt-2 text-sm text-muted">Track games, deploy price watches, and manage alert emails.</p>
      </div>

      <div className="grid grid-cols-2 gap-2 p-1 rounded-[var(--radius-md)] bg-surface/60 border border-border/50">
        <button
          type="button"
          onClick={() => setMode("password")}
          className={`rounded-[var(--radius-sm)] py-2 font-data text-xs uppercase tracking-wider transition ${
            mode === "password" ? "bg-accent/20 text-accent" : "text-muted hover:text-ink"
          }`}
        >
          Email & password
        </button>
        <button
          type="button"
          onClick={() => setMode("passkey")}
          className={`rounded-[var(--radius-sm)] py-2 font-data text-xs uppercase tracking-wider transition ${
            mode === "passkey" ? "bg-accent/20 text-accent" : "text-muted hover:text-ink"
          }`}
        >
          Passkey only
        </button>
      </div>

      <div className="space-y-4">
        <Input label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />

        {mode === "password" ? (
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="At least 10 characters"
            />
            {error ? <p className="text-sm text-error">{error}</p> : null}
            <Button type="submit" className="w-full" loading={loading}>
              Create account
            </Button>
          </form>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted">
              Create your account with Face ID, Touch ID, or a security key. You can add a password later in account settings.
            </p>
            {error ? <p className="text-sm text-error">{error}</p> : null}
            <Button type="button" className="w-full" loading={loading} onClick={handlePasskeySignup} disabled={!email}>
              Create account with passkey
            </Button>
          </div>
        )}
      </div>

      <p className="text-sm text-muted text-center">
        Already have an account?{" "}
        <Link href="/auth/login" className="text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
