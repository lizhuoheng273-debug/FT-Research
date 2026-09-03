import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  getAuthIdentity, heartbeat, login, logout, restoreIdentity, startGuest,
  subscribeIdentityInvalidation, type AuthIdentity,
} from "@/lib/authClient";

type AuthContextValue = {
  identity: AuthIdentity | null;
  ready: boolean;
  signIn: (password: string) => Promise<void>;
  signInGuest: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<AuthIdentity | null>(getAuthIdentity());
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    void restoreIdentity().then((next) => { if (active) { setIdentity(next); setReady(true); } });
    const unsubscribe = subscribeIdentityInvalidation(() => setIdentity(null));
    return () => { active = false; unsubscribe(); };
  }, []);
  useEffect(() => {
    if (identity?.kind !== "guest") return;
    const timer = window.setInterval(() => void heartbeat().catch(() => setIdentity(null)), 15000);
    return () => window.clearInterval(timer);
  }, [identity?.id, identity?.kind]);
  const value = useMemo<AuthContextValue>(() => ({
    identity, ready,
    signIn: async (password) => { setIdentity(await login(password)); },
    signInGuest: async () => { const result = await startGuest(); setIdentity(result.identity); },
    signOut: async () => { await logout(); setIdentity(null); },
  }), [identity, ready]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
