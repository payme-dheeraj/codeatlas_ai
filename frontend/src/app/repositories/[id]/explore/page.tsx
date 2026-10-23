"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Folder, FolderOpen, File, ChevronRight, ChevronDown, Code,
  Search, Copy, Check, Download, FileWarning, AlertCircle,
} from "lucide-react";
import dynamic from "next/dynamic";
import { Navbar } from "@/components/navbar";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionLoader, Spinner } from "@/components/ui/spinner";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-none" /> });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchTree(repoId: string, path = ""): Promise<TreeNode[]> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/repos/${repoId}/files?${params}`, { headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

async function fetchFileContent(repoId: string, path: string): Promise<FileContent> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/repos/${repoId}/file?${params}`, { headers: authHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

interface TreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number | null;
}

interface FileContent {
  path: string;
  content: string | null;
  size: number;
  is_binary?: boolean;
  truncated?: boolean;
}

/** Human-readable byte size. */
function formatBytes(bytes?: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Map a file extension to a Monaco language id. */
function languageFor(path: string): string | undefined {
  const ext = path.split(".").pop()?.toLowerCase();
  const map: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", java: "java", go: "go", rs: "rust", rb: "ruby", php: "php",
    cs: "csharp", cpp: "cpp", c: "c", kt: "kotlin", swift: "swift", scala: "scala",
    json: "json", yaml: "yaml", yml: "yaml", toml: "ini", sql: "sql",
    md: "markdown", html: "html", css: "css", scss: "scss", sh: "shell",
    dockerfile: "dockerfile", tf: "hcl", xml: "xml",
  };
  return ext ? map[ext] : undefined;
}

function TreeItem({
  node,
  repoId,
  selectedPath,
  onSelect,
  depth,
}: {
  node: TreeNode;
  repoId: string;
  selectedPath: string | null;
  onSelect: (node: TreeNode) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const { data: children = [], isFetching } = useQuery({
    queryKey: ["tree", repoId, node.path],
    queryFn: () => fetchTree(repoId, node.path),
    enabled: node.type === "directory" && expanded,
  });

  const toggle = () => {
    if (node.type === "directory") setExpanded((e) => !e);
    onSelect(node);
  };

  return (
    <div>
      <button
        onClick={toggle}
        title={node.path}
        className={cn(
          "group w-full flex items-center gap-1.5 px-2 py-1 rounded text-sm hover:bg-muted/50 transition-colors text-left",
          selectedPath === node.path && "bg-primary/10 text-primary"
        )}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {node.type === "directory" ? (
          <>
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            {expanded ? (
              <FolderOpen className="h-4 w-4 shrink-0 text-secondary" />
            ) : (
              <Folder className="h-4 w-4 shrink-0 text-secondary" />
            )}
          </>
        ) : (
          <>
            <span className="w-3.5 shrink-0" />
            <File className="h-4 w-4 shrink-0 text-muted-foreground" />
          </>
        )}
        <span className="truncate flex-1">{node.name}</span>
        {node.type === "file" && node.size != null && (
          <span className="shrink-0 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
            {formatBytes(node.size)}
          </span>
        )}
        {isFetching && <Spinner className="h-3 w-3 shrink-0" />}
      </button>
      {expanded && (
        <div>
          {isFetching && children.length === 0 && (
            <p
              className="py-1 text-xs text-muted-foreground"
              style={{ paddingLeft: `${8 + (depth + 1) * 14 + 22}px` }}
            >
              Loading…
            </p>
          )}
          {!isFetching && children.length === 0 && (
            <p
              className="py-1 text-xs text-muted-foreground italic"
              style={{ paddingLeft: `${8 + (depth + 1) * 14 + 22}px` }}
            >
              empty
            </p>
          )}
          {children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              repoId={repoId}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExplorePage({ params }: { params: { id: string } }) {
  const { id: repoId } = params;
  const [selected, setSelected] = useState<TreeNode | null>(null);
  const [filter, setFilter] = useState("");
  const [copied, setCopied] = useState(false);

  const { data: rootFiles = [], isLoading } = useQuery({
    queryKey: ["tree", repoId, ""],
    queryFn: () => fetchTree(repoId),
  });

  const isDir = selected?.type === "directory";

  const {
    data: file,
    isFetching: fileLoading,
    error: fileError,
  } = useQuery({
    queryKey: ["file-content", repoId, selected?.path],
    queryFn: () => fetchFileContent(repoId, selected!.path),
    enabled: !!selected && !isDir,
    retry: false,
  });

  // Children of the selected directory, shown as a listing in the main pane.
  const { data: dirChildren = [], isFetching: dirLoading } = useQuery({
    queryKey: ["tree", repoId, selected?.path],
    queryFn: () => fetchTree(repoId, selected!.path),
    enabled: !!selected && isDir,
  });

  const visibleRoots = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rootFiles;
    return rootFiles.filter((n) => n.name.toLowerCase().includes(q));
  }, [rootFiles, filter]);

  const handleCopy = async () => {
    if (!file?.content) return;
    await navigator.clipboard.writeText(file.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownload = () => {
    if (!file?.content || !selected) return;
    const blob = new Blob([file.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selected.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  /** Shared path header above the main pane. */
  const PathHeader = ({ children }: { children?: React.ReactNode }) => (
    <div className="sticky top-0 z-10 border-b border-border bg-card/80 backdrop-blur px-4 py-2 flex items-center gap-2 shrink-0">
      {isDir ? (
        <FolderOpen className="h-4 w-4 text-secondary shrink-0" />
      ) : (
        <Code className="h-4 w-4 text-muted-foreground shrink-0" />
      )}
      <span className="text-sm font-mono text-muted-foreground truncate">{selected?.path}</span>
      {file?.size != null && !isDir && (
        <Badge variant="outline" className="text-[10px] shrink-0">{formatBytes(file.size)}</Badge>
      )}
      {file?.truncated && (
        <Badge variant="warning" className="text-[10px] shrink-0">truncated</Badge>
      )}
      <div className="ml-auto flex items-center gap-1 shrink-0">{children}</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <div className="flex" style={{ height: "calc(100vh - 57px)" }}>
        {/* File tree */}
        <aside className="w-72 shrink-0 border-r border-border bg-card flex flex-col">
          <div className="px-3 pt-3 pb-2 space-y-2 border-b border-border">
            <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium uppercase tracking-wider">
              <Folder className="h-3.5 w-3.5" />
              Explorer
              {rootFiles.length > 0 && (
                <span className="ml-auto normal-case tracking-normal">{rootFiles.length} items</span>
              )}
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <Input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter top-level…"
                className="pl-8 h-8 text-xs"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
            {isLoading ? (
              <div className="space-y-1.5 px-1">
                {[...Array(10)].map((_, i) => (
                  <Skeleton key={i} className="h-5" style={{ width: `${60 + ((i * 13) % 35)}%` }} />
                ))}
              </div>
            ) : rootFiles.length === 0 ? (
              <div className="px-2 py-8 text-center space-y-2">
                <FileWarning className="h-8 w-8 mx-auto text-muted-foreground opacity-40" />
                <p className="text-xs text-muted-foreground">
                  No files found. The repository may still be indexing, or the import contained no files.
                </p>
              </div>
            ) : visibleRoots.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                Nothing matches &quot;{filter}&quot;.
              </p>
            ) : (
              visibleRoots.map((node) => (
                <TreeItem
                  key={node.path}
                  node={node}
                  repoId={repoId}
                  selectedPath={selected?.path ?? null}
                  onSelect={setSelected}
                  depth={0}
                />
              ))
            )}
          </div>
        </aside>

        {/* Main pane */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {!selected ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
              <Code className="h-10 w-10 opacity-30" />
              <p className="text-sm">Select a file from the tree to view its contents.</p>
            </div>
          ) : isDir ? (
            <>
              <PathHeader />
              {dirLoading ? (
                <SectionLoader label="Loading folder…" className="flex-1" />
              ) : dirChildren.length === 0 ? (
                <div className="flex flex-col items-center justify-center flex-1 text-muted-foreground gap-2">
                  <Folder className="h-10 w-10 opacity-30" />
                  <p className="text-sm">This folder is empty.</p>
                </div>
              ) : (
                <div className="flex-1 overflow-auto scrollbar-thin divide-y divide-border">
                  {dirChildren.map((child) => (
                    <button
                      key={child.path}
                      onClick={() => setSelected(child)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-muted/40 transition-colors"
                    >
                      {child.type === "directory" ? (
                        <Folder className="h-4 w-4 text-secondary shrink-0" />
                      ) : (
                        <File className="h-4 w-4 text-muted-foreground shrink-0" />
                      )}
                      <span className="truncate">{child.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground shrink-0">
                        {child.type === "file" ? formatBytes(child.size) : "—"}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : fileLoading ? (
            <>
              <PathHeader />
              <SectionLoader label="Loading file…" className="flex-1" />
            </>
          ) : fileError ? (
            <>
              <PathHeader />
              <div className="flex flex-col items-center justify-center flex-1 text-muted-foreground gap-3 px-6 text-center">
                <AlertCircle className="h-10 w-10 text-destructive opacity-70" />
                <p className="text-sm text-destructive">Could not load this file.</p>
                <p className="text-xs font-mono">
                  {fileError instanceof Error ? fileError.message : String(fileError)}
                </p>
              </div>
            </>
          ) : file?.is_binary ? (
            <>
              <PathHeader />
              <div className="flex flex-col items-center justify-center flex-1 text-muted-foreground gap-3 px-6 text-center">
                <FileWarning className="h-10 w-10 opacity-40" />
                <p className="text-sm">This is a binary file and cannot be previewed.</p>
                <p className="text-xs">
                  {selected.name} · {formatBytes(file.size)}
                </p>
              </div>
            </>
          ) : (
            <>
              <PathHeader>
                <Button variant="ghost" size="sm" onClick={handleCopy} title="Copy contents">
                  {copied ? <Check className="h-3.5 w-3.5 text-accent" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
                <Button variant="ghost" size="sm" onClick={handleDownload} title="Download file">
                  <Download className="h-3.5 w-3.5" />
                </Button>
              </PathHeader>
              <div className="flex-1 min-h-0">
                <MonacoEditor
                  height="100%"
                  path={selected.path}
                  language={languageFor(selected.path)}
                  value={file?.content ?? ""}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    fontSize: 13,
                    lineNumbers: "on",
                    minimap: { enabled: true, maxColumn: 70 },
                    scrollBeyondLastLine: false,
                    wordWrap: "off",
                    folding: true,
                    automaticLayout: true,
                    renderLineHighlight: "line",
                    padding: { top: 12, bottom: 12 },
                  }}
                />
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
