const TAB_USER_KEY = "teacher-workspace:tab-user-id";
const CHANNEL_NAME = "teacher-workspace:auth";
const CONTEXT_MISMATCH_EVENT = "teacher-workspace:context-mismatch";

export function getTabUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TAB_USER_KEY);
}

export function setTabUserId(userId: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(TAB_USER_KEY, userId);
}

export function clearTabUserId(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(TAB_USER_KEY);
}

export function broadcastAuthChanged(): void {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.postMessage({ type: "AUTH_CHANGED", at: Date.now() });
  channel.close();
}

export function notifyContextMismatch(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CONTEXT_MISMATCH_EVENT));
}

export function watchAccountContext(onChanged: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const mismatch = () => onChanged();
  window.addEventListener(CONTEXT_MISMATCH_EVENT, mismatch);
  if (typeof BroadcastChannel === "undefined") {
    return () => window.removeEventListener(CONTEXT_MISMATCH_EVENT, mismatch);
  }
  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.onmessage = (event: MessageEvent<{ type?: string }>) => {
    if (event.data?.type === "AUTH_CHANGED") onChanged();
  };
  return () => {
    window.removeEventListener(CONTEXT_MISMATCH_EVENT, mismatch);
    channel.close();
  };
}
