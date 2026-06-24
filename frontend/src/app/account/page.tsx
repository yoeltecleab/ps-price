"use client";

import Link from "next/link";
import { useState } from "react";
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

export default function AccountPage() {
  const { user, notificationEmails, refresh, signOut } = useAuth();
  const [newEmail, setNewEmail] = useState("");
  const [label, setLabel] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!user) {
    return (
      <div className="text-center py-20">
        <p className="text-muted mb-4">Sign in to manage your account.</p>
        <Link href="/auth/login?next=/account">
          <Button>Sign in</Button>
        </Link>
      </div>
    );
  }

  async function addEmail(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      await api("/api/auth/notification-emails", {
        method: "POST",
        body: JSON.stringify({ email: newEmail, label: label || null }),
      });
      setNewEmail("");
      setLabel("");
      setMessage("Verification email sent.");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to add email");
    } finally {
      setLoading(false);
    }
  }

  async function setPrimary(id: number) {
    await api(`/api/auth/notification-emails/${id}/primary`, { method: "PATCH" });
    await refresh();
  }

  async function removeEmail(id: number) {
    await api(`/api/auth/notification-emails/${id}`, { method: "DELETE" });
    await refresh();
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password updated. Signing you out of other devices…");
      await signOut();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Password change failed");
    } finally {
      setLoading(false);
    }
  }

  async function addPasskey() {
    setLoading(true);
    try {
      const options = await api<Record<string, unknown>>("/api/auth/passkey/register/options", {
        method: "POST",
      });
      const credential = (await navigator.credentials.create({
        publicKey: {
          challenge: Uint8Array.from(
            atob((options.challenge as string).replace(/-/g, "+").replace(/_/g, "/")),
            (c) => c.charCodeAt(0),
          ),
          rp: options.rp as PublicKeyCredentialRpEntity,
          user: {
            ...(options.user as PublicKeyCredentialUserEntity),
            id: Uint8Array.from(
              atob(
                ((options.user as { id: string }).id).replace(/-/g, "+").replace(/_/g, "/"),
              ),
              (c) => c.charCodeAt(0),
            ),
          },
          pubKeyCredParams: options.pubKeyCredParams as PublicKeyCredentialParameters[],
          timeout: (options.timeout as number) || 60000,
          excludeCredentials: [],
        },
      })) as PublicKeyCredential | null;
      if (!credential) return;
      const response = credential.response as AuthenticatorAttestationResponse;
      await api("/api/auth/passkey/register/verify", {
        method: "POST",
        body: JSON.stringify({
          friendly_name: "Passkey",
          credential: {
            id: credential.id,
            rawId: bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
              clientDataJSON: bufferToBase64url(response.clientDataJSON),
              attestationObject: bufferToBase64url(response.attestationObject),
            },
          },
        }),
      });
      setMessage("Passkey registered.");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Passkey registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-2">
        <h1 className="font-display text-2xl font-bold text-ink">Account</h1>
        <p className="text-sm text-muted">{user.email}</p>
        <p className="text-xs text-muted">
          {user.email_verified ? "Email verified" : "Email not verified — check your inbox"}
        </p>
        <div className="pt-4 flex gap-2">
          {!user.email_verified ? (
            <Link href="/auth/verify">
              <Button variant="secondary" size="sm">
                Verify email
              </Button>
            </Link>
          ) : null}
          <Button variant="secondary" size="sm" onClick={() => signOut()}>
            Sign out
          </Button>
        </div>
      </div>

      <section className="holo-panel rounded-[var(--radius-xl)] p-6 space-y-4">
        <h2 className="font-data text-xs uppercase tracking-widest text-accent">Notification emails</h2>
        <ul className="space-y-2">
          {notificationEmails.map((row) => (
            <li
              key={row.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-md)] border border-border/50 px-4 py-3"
            >
              <div>
                <p className="text-sm text-ink">{row.email}</p>
                <p className="text-xs text-muted">
                  {row.label || "No label"} · {row.verified ? "Verified" : "Pending"}{" "}
                  {row.is_primary ? "· Primary" : ""}
                </p>
              </div>
              <div className="flex gap-2">
                {row.verified && !row.is_primary ? (
                  <Button size="sm" variant="secondary" onClick={() => setPrimary(row.id)}>
                    Make primary
                  </Button>
                ) : null}
                {!row.is_primary ? (
                  <Button size="sm" variant="secondary" onClick={() => removeEmail(row.id)}>
                    Remove
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
        <form onSubmit={addEmail} className="grid gap-3 sm:grid-cols-2">
          <Input label="New email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} required />
          <Input label="Label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Work, personal…" />
          <div className="sm:col-span-2">
            <Button type="submit" loading={loading}>
              Add notification email
            </Button>
          </div>
        </form>
      </section>

      {user.has_password ? (
        <section className="holo-panel rounded-[var(--radius-xl)] p-6 space-y-4">
          <h2 className="font-data text-xs uppercase tracking-widest text-accent">Password</h2>
          <form onSubmit={changePassword} className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Current password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
            <Input
              label="New password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              placeholder="At least 10 characters"
            />
            <div className="sm:col-span-2">
              <Button type="submit" loading={loading} variant="secondary">
                Change password
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="holo-panel rounded-[var(--radius-xl)] p-6 space-y-4">
        <h2 className="font-data text-xs uppercase tracking-widest text-accent">Passkeys</h2>
        <p className="text-sm text-muted">Sign in without a password using Face ID, Touch ID, or a security key.</p>
        <Button onClick={addPasskey} loading={loading} variant="secondary">
          Register passkey
        </Button>
      </section>

      {message ? <p className="text-sm text-accent">{message}</p> : null}
    </div>
  );
}
