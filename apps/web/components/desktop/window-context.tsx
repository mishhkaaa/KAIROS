"use client";

import { createContext, useContext } from "react";

/** What an app inside a window knows about its own window: the URL it shows, and how to move it somewhere else
 *  (a new URL for the same app navigates in place; another app's URL opens or focuses that app's window). */
export interface WindowNav {
  key: string;
  url: string;
  navigate: (url: string) => void;
  close: () => void;
}

export const WindowContext = createContext<WindowNav | null>(null);

export function useWindowNav(): WindowNav {
  const nav = useContext(WindowContext);
  if (!nav) throw new Error("useWindowNav must be used inside a desktop window");
  return nav;
}

/** The window URL's query string, like useSearchParams() but per window. */
export function useWindowParams(): URLSearchParams {
  return new URLSearchParams(useWindowNav().url.split("?", 2)[1] ?? "");
}
