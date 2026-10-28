"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";

export type Resource<T> = {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
};

/** Fetch a GET endpoint. Pass `null` to skip. `pollMs` re-fetches while `shouldPoll(data)` is true. */
export function useApi<T>(path: string | null, opts: { pollMs?: number; shouldPoll?: (d: T | undefined) => boolean } = {}): Resource<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const seq = useRef(0);
  const { pollMs, shouldPoll } = opts;
  const shouldPollRef = useRef(shouldPoll);
  useEffect(() => {
    shouldPollRef.current = shouldPoll;
  }, [shouldPoll]);

  const load = useCallback(async () => {
    if (path === null) return;
    const id = ++seq.current;
    try {
      const d = await api<T>(path);
      if (id === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (id === seq.current) setError(e);
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(path !== null);
    void load();
  }, [load, path]);

  useEffect(() => {
    if (!pollMs || path === null) return;
    const t = setInterval(() => {
      if (!shouldPollRef.current || shouldPollRef.current(data)) void load();
    }, pollMs);
    return () => clearInterval(t);
  }, [pollMs, path, load, data]);

  return { data, error, loading, reload: load, setData };
}

export const isActive = (status: string | undefined) => status === "queued" || status === "running";
