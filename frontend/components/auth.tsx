"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, ApiError, post } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthState = { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Loads the current user. Pages inside the app redirect to /login when the session is missing or expired. */
export function AuthProvider({ children, requireAuth }: { children: ReactNode; requireAuth: boolean }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(
    () =>
      api<User>("/auth/me").then(
        (u) => {
          setUser(u);
          setLoading(false);
        },
        (e: unknown) => {
          setUser(null);
          setLoading(false);
          if (requireAuth && e instanceof ApiError && e.status === 401) router.replace("/login");
        },
      ),
    [requireAuth, router],
  );

  const logout = useCallback(async () => {
    try {
      await post("/auth/logout");
    } finally {
      setUser(null);
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!requireAuth) return;
    const onUnauthorized = () => router.replace("/login");
    window.addEventListener("nexus:unauthorized", onUnauthorized);
    return () => window.removeEventListener("nexus:unauthorized", onUnauthorized);
  }, [requireAuth, router]);

  return <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>;
}
