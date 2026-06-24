/** Helpers for WebAuthn ceremony in the browser. */

export function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function base64urlToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

type CredDescriptor = { id: string; type: string; transports?: string[] };

export function buildRegistrationOptions(options: Record<string, unknown>): CredentialCreationOptions {
  const exclude = Array.isArray(options.excludeCredentials)
    ? (options.excludeCredentials as CredDescriptor[]).map((c) => ({
        type: "public-key" as const,
        id: base64urlToBuffer(c.id),
        transports: c.transports as AuthenticatorTransport[] | undefined,
      }))
    : [];

  const rpEntity = (options.rp as PublicKeyCredentialRpEntity) || { name: "PS Prices" };
  const rpId = (options.rpId as string) || (options.rp as { id?: string })?.id;

  return {
    publicKey: {
      challenge: base64urlToBuffer(options.challenge as string),
      rp: { ...rpEntity, id: rpId || rpEntity.id },
      user: {
        ...(options.user as PublicKeyCredentialUserEntity),
        id: base64urlToBuffer((options.user as { id: string }).id),
      },
      pubKeyCredParams: (options.pubKeyCredParams as PublicKeyCredentialParameters[]) || [
        { type: "public-key", alg: -7 },
        { type: "public-key", alg: -257 },
      ],
      timeout: (options.timeout as number) || 120000,
      excludeCredentials: exclude,
      authenticatorSelection: (options.authenticatorSelection as AuthenticatorSelectionCriteria) || {
        residentKey: "preferred",
        userVerification: "required",
      },
      attestation: "none",
    },
  };
}

export function buildLoginOptions(options: Record<string, unknown>): CredentialRequestOptions {
  return {
    publicKey: {
      challenge: base64urlToBuffer(options.challenge as string),
      timeout: (options.timeout as number) || 120000,
      rpId: options.rpId as string,
      userVerification: "required",
      allowCredentials: Array.isArray(options.allowCredentials)
        ? (options.allowCredentials as CredDescriptor[]).map((c) => ({
            type: "public-key" as const,
            id: base64urlToBuffer(c.id),
            transports: c.transports as AuthenticatorTransport[] | undefined,
          }))
        : undefined,
    },
  };
}

export function credentialToJson(credential: PublicKeyCredential) {
  if (credential.response instanceof AuthenticatorAttestationResponse) {
    const response = credential.response;
    return {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(response.clientDataJSON),
        attestationObject: bufferToBase64url(response.attestationObject),
      },
    };
  }
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    },
  };
}
