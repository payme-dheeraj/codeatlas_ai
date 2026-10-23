"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "next-themes";
import { useState, useEffect } from "react";
import { useAppStore } from "@/lib/store";
import { AuthGuard } from "@/components/auth-guard";
import { GlobalLoadingBar } from "@/components/global-loading-bar";

function ThemeSync() {
  const { resolvedTheme } = useTheme();
  const setTheme = useAppStore((s) => s.setTheme);
  useEffect(() => {
    if (resolvedTheme === "light" || resolvedTheme === "dark") {
      setTheme(resolvedTheme);
    }
  }, [resolvedTheme, setTheme]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="dark"
        enableSystem={false}
        disableTransitionOnChange
      >
        <ThemeSync />
        <GlobalLoadingBar />
        <AuthGuard>{children}</AuthGuard>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
