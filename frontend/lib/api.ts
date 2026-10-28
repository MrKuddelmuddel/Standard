// Same-origin API client. Sends the session cookie and the CSRF header on every request.

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type Json = Record<string, unknown> | unknown[];

export async function api<T = unknown>(path: string, init: RequestInit & { json?: Json } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    ...rest,
    headers: {
      "X-Requested-With": "nexus",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  const text = await res.text();
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; details?: unknown; request_id?: string } } | null)?.error;
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      window.dispatchEvent(new CustomEvent("nexus:unauthorized"));
    }
    throw new ApiError(
      res.status,
      err?.code ?? (res.status >= 500 ? "server_error" : "http_error"),
      err?.message ?? (res.status >= 500 ? "The server is not reachable or returned an error." : `Request failed (${res.status}).`),
      err?.details,
      err?.request_id,
    );
  }
  return body as T;
}

export const post = <T = unknown>(path: string, json?: Json) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T = unknown>(path: string, json: Json) => api<T>(path, { method: "PUT", json });
export const patch = <T = unknown>(path: string, json: Json) => api<T>(path, { method: "PATCH", json });
export const del = <T = unknown>(path: string) => api<T>(path, { method: "DELETE" });

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}

export function errorIssues(e: unknown): { path: string; message: string }[] {
  if (e instanceof ApiError && Array.isArray(e.details)) {
    return (e.details as { path?: string; message?: string }[]).map((d) => ({ path: d.path ?? "", message: d.message ?? String(d) }));
  }
  return [];
}
