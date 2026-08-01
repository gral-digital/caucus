/**
 * Impostazioni client-side, persistite in localStorage.
 *
 * L'unica impostazione con effetto sul retrieval è la data di vigenza
 * (`effectiveAt`): quando impostata, ogni richiesta /chat la passa come
 * `effective_at` e il sistema risponde sulla base dei testi vigenti a quella
 * data. null = oggi (default).
 */

const KEY = "caucus:settings:v1";

export type AppSettings = {
  /** Data di vigenza ISO (YYYY-MM-DD) per il retrieval; null = oggi. */
  effectiveAt: string | null;
};

const DEFAULTS: AppSettings = { effectiveAt: null };

export function loadSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export function saveSettings(settings: AppSettings): void {
  window.localStorage.setItem(KEY, JSON.stringify(settings));
}
