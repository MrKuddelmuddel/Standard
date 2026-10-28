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

type State<T> = { path: string | null; data: T | undefined; error: unknown };

/**
 * Fetch a GET endpoint. Pass `null` to skip. `pollMs` re-fetches while `shouldPoll(data)` is true.
 * Keeps the previous data while a new path loads; `loading` is true until the current path has answered once.
 */
export function useApi<T>(path: string | null, opts: { pollMs?: number; shouldPoll?: (d: T | undefined) => boolean } = {}): Resource<T> {
  const [state, setState] = useState<State<T>>({ path: null, data: undefined, error: null });
  const seq = useRef(0);
  const { pollMs, shouldPoll } = opts;
  const shouldPollRef = useRef(shouldPoll);
  useEffect(() => {
    shouldPollRef.current = shouldPoll;
  }, [shouldPoll]);

  const fetchPath = useCallback((p: string): Promise<void> => {
    const id = ++seq.current;
    return api<T>(p).then(
      (d) => {
        if (id === seq.current) setState({ path: p, data: d, error: null });
      },
      (e: unknown) => {
        if (id === seq.current) setState((s) => ({ path: p, data: s.data, error: e }));
      },
    );
  }, []);

  useEffect(() => {
    if (path !== null) void fetchPath(path);
  }, [path, fetchPath]);

  const data = state.data;
  useEffect(() => {
    if (!pollMs || path === null) return;
    const t = setInterval(() => {
      if (!shouldPollRef.current || shouldPollRef.current(data)) void fetchPath(path);
    }, pollMs);
    return () => clearInterval(t);
  }, [pollMs, path, fetchPath, data]);

  const reload = useCallback(() => (path === null ? Promise.resolve() : fetchPath(path)), [path, fetchPath]);
  const setData = useCallback((d: T) => setState((s) => ({ ...s, data: d, error: null })), []);
  return { data, error: state.path === path ? state.error : null, loading: path !== null && state.path !== path, reload, setData };
}

export const isActive = (status: string | undefined) => status === "queued" || status === "running";
