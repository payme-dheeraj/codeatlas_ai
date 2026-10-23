"use client";

import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Thin progress bar pinned to the top of the viewport that is visible whenever
 * any backend request (query or mutation) is in flight. Appearance is delayed
 * slightly so fast responses do not cause a distracting flash.
 */
export function GlobalLoadingBar({ delayMs = 150 }: { delayMs?: number }) {
  const active = useIsFetching() + useIsMutating() > 0;
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!active) {
      setVisible(false);
      return;
    }
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [active, delayMs]);

  return (
    <div
      role="progressbar"
      aria-busy={visible}
      aria-label="Loading data from server"
      className={cn(
        "fixed inset-x-0 top-0 z-[100] h-0.5 overflow-hidden transition-opacity duration-200",
        visible ? "opacity-100" : "opacity-0 pointer-events-none"
      )}
    >
      <div className="h-full w-1/3 animate-loading-bar bg-primary" />
    </div>
  );
}
