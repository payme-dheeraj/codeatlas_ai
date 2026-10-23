"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  username: string;
  role: string;
  created_at: string;
}

export interface RepositoryListResponse {
  total: number;
  page: number;
  limit: number;
  has_next: boolean;
  items: Repository[];
}

export interface TechStack {
  languages: string[];
  primary_language: string | null;
  frameworks: string[];
  databases: string[];
  infrastructure: string[];
  package_managers: string[];
  tools: string[];
}

export interface RepoStats {
  total_files: number;
  total_lines: number;
  total_size_bytes: number;
  modules: string[];
  module_count: number;
  commits: number;
  contributors: number;
  dependencies: number;
  files_stored?: number;
}

export interface IndexJob {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  current_stage: string | null;
  celery_task_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Repository {
  id: string;
  name: string;
  url: string | null;
  provider: string | null;
  default_branch: string;
  description: string | null;
  tech_stack: TechStack | null;
  stats: RepoStats | null;
  index_status: string;
  last_indexed_at: string | null;
  error_message: string | null;
  is_private: boolean;
  created_at: string;
  updated_at: string;
  latest_job: IndexJob | null;
}

/** AI-generated remediation payload (JSON object, not a string). */
export interface Remediation {
  vulnerability?: string;
  fixed_code?: string;
  recommendations?: string[];
}

export interface SecurityFinding {
  id: string;
  scan_id: string;
  repo_id: string;
  scanner: string;
  rule_id: string;
  title: string;
  description: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  cvss_score: number;
  category: string;
  language: string | null;
  file_path: string | null;
  start_line: number | null;
  end_line: number | null;
  snippet: string | null;
  remediation: Remediation | null;
  is_false_positive: boolean;
  suppressed: boolean;
}

export interface SecurityScan {
  id: string;
  repo_id: string;
  status: "queued" | "running" | "complete" | "failed";
  created_at: string;
  finding_count: number;
  total_findings: number;
}

export interface ChatSession {
  id: string;
  repo_id: string;
  title: string | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Citation {
  file_path: string;
  line_start: number | null;
  line_end: number | null;
  snippet: string;
}

export interface DiagramResponse {
  id: string;
  repo_id: string;
  diagram_type: string;
  diagram_format: string;
  source_code: string | null;
  render_url_svg: string | null;
  render_url_png: string | null;
  svg_url: string | null;
  png_url: string | null;
  version: number;
  created_at: string;
}

export interface DocumentResponse {
  id: string;
  repo_id: string;
  doc_type: string;
  title: string;
  content_md: string | null;
  content: string | null;
  version: number;
  created_at: string;
}

export interface HealthScore {
  repo_id: string;
  composite_score: number;
  grade: string;
  pillars: {
    code_quality: { score: number; details: unknown };
    security: { score: number; details: unknown };
    documentation: { score: number; details: unknown };
    activity: { score: number; details: unknown };
  };
  computed_at: string;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function setToken(token: string): void {
  localStorage.setItem("access_token", token);
}

function clearToken(): void {
  localStorage.removeItem("access_token");
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  auth = true
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401 && auth && typeof window !== "undefined") {
      window.dispatchEvent(new Event("codeatlas:unauthorized"));
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = Array.isArray(err.detail)
      ? err.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ")
      : err.detail;
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth API ──────────────────────────────────────────────────────────────────

export const authApi = {
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const data = await apiFetch<{ access_token: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false
    );
    setToken(data.access_token);
    return data;
  },

  async register(email: string, username: string, password: string): Promise<User> {
    return apiFetch<User>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, username, password }) },
      false
    );
  },

  logout(): void {
    clearToken();
  },

  async me(): Promise<User> {
    return apiFetch<User>("/users/me");
  },
};

// ── Repositories API ──────────────────────────────────────────────────────────

