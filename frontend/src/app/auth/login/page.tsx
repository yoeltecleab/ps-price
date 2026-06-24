"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { safeRedirectPath } from "@/lib/safeRedirect";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

function bufferToBase64url(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlToBuffer(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

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
      const credential = (await navigator.credentials.get({
        publicKey: {
          challenge: base64urlToBuffer(options.challenge as string),
          timeout: (options.timeout as number) || 60000,
          rpId: options.rpId as string,
          userVerification: "preferred",
          allowCredentials: Array.isArray(options.allowCredentials)
            ? (options.allowCredentials as { id: string; type: string; transports?: string[] }[]).map(
                (c) => ({
                  type: "public-key" as const,
                  id: base64urlToBuffer(c.id),
                  transports: c.transports as AuthenticatorTransport[] | undefined,
                }),
              )
            : undefined,
        },
      })) as PublicKeyCredential | null;
      if (!credential) throw new Error("Passkey sign-in cancelled");
      const response = credential.response as AuthenticatorAssertionResponse;
      await api("/api/auth/passkey/login/verify", {
        method: "POST",
        body: JSON.stringify({
          credential: {
            id: credential.id,
            rawId: bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
              clientDataJSON: bufferToBase64url(response.clientDataJSON),
              authenticatorData: bufferToBase64url(response.authenticatorData),
              signature: bufferToBase64url(response.signature),
              userHandle: response.userHandle
                ? bufferToBase64url(response.userHandle)
                : null,
            },
          },
        }),
      });
      await refresh();
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Passkey sign-in failed");
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
        <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
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
