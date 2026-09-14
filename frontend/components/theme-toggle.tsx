"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false);
  if (!mounted) return <button className="icon-button" aria-label="Change theme"><Sun size={15} /></button>;
  const light = theme === "light";
  return <button className="icon-button" aria-label={`Switch to ${light ? "dark" : "light"} mode`} onClick={() => setTheme(light ? "dark" : "light")}>{light ? <Moon size={15} /> : <Sun size={15} />}</button>;
}