export const reposApi = {
  async list(): Promise<Repository[]> {
    const res = await apiFetch<RepositoryListResponse | Repository[]>("/repos");
    if (Array.isArray(res)) return res;
    return (res as RepositoryListResponse).items ?? [];
  },
  async get(id: string): Promise<Repository> {
    return apiFetch<Repository>(`/repos/${id}`);
  },
  async create(
    url: string,
    name?: string,
    auth_token?: string,
    default_branch?: string
  ): Promise<Repository> {
    return apiFetch<Repository>("/repos", {
      method: "POST",
      // `default_branch` omitted => backend auto-detects main vs master.
      body: JSON.stringify({ url, name, auth_token, default_branch }),
    });
  },
  async remoteBranches(
    url: string,
    auth_token?: string
  ): Promise<{ branches: string[]; default_branch: string }> {
    const params = new URLSearchParams({ url });
    if (auth_token) params.set("auth_token", auth_token);
    return apiFetch<{ branches: string[]; default_branch: string }>(
      `/repos/remote-branches?${params.toString()}`
    );
  },
  async uploadZip(file: File, name?: string): Promise<Repository> {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const url = new URL(`${API_BASE}/repos/upload`);
    if (name) url.searchParams.set("name", name);
    const res = await fetch(url.toString(), {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }
    return res.json();
  },
  async delete(id: string): Promise<void> {
    await apiFetch<void>(`/repos/${id}`, { method: "DELETE" });
  },
  async reindex(id: string): Promise<Repository> {
    return apiFetch<Repository>(`/repos/${id}/reindex`, { method: "POST" });
  },
  async health(id: string): Promise<HealthScore> {
    return apiFetch<HealthScore>(`/repos/${id}/health`);
  },
};

// ── Security API ──────────────────────────────────────────────────────────────

export const securityApi = {
  async triggerScan(repoId: string): Promise<{ id: string; status: string }> {
    return apiFetch(`/security/scans`, {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId }),
    });
  },
  async listScans(repoId: string): Promise<SecurityScan[]> {
    const res = await apiFetch<SecurityScan[] | { items?: SecurityScan[] }>(`/repos/${repoId}/scans`);
    const items = Array.isArray(res) ? res : (res as { items?: SecurityScan[] }).items ?? [];
    return items.map((s) => ({ ...s, finding_count: (s as SecurityScan).finding_count ?? (s as unknown as { total_findings?: number }).total_findings ?? 0 }));
  },
  async getFindings(repoId: string, scanId: string): Promise<SecurityFinding[]> {
    const res = await apiFetch<{ items?: SecurityFinding[] } | SecurityFinding[]>(`/security/scans/${scanId}/findings`);
    if (Array.isArray(res)) return res;
    return (res as { items?: SecurityFinding[] }).items ?? [];
  },
  async suppress(findingId: string, reason: string): Promise<void> {
    await apiFetch(`/security/findings/${findingId}/suppress`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },
  async exportSarif(repoId: string, scanId: string): Promise<Blob> {
    const token = getToken();
    const res = await fetch(`${API_BASE}/security/scans/${scanId}/report?format=sarif`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.blob();
  },
};

// ── Chat API ──────────────────────────────────────────────────────────────────

export const chatApi = {
  async createSession(repoId: string): Promise<ChatSession> {
    return apiFetch<ChatSession>("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId }),
    });
  },
  async listSessions(repoId: string): Promise<ChatSession[]> {
    return apiFetch<ChatSession[]>(`/chat/sessions?repo_id=${repoId}`);
  },
  async getMessages(sessionId: string): Promise<ChatMessage[]> {
    return apiFetch<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);
  },
  streamMessage(sessionId: string, content: string): EventSource {
    const token = getToken();
    const url = new URL(`${API_BASE}/chat/sessions/${sessionId}/stream`);
    url.searchParams.set("message", content);
    if (token) url.searchParams.set("token", token);
    return new EventSource(url.toString());
  },
};

// ── Diagrams API ──────────────────────────────────────────────────────────────

export const diagramsApi = {
  async generate(
    repoId: string,
    types: string[],
    format = "mermaid"
  ): Promise<{ job_id: string; status: string }> {
    return apiFetch(`/repos/${repoId}/diagrams/generate`, {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId, diagram_types: types, diagram_format: format }),
    });
  },
  async list(repoId: string): Promise<DiagramResponse[]> {
    return apiFetch<DiagramResponse[]>(`/repos/${repoId}/diagrams`);
  },
  async get(repoId: string, type: string): Promise<DiagramResponse> {
    return apiFetch<DiagramResponse>(`/repos/${repoId}/diagrams/${type}`);
  },
};

// ── Docs API ──────────────────────────────────────────────────────────────────

export const docsApi = {
  async generate(repoId: string, types: string[]): Promise<{ id: string; status: string }> {
    return apiFetch(`/repos/${repoId}/docs/generate`, {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId, doc_types: types }),
    });
  },
  async list(repoId: string): Promise<DocumentResponse[]> {
    return apiFetch<DocumentResponse[]>(`/repos/${repoId}/docs`);
  },
  async get(repoId: string, type: string): Promise<DocumentResponse> {
    return apiFetch<DocumentResponse>(`/repos/${repoId}/docs/${type}`);
  },
};

// ── Search API ────────────────────────────────────────────────────────────────

export interface SearchResult {
  id: string;
  repo_id: string;
  file_path: string;
  symbol_name: string | null;
  snippet: string;
  score: number;
  line_start?: number | null;
  line_end?: number | null;
}

export const searchApi = {
  async search(query: string, repoId?: string): Promise<SearchResult[]> {
    // Hybrid fuses semantic + keyword, which is the sensible default for a
    // natural-language search box (keyword alone misses paraphrased queries).
    const body: Record<string, unknown> = { query, mode: "hybrid" };
    if (repoId) body.repo_ids = [repoId];
    const res = await apiFetch<any>(
      "/search",
      { method: "POST", body: JSON.stringify(body) }
    );
    const rawHits: any[] = Array.isArray(res)
      ? res
      : (res?.hits ?? res?.items ?? []);
    return rawHits.map((h: any) => ({
      id: h.symbol_id ?? h.id ?? String(Math.random()),
      repo_id: h.repo_id ?? "",
      file_path: h.file_path ?? "",
      symbol_name: h.name ?? h.symbol_name ?? null,
      snippet: h.chunk_text ?? h.snippet ?? h.docstring ?? "",
      score: typeof h.score === "number" ? h.score : 0,
      line_start: h.start_line ?? h.line_start ?? null,
      line_end: h.end_line ?? h.line_end ?? null,
    }));
  },
};
