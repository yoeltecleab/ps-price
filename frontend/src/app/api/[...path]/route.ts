import { NextRequest, NextResponse } from "next/server";
import { API_CLIENT_HEADER, API_CLIENT_VALUE } from "@/lib/apiClient";

const apiUrl = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";
const internalKey = process.env.INTERNAL_API_KEY || "";
const isProduction = process.env.NODE_ENV === "production";

const ALLOWED_REQUEST_HEADERS = new Set([
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "authorization",
]);

function allowedOrigins(): string[] {
  const raw =
    process.env.ALLOWED_API_ORIGINS ||
    "http://localhost:3000,http://127.0.0.1:3000";
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

/**
 * In production, only forward browser API calls that originate from our frontend.
 * Blocks address-bar navigation to /api/* and anonymous curl/scrapers.
 */
function rejectPublicApiBypass(request: NextRequest): NextResponse | null {
  if (!isProduction) {
    return null;
  }

  const fetchMode = request.headers.get("sec-fetch-mode");
  const fetchDest = request.headers.get("sec-fetch-dest");
  if (fetchMode === "navigate" || fetchDest === "document") {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }

  if (request.headers.get(API_CLIENT_HEADER.toLowerCase()) !== API_CLIENT_VALUE) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }

  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "same-origin" || fetchSite === "same-site") {
    return null;
  }

  const origins = allowedOrigins();
  const origin = request.headers.get("origin");
  if (origin && origins.includes(origin)) {
    return null;
  }

  const referer = request.headers.get("referer");
  if (referer && origins.some((allowed) => referer.startsWith(allowed))) {
    return null;
  }

  return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
}

function buildUpstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const [key, value] of request.headers.entries()) {
    const lower = key.toLowerCase();
    if (ALLOWED_REQUEST_HEADERS.has(lower)) {
      headers.set(lower, value);
    }
  }
  headers.set(API_CLIENT_HEADER, API_CLIENT_VALUE);
  if (internalKey) {
    headers.set("X-PS-Price-Internal", internalKey);
  }
  return headers;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (isProduction && !internalKey) {
    return NextResponse.json({ detail: "API proxy misconfigured" }, { status: 503 });
  }

  const rejected = rejectPublicApiBypass(request);
  if (rejected) {
    return rejected;
  }

  const { path } = await context.params;
  const targetPath = path.join("/");
  const target = `${apiUrl}/api/${targetPath}${request.nextUrl.search}`;

  const init: RequestInit = {
    method: request.method,
    headers: buildUpstreamHeaders(request),
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("transfer-encoding");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
