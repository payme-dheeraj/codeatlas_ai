const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface SSEOptions {
  onMessage: (data: string) => void;
  onError?: (err: Event) => void;
  onOpen?: () => void;
}

export function createSSE(path: string, options: SSEOptions): EventSource {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const url = new URL(`${API_BASE}${path}`);
  if (token) url.searchParams.set("token", token);

  const es = new EventSource(url.toString());

  es.onopen = () => options.onOpen?.();
  es.onmessage = (e) => options.onMessage(e.data);
  es.onerror = (e) => {
    options.onError?.(e);
    es.close();
  };

  return es;
}

export function useIndexingSSE(
  repoId: string,
  onProgress: (pct: number, status: string) => void,
  enabled = true
): () => void {
  if (!enabled || typeof window === "undefined") return () => {};

  const es = createSSE(`/repos/${repoId}/status/stream`, {
    onMessage: (raw) => {
      try {
        const data = JSON.parse(raw) as { progress?: number; status?: string };
        onProgress(data.progress ?? 0, data.status ?? "indexing");
      } catch {
        // ignore non-JSON heartbeats
      }
    },
  });

  return () => es.close();
}
