# 12 — Frontend Design

## Overview

The CodeAtlas AI frontend is a Next.js 14 application using the App Router, TailwindCSS for styling, and shadcn/ui for the component library. It provides a dark-mode-first, developer-focused interface with a VSCode-inspired aesthetic.

---

## Technology Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Next.js | 14.x (App Router) | Framework, SSR, API routes |
| TypeScript | 5.x | Type safety |
| TailwindCSS | 3.x | Utility-first styling |
| shadcn/ui | latest | Component library |
| Lucide React | latest | Icons |
| React Query | 5.x | Server state management |
| Zustand | 4.x | Client state management |
| Monaco Editor | latest | Code display with syntax highlighting |
| Mermaid.js | 10.x | Diagram rendering in UI |
| highlight.js | 11.x | Syntax highlighting for chat citations |
| Socket.io / SSE | — | Real-time updates (indexing status, chat streaming) |

---

## Application Routes

```
/                          Landing / Dashboard
/repositories              Repository list
/repositories/new          Import repository form
/repositories/[id]         Repository overview
/repositories/[id]/chat    AI Chat interface
/repositories/[id]/diagram Diagram viewer
/repositories/[id]/docs    Generated documentation
/repositories/[id]/security Security findings
/repositories/[id]/explore Code explorer
/search                    Global search
/settings                  User settings, LLM config
/admin                     Admin panel (admin role)
```

---

## Key UI Screens

### 1. Dashboard (`/`)

```
┌─────────────────────────────────────────────────────────┐
│  [CodeAtlas AI Logo]          [Search]    [User Avatar]  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Repositories│  │  Findings    │  │  AI Queries  │ │
│  │     12       │  │   47 (3 🔴)  │  │   1,204      │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  Recent Repositories                [+ Import Repo]      │
│  ┌─────────────────────────────────────────────────────┐│
│  │ 📁 codeatlas-ai    Python/TS  ✅ Indexed  2h ago     ││
│  │ 📁 payment-service  Java      ⏳ Indexing  now        ││
│  │ 📁 frontend-app     React     ✅ Indexed  1d ago      ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### 2. Repository Overview (`/repositories/[id]`)

```
┌─────────────────────────────────────────────────────────┐
│  📁 codeatlas-ai                          [Re-index] [⚙️] │
├─────────────────────────────────────────────────────────┤
│  Python · TypeScript · 47k LOC · 523 files · ✅ Indexed  │
├────────────────┬────────────────────────────────────────┤
│  [Chat] [Diagrams] [Docs] [Security] [Explore]          │
├────────────────┴────────────────────────────────────────┤
│                                                          │
│  Health Score: 87/100  ████████░░                       │
│                                                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐          │
│  │ Languages  │ │ Top Dirs   │ │ Security   │          │
│  │ Python 60% │ │ src/       │ │ 🔴 2 Crit  │          │
│  │ TS 30%     │ │ tests/     │ │ 🟡 5 Med   │          │
│  │ Other 10%  │ │ docs/      │ │ ℹ️ 12 Low  │          │
│  └────────────┘ └────────────┘ └────────────┘          │
└─────────────────────────────────────────────────────────┘
```

### 3. AI Chat (`/repositories/[id]/chat`)

```
┌─────────────────────────────────────────────────────────┐
│  Chat — codeatlas-ai              [New Session] [History]│
├──────────────────────────────────────┬──────────────────┤
│  Chat History (left panel)           │  Code Preview    │
│  ─────────────────                   │  (right panel)   │
│  > How does authentication work?     │                  │
│                                      │  src/auth/       │
│  ◀ The authentication flow starts    │  service.py:42   │
│    with `authenticate_user()` in     │  ──────────────  │
│    `src/auth/service.py:42-78`.      │  def authenticate│
│    It validates credentials by       │  _user(...):     │
│    hashing the password using        │    ...           │
│    bcrypt and comparing with the     │                  │
│    stored hash. [src/auth/           │                  │
│    service.py:55-62]                 │                  │
│                                      │                  │
│  > What calls this function?         │                  │
│                                      │                  │
│  ◀ `authenticate_user` is called     │                  │
│    from: [src/api/routes/auth.py:20] │                  │
│    and [src/cli/commands.py:88]      │                  │
├──────────────────────────────────────┴──────────────────┤
│  [Type your question about codeatlas-ai...]      [Send▶] │
└─────────────────────────────────────────────────────────┘
```

### 4. Security Findings (`/repositories/[id]/security`)

```
┌─────────────────────────────────────────────────────────┐
│  Security — codeatlas-ai      [Scan Now] [Export SARIF] │
├─────────────────────────────────────────────────────────┤
│  Filters: [All Severity ▼] [All Types ▼] [Status: Open] │
├─────────────────────────────────────────────────────────┤
│  🔴 CRITICAL — Hardcoded AWS Secret Key                 │
│     src/config/settings.py:14                           │
│     AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MD..."           │
│     [View Remediation ▼]                                │
├─────────────────────────────────────────────────────────┤
│  🔴 CRITICAL — SQL Injection                            │
│     src/services/user.py:88                             │
│     query.raw(f"SELECT * FROM users WHERE id={uid}")    │
│     [View Remediation ▼]                                │
├─────────────────────────────────────────────────────────┤
│  🟠 HIGH — Container Running as Root                    │
│     Dockerfile:3                                        │
│     (No USER directive found)                           │
│     [View Remediation ▼]                                │
└─────────────────────────────────────────────────────────┘
```

---

## Component Library

All UI components are from **shadcn/ui** with custom tokens:

| Component | Usage |
|-----------|-------|
| `Card` | Repository cards, finding cards |
| `Badge` | Severity badges, language tags |
| `Dialog` | Import repository modal |
| `Tabs` | Repository view navigation |
| `Progress` | Indexing progress |
| `Textarea` | Chat input |
| `ScrollArea` | Chat history, file tree |
| `Separator` | Layout dividers |
| `Button` | All CTAs |
| `Alert` | Error/warning messages |
| `Skeleton` | Loading states |
| `Tooltip` | Icon labels |
| `Sheet` | Mobile side navigation |

---

## State Management

```typescript
// Global app state (Zustand)
interface AppStore {
  currentRepo: Repository | null;
  setCurrentRepo: (repo: Repository) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  theme: 'dark' | 'light';
}

// Chat state (Zustand)
interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  sendMessage: (content: string) => Promise<void>;
}
```

---

## Real-Time Features

| Feature | Implementation |
|---------|---------------|
| Indexing progress | SSE from `/repos/{id}/status/stream` |
| Chat response streaming | SSE from `/ai/chat/stream` |
| Security scan progress | SSE from `/security/scan/{id}/stream` |
| Notifications | WebSocket or polling (every 10s) |

---

## Design Tokens

```css
/* Dark mode primary (VSCode-inspired) */
--background: #1e1e2e;
--foreground: #cdd6f4;
--card: #181825;
--border: #313244;
--primary: #cba6f7;        /* Catppuccin Mauve */
--secondary: #89b4fa;      /* Catppuccin Blue */
--destructive: #f38ba8;    /* Catppuccin Red */
--muted: #585b70;
--accent: #a6e3a1;         /* Catppuccin Green */
```
