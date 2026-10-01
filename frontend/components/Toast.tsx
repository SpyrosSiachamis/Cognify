"use client";

import { useEffect, useState } from "react";
import { useApp } from "./AppProvider";

/* A small pill at the bottom: "Cognify found where you get stuck  [See it]". It fades after seven seconds. */
export function Toast() {
  const { state, dispatch } = useApp();
  const toast = state.toast;
  // Keep the last message so the text does not vanish while the pill fades out.
  const [shown, setShown] = useState(toast);
  if (toast && toast !== shown) setShown(toast);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => dispatch({ type: "toast", toast: null }), 7000);
    return () => clearTimeout(t);
  }, [toast, dispatch]);

  return (
    <div className={`toast${toast ? " show" : ""}`} role="status">
      <span>{shown?.msg}</span>
      <button type="button" onClick={() => toast && dispatch({ type: "sheet", open: true, tab: toast.tab })}>
        {shown?.label}
      </button>
    </div>
  );
}
