import { NextRequest, NextResponse } from "next/server";

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

function buildUpstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const [key, value] of request.headers.entries()) {
    const lower = key.toLowerCase();
    if (ALLOWED_REQUEST_HEADERS.has(lower)) {
      headers.set(lower, value);
    }
  }
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
