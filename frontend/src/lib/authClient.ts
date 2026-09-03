export type AuthIdentity = { id: string; kind: 'owner' | 'guest'; expiresAt: string | number | null };

let guestToken: string | null = null;
let identity: AuthIdentity | null = null;
let channel: BroadcastChannel | null = null;

function url(path: string) {
  const base = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
  return `${base}/api${path.startsWith('/') ? path : `/${path}`}`;
}

function csrfToken() {
  return document.cookie.split('; ').find((entry) => entry.startsWith('ft-csrf='))?.slice(8) || '';
}

function headers(method?: string): Record<string, string> {
  const result: Record<string, string> = {};
  if (guestToken) result.Authorization = `Bearer ${guestToken}`;
  if (identity?.kind === 'owner' && method && method !== 'GET') result['X-CSRF-Token'] = csrfToken();
  return result;
}

async function request(path: string, method = 'GET', body?: unknown) {
  const init: RequestInit = { method, credentials: 'include', headers: { ...headers(method) } };
  if (body !== undefined) { (init.headers as Record<string, string>)['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  const response = await fetch(url(path), init);
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
  return response.json();
}

export function getGuestToken() { return guestToken; }
export function getAuthIdentity() { return identity; }
export function authHeaders(method = 'GET') { return headers(method); }
export function hasGuestToken() { return Boolean(guestToken); }

export async function restoreIdentity(): Promise<AuthIdentity | null> {
  if (!guestToken && !identity) {
    try { identity = await request('/auth/me'); } catch { identity = null; }
  }
  return identity;
}

export async function login(password: string): Promise<AuthIdentity> {
  const result = await request('/auth/login', 'POST', { password });
  identity = result as AuthIdentity;
  guestToken = null;
  return identity;
}

export async function startGuest(): Promise<{ identity: AuthIdentity; token: string }> {
  await logout().catch(() => undefined);
  const result = await request('/auth/guest', 'POST');
  identity = result.identity;
  guestToken = result.token;
  return result;
}

export async function heartbeat() {
  if (identity?.kind === 'guest') await request('/auth/heartbeat', 'POST');
}

export async function logout() {
  try { await request('/auth/logout', 'POST'); } finally { guestToken = null; identity = null; }
  try { channel?.postMessage({ type: 'identity-invalidated' }); } catch { /* browser shutdown */ }
}

export function clearAuthMemory() { guestToken = null; identity = null; }

export function subscribeIdentityInvalidation(onInvalidated: () => void) {
  if (typeof BroadcastChannel === 'undefined') return () => undefined;
  channel ??= new BroadcastChannel('ft-research-auth');
  const handler = (event: MessageEvent) => { if (event.data?.type === 'identity-invalidated') { clearAuthMemory(); onInvalidated(); } };
  channel.addEventListener('message', handler);
  return () => channel?.removeEventListener('message', handler);
}
