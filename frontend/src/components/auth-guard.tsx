"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PageLoader } from "@/components/ui/spinner";

const PUBLIC_PATHS = ["/login", "/register"];

export function isPublicPath(pathname: string | null): boolean {
  return !!pathname && PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Client-side route guard. Redirects to /login (preserving the target URL)
 * when no access token is present for a protected route, and listens for the
 * global "codeatlas:unauthorized" event emitted by the API client on 401.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token && !isPublicPath(pathname)) {
      const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
      return;
    }
    setReady(true);
  }, [pathname, router]);

  useEffect(() => {
    const onUnauthorized = () => {
      localStorage.removeItem("access_token");
      if (!isPublicPath(window.location.pathname)) {
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      }
    };
    window.addEventListener("codeatlas:unauthorized", onUnauthorized);
    return () => window.removeEventListener("codeatlas:unauthorized", onUnauthorized);
  }, [router]);

  if (!ready && !isPublicPath(pathname)) {
    return <PageLoader label="Checking your session…" />;
  }
  return <>{children}</>;
}
