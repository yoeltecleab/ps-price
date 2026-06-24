export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg ?? "").join(", ");
    }
  } catch {
    /* ignore */
  }
  return res.statusText || "Request failed";
}

const AUTH_PATHS = [
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/logout",
  "/api/auth/me",
];

async function tryRefreshAccessToken(): Promise<boolean> {
  const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
  return res.ok;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const fetchOpts: RequestInit = { ...init, headers, credentials: "include" };
  let res = await fetch(path, fetchOpts);

  const isAuthPath = AUTH_PATHS.some((p) => path.startsWith(p));
  if (res.status === 401 && !isAuthPath) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) {
      res = await fetch(path, fetchOpts);
    }
  }

  if (!res.ok) {
    throw new ApiError(await parseError(res), res.status);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
