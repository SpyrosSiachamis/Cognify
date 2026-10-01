"use client";

import { AppProvider, useApp } from "./AppProvider";
import { IconSprite } from "./Icons";
import { Room } from "./Room";
import { TopBar } from "./TopBar";

function Shell() {
  const { state, dispatch } = useApp();
  const newProblem = () => {
    if (state.sealOpen) return;
    dispatch({ type: "newProblem" });
  };
  return (
    <>
      <IconSprite />
      <Room />
      <TopBar onNewProblem={newProblem} />
      <main className="wrap" id="main" />
    </>
  );
}

export function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
