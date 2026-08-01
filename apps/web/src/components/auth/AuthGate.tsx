"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  fetchAuthConfig,
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  type AuthUser,
} from "@/lib/auth";
import { Wordmark } from "@/components/layout/Wordmark";

type AuthState = {
  /** null = account disattivati (self-hosting): nessun gate. */
  user: AuthUser | null;
  accountsEnabled: boolean;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  user: null,
  accountsEnabled: false,
  logout: async () => undefined,
});

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

/**
 * Gate del free tier hosted: con gli account attivi (config dal server)
 * chiede accesso o registrazione prima di mostrare l'app; nel self-hosting
 * (default) è trasparente e non aggiunge alcun passaggio.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<"loading" | "gate" | "ready">("loading");
  const [accountsEnabled, setAccountsEnabled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const config = await fetchAuthConfig();
      if (cancelled) return;
      setAccountsEnabled(config.accounts_enabled);
      if (!config.accounts_enabled) {
        setPhase("ready");
        return;
      }
      const me = await fetchMe();
      if (cancelled) return;
      setUser(me);
      setPhase(me ? "ready" : "gate");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setPhase(accountsEnabled ? "gate" : "ready");
  }, [accountsEnabled]);

  if (phase === "loading") {
    return <div className="flex h-screen items-center justify-center bg-paper" />;
  }
  if (phase === "gate") {
    return (
      <AuthScreen
        onDone={(u) => {
          setUser(u);
          setPhase("ready");
        }}
      />
    );
  }
  return (
    <AuthContext.Provider value={{ user, accountsEnabled, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

function AuthScreen({ onDone }: { onDone: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user =
        mode === "login"
          ? await apiLogin(email, password)
          : await apiRegister(email, password);
      onDone(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Wordmark size="lg" />
          <p className="mt-3 text-[13.5px] leading-relaxed text-ink-muted">
            Accedi per usare il piano gratuito. Preferisci non registrarti?
            Caucus è software libero:{" "}
            <a
              href="https://github.com/caucus-legal"
              className="text-accent underline decoration-accent/40 underline-offset-2"
            >
              self-hosting senza account
            </a>
            .
          </p>
        </div>

        <div className="mb-4 flex rounded-lg border border-paper-border bg-paper-panel p-1 text-[13.5px]">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={
                "flex-1 rounded-md px-3 py-1.5 transition " +
                (mode === m ? "bg-paper font-medium text-ink shadow-sm" : "text-ink-muted")
              }
            >
              {m === "login" ? "Accedi" : "Registrati"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            autoComplete="email"
            className="rounded-lg border border-paper-border bg-paper px-3.5 py-2.5 text-[14.5px] outline-none transition placeholder:text-ink-subtle focus:border-ink-subtle/60"
          />
          <input
            type="password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === "register" ? "Password (minimo 10 caratteri)" : "Password"}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            className="rounded-lg border border-paper-border bg-paper px-3.5 py-2.5 text-[14.5px] outline-none transition placeholder:text-ink-subtle focus:border-ink-subtle/60"
          />
          {error ? <p className="text-[13px] text-accent">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-lg bg-ink px-4 py-2.5 text-[14.5px] font-medium text-paper transition hover:bg-ink-muted disabled:opacity-50"
          >
            {busy ? "Un momento…" : mode === "login" ? "Accedi" : "Crea account gratuito"}
          </button>
        </form>

        <p className="mt-6 text-center text-[11.5px] leading-relaxed text-ink-subtle">
          L&apos;assistente non sostituisce il parere di un avvocato.
        </p>
      </div>
    </div>
  );
}
