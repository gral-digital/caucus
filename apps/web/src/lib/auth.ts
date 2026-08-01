"use client";

/**
 * Sessione client per il free tier hosted.
 *
 * Il token bearer vive in localStorage: accettabile per il free tier (niente
 * dati di fascicolo persistiti lato server oltre ai documenti caricati
 * dall'utente stesso); il server conserva comunque solo l'hash e ogni
 * sessione è revocabile con il logout.
 */

const TOKEN_KEY = "caucus_session_token";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** Header Authorization se c'è una sessione; oggetto vuoto altrimenti. */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchAuthConfig(): Promise<{
  accounts_enabled: boolean;
  free_daily_chat_limit: number;
}> {
  const res = await fetch("/api/v1/auth/config");
  if (!res.ok) return { accounts_enabled: false, free_daily_chat_limit: 0 };
  return res.json();
}

export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch("/api/v1/auth/me", { headers: authHeaders() });
  if (!res.ok) return null;
  return res.json();
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail ?? "Accesso non riuscito.");
  setToken(data.token);
  return data.user as AuthUser;
}

export async function register(email: string, password: string): Promise<AuthUser> {
  const res = await fetch("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail ?? "Registrazione non riuscita.");
  // Login immediato post-registrazione: un passaggio in meno per l'utente.
  return login(email, password);
}

export async function logout(): Promise<void> {
  const token = getToken();
  clearToken();
  if (token) {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
}
