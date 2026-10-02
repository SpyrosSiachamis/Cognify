"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { room } from "@/lib/room";
import { initialState, reducer, type Action, type AppState, type Theme } from "@/lib/state";

/* The app state lives in a tiny store (the same reducer as before). Components read only the part
   they need with useAppSelector, so typing in the problem box, for example, no longer re-renders
   the top bar, the drawer or the seal. */

type Store = {
  get: () => AppState;
  dispatch: (a: Action) => void;
  subscribe: (listener: () => void) => () => void;
};

function createStore(): Store {
  let state = initialState;
  const listeners = new Set<() => void>();
  return {
    get: () => state,
    dispatch(a) {
      const next = reducer(state, a);
      if (next === state) return;
      state = next;
      listeners.forEach((l) => l());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

type Actions = { dispatch: (a: Action) => void; chooseTheme: (t: Theme) => void; getState: () => AppState };
const StoreContext = createContext<{ store: Store; actions: Actions } | null>(null);

const THEME_KEY = "cognify-theme";

function paintTheme(theme: Theme) {
  // The theme is just an attribute on <html>; the CSS does the rest.
  if (theme === "salon") document.documentElement.setAttribute("data-theme", "salon");
  else document.documentElement.removeAttribute("data-theme");
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [store] = useState(createStore);

  const chooseTheme = useCallback(
    (theme: Theme) => {
      paintTheme(theme);
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch {}
      store.dispatch({ type: "theme", theme });
      room.setTheme();
    },
    [store],
  );
  const value = useMemo(() => ({ store, actions: { dispatch: store.dispatch, chooseTheme, getState: store.get } }), [store, chooseTheme]);

  // Pick up the saved theme. The inline script in layout.tsx already painted it on <html>,
  // so here we only tell the store which button is pressed.
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(THEME_KEY);
    } catch {}
    store.dispatch({ type: "theme", theme: saved === "salon" ? "salon" : "velvet" });
  }, [store]);

  // The room dims during the fresh problem.
  useEffect(() => {
    let dim = store.get().dim;
    return store.subscribe(() => {
      const next = store.get().dim;
      if (next !== dim) document.body.classList.toggle("dim", (dim = next));
    });
  }, [store]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}

/** Read one part of the state. The component re-renders only when that part changes,
    so the selector must return a value from the state (or a primitive), not build a new object. */
export function useAppSelector<T>(select: (s: AppState) => T): T {
  const { store } = useStore();
  return useSyncExternalStore(
    store.subscribe,
    () => select(store.get()),
    () => select(initialState),
  );
}

/** dispatch, chooseTheme and getState. These never change, so using them causes no re-render. */
export function useActions(): Actions {
  return useStore().actions;
}

/** The whole state plus the actions. Re-renders on every change: use it only where that is needed. */
export function useApp(): Actions & { state: AppState } {
  const state = useAppSelector((s) => s);
  return { state, ...useActions() };
}
