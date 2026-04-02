/* API client + WebSocket helpers */

const BASE = "";

export async function apiFetch<T = any>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers as any },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function apiGet<T = any>(path: string) {
  return apiFetch<T>(path);
}

export function apiPatch<T = any>(path: string, body: object) {
  return apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function apiPost<T = any>(path: string, body: object) {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function apiDelete<T = any>(path: string) {
  return apiFetch<T>(path, { method: "DELETE" });
}

/* WebSocket */

export type WsEvent = {
  type: string;
  [key: string]: any;
};

export function createWs(onMessage: (e: WsEvent) => void): WebSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/api/ws`);
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data));
    } catch {}
  };
  return ws;
}
