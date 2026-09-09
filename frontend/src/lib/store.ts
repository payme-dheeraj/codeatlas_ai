"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Repository, ChatSession, ChatMessage, User } from "./api";

// ── App Store ─────────────────────────────────────────────────────────────────

interface AppStore {
  currentRepo: Repository | null;
  setCurrentRepo: (repo: Repository | null) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  theme: "dark" | "light";
  setTheme: (theme: "dark" | "light") => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      currentRepo: null,
      setCurrentRepo: (repo) => set({ currentRepo: repo }),
      sidebarOpen: true,
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      theme: "dark",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "codeatlas-app" }
  )
);

// ── Auth Store ────────────────────────────────────────────────────────────────

interface AuthStore {
  user: User | null;
  token: string | null;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user) => set({ user }),
      setToken: (token) => set({ token }),
      logout: () => {
        set({ user: null, token: null });
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
        }
      },
    }),
    { name: "codeatlas-auth" }
  )
);

// ── Chat Store ────────────────────────────────────────────────────────────────

interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  setSessions: (sessions: ChatSession[]) => void;
  setActiveSession: (id: string | null) => void;
  setMessages: (messages: ChatMessage[]) => void;
  appendMessage: (message: ChatMessage) => void;
  setStreaming: (streaming: boolean) => void;
  appendStreamChunk: (chunk: string) => void;
  clearStreamBuffer: () => void;
}

export const useChatStore = create<ChatStore>()((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  isStreaming: false,
  streamingContent: "",
  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  appendStreamChunk: (chunk) =>
    set((s) => ({ streamingContent: s.streamingContent + chunk })),
  clearStreamBuffer: () => set({ streamingContent: "" }),
}));
