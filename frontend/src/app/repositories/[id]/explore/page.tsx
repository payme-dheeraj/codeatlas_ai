"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Folder, File, ChevronRight, ChevronDown, Code } from "lucide-react";
import dynamic from "next/dynamic";
import { Navbar } from "@/components/navbar";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-none" /> });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function fetchTree(repoId: string, path = "") {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/repos/${repoId}/files?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return [];
  return res.json();
}

async function fetchFileContent(repoId: string, path: string) {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/repos/${repoId}/file?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return null;
  return res.json();
}

interface TreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
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
  onSelect: (path: string, isDir: boolean) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const { data: children = [] } = useQuery({
    queryKey: ["tree", repoId, node.path],
    queryFn: () => fetchTree(repoId, node.path),
    enabled: node.type === "directory" && expanded,
  });

  const toggle = () => {
    if (node.type === "directory") {
      setExpanded((e) => !e);
      onSelect(node.path, true);
    } else {
      onSelect(node.path, false);
    }
  };

  return (
    <div>
      <button
        onClick={toggle}
        className={cn(
          "w-full flex items-center gap-1.5 px-2 py-1 rounded text-sm hover:bg-muted/50 transition-colors text-left",
          selectedPath === node.path && "bg-primary/10 text-primary"
        )}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
      >
        {node.type === "directory" ? (
          <>
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            <Folder className="h-4 w-4 shrink-0 text-secondary" />
          </>
        ) : (
          <>
            <span className="w-3.5" />
            <File className="h-4 w-4 shrink-0 text-muted-foreground" />
          </>
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {expanded && children.length > 0 && (
        <div>
          {children.map((child: TreeNode) => (
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
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [isDir, setIsDir] = useState(false);

  const { data: rootFiles = [], isLoading } = useQuery({
    queryKey: ["tree", repoId, ""],
    queryFn: () => fetchTree(repoId),
  });

  const { data: fileContent } = useQuery({
    queryKey: ["file-content", repoId, selectedPath],
    queryFn: () => fetchFileContent(repoId, selectedPath!),
    enabled: !!selectedPath && !isDir,
  });

  const handleSelect = (path: string, dir: boolean) => {
    setSelectedPath(path);
    setIsDir(dir);
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <div className="flex" style={{ height: "calc(100vh - 57px)" }}>
        {/* File tree */}
        <aside className="w-64 shrink-0 border-r border-border bg-card overflow-y-auto scrollbar-thin p-2">
          <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1">
            <Folder className="h-3.5 w-3.5" />
            Explorer
          </div>
          {isLoading ? (
            <div className="space-y-1 px-2">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="h-5 rounded bg-muted animate-pulse" />
              ))}
            </div>
          ) : rootFiles.length === 0 ? (
            <p className="px-2 text-xs text-muted-foreground">Repository not yet indexed or no files found.</p>
          ) : (
            rootFiles.map((node: TreeNode) => (
              <TreeItem
                key={node.path}
                node={node}
                repoId={repoId}
                selectedPath={selectedPath}
                onSelect={handleSelect}
                depth={0}
              />
            ))
          )}
        </aside>

        {/* File content */}
        <main className="flex-1 overflow-auto scrollbar-thin">
          {selectedPath && !isDir && fileContent ? (
            <div className="h-full flex flex-col">
              <div className="sticky top-0 border-b border-border bg-card/80 backdrop-blur px-4 py-2 flex items-center gap-2 shrink-0">
                <Code className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-mono text-muted-foreground truncate">{selectedPath}</span>
              </div>
              <div className="flex-1">
                <MonacoEditor
                  height="100%"
                  path={selectedPath}
                  value={typeof fileContent === "string" ? fileContent : fileContent?.content ?? JSON.stringify(fileContent, null, 2)}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    fontSize: 13,
                    lineNumbers: "on",
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    wordWrap: "off",
                    folding: true,
                    automaticLayout: true,
                    padding: { top: 12, bottom: 12 },
                  }}
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
              <Code className="h-10 w-10 opacity-30" />
              <p className="text-sm">Select a file from the tree to view its contents.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
