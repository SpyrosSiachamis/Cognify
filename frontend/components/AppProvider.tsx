"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import { room } from "@/lib/room";
import { initialState, reducer, type Action, type AppState, type Theme } from "@/lib/state";

type Ctx = { state: AppState; dispatch: (a: Action) => void; chooseTheme: (t: Theme) => void };
const AppContext = createContext<Ctx | null>(null);

const THEME_KEY = "cognify-theme";

function paintTheme(theme: Theme) {
  // The theme is just an attribute on <html>; the CSS does the rest.
  if (theme === "salon") document.documentElement.setAttribute("data-theme", "salon");
  else document.documentElement.removeAttribute("data-theme");
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // Pick up the saved theme. The inline script in layout.tsx already painted it on <html>,
  // so here we only tell React which button is pressed.
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(THEME_KEY);
    } catch {}
    dispatch({ type: "theme", theme: saved === "salon" ? "salon" : "velvet" });
  }, []);

  const chooseTheme = useCallback((theme: Theme) => {
    paintTheme(theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {}
    dispatch({ type: "theme", theme });
    room.setTheme();
  }, []);

  useEffect(() => {
    document.body.classList.toggle("dim", state.dim);
  }, [state.dim]);

  const value = useMemo(() => ({ state, dispatch, chooseTheme }), [state, chooseTheme]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
