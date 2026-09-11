import { getTabUserId, notifyContextMismatch } from "./account-context";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message);
  }
}

function cookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length);
}

const PUBLIC_AUTH_WRITES = new Set(["/auth/login", "/auth/register", "/auth/reset-password"]);

function addWriteProtection(path: string, headers: Headers): void {
  const csrf = cookie("teacher_workspace_session_csrf");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const expectedUserId = getTabUserId();
  if (expectedUserId) headers.set("X-Expected-User-ID", expectedUserId);
  else if (!PUBLIC_AUTH_WRITES.has(path)) {
    throw new ApiError("正在确认当前账户，请稍后重试", 409, "ACCOUNT_CONTEXT_PENDING");
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (
    init.body &&
    !(typeof FormData !== "undefined" && init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    addWriteProtection(path, headers);
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { message?: string; code?: string }
      | null;
    const code = body?.code ?? "HTTP_ERROR";
    if (code === "ACCOUNT_CONTEXT_CHANGED") notifyContextMismatch();
    throw new ApiError(body?.message ?? "请求失败", response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiBlob(
  path: string,
  init: RequestInit = {},
): Promise<{ blob: Blob; filename: string }> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    addWriteProtection(path, headers);
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { message?: string; code?: string }
      | null;
    const code = body?.code ?? "HTTP_ERROR";
    if (code === "ACCOUNT_CONTEXT_CHANGED") notifyContextMismatch();
    throw new ApiError(body?.message ?? "下载失败", response.status, code);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  return {
    blob: await response.blob(),
    filename: encodedFilename ? decodeURIComponent(encodedFilename) : "教师版教案.docx",
  };
}

export function jsonBody(value: unknown): Pick<RequestInit, "body"> {
  return { body: JSON.stringify(value) };
}
