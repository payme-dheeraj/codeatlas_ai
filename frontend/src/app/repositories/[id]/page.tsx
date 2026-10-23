"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderGit2, RefreshCw, MessageSquare, GitBranch,
  Shield, FileText, AlertTriangle, Loader2, Code2, ExternalLink, Trash2,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { reposApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { cn, timeAgo } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useIndexingSSE } from "@/lib/sse";

const TABS = [
  { id: "chat",     label: "Chat",     icon: MessageSquare, href: "chat" },
  { id: "diagram",  label: "Diagrams", icon: GitBranch,     href: "diagram" },
  { id: "docs",     label: "Docs",     icon: FileText,      href: "docs" },
  { id: "security", label: "Security", icon: Shield,        href: "security" },
  { id: "explore",  label: "Explore",  icon: Code2,         href: "explore" },
];

export default function RepositoryPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const queryClient = useQueryClient();
  const [indexProgress, setIndexProgress] = useState(0);
  const [showDelete, setShowDelete] = useState(false);

  const ACTIVE_STATUSES = ["cloning", "uploading", "analysing", "parsing", "embedding"];

  const { data: repo, isLoading } = useQuery({
    queryKey: ["repo", id],
    queryFn: () => reposApi.get(id),
    refetchInterval: (q) =>
      q.state.data && ACTIVE_STATUSES.includes(q.state.data.index_status) ? 3000 : false,
  });

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["health", id],
    queryFn: () => reposApi.health(id),
    enabled: repo?.index_status === "complete" || repo?.index_status === "cloned",
  });

  const { mutate: reindex, isPending: reindexing } = useMutation({
    mutationFn: () => reposApi.reindex(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["repo", id] }),
  });

  const { mutate: deleteRepo, isPending: deleting } = useMutation({
    mutationFn: () => reposApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repos"] });
      router.push("/repositories");
    },
  });

  useEffect(() => {
    if (!repo || !ACTIVE_STATUSES.includes(repo.index_status)) return;
    const cleanup = useIndexingSSE(id, (pct) => setIndexProgress(pct), true);
    return cleanup;
  }, [id, repo?.index_status]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-8 rounded-md" />
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-64" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28 rounded-lg" />)}
          </div>
        </main>
      </div>
    );
  }

  if (!repo) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="flex flex-col items-center justify-center h-64 gap-4">
          <AlertTriangle className="h-8 w-8 text-destructive" />
          <p className="text-muted-foreground">Repository not found.</p>
          <Link href="/repositories" className="text-primary hover:underline text-sm">
            ← Back to repositories
          </Link>
        </div>
      </div>
    );
  }

  const ts = repo.tech_stack;
  const st = repo.stats;
  const isActive = ACTIVE_STATUSES.includes(repo.index_status);
  const isDone = repo.index_status === "complete" || repo.index_status === "cloned";
  // A failed *re-index* must not hide data from an earlier successful run.
  const hasPriorIndex = !!repo.last_indexed_at;
  const statusBadgeVariant = isDone ? "success" : repo.index_status === "failed" ? "destructive" : "secondary";
  const healthScore = health?.composite_score ?? 0;
  const healthColor = healthScore >= 80 ? "text-accent" : healthScore >= 60 ? "text-secondary" : "text-destructive";

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <FolderGit2 className="h-7 w-7 text-primary shrink-0" />
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold">{repo.name}</h1>
                <Badge variant={statusBadgeVariant}>{repo.index_status}</Badge>
                {ts?.primary_language && <Badge variant="outline">{ts.primary_language}</Badge>}
              </div>
              {repo.description && (
                <p className="text-sm text-muted-foreground mt-0.5 max-w-xl">{repo.description}</p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {repo.url && (
              <Button variant="outline" size="sm" asChild>
                <a href={repo.url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-4 w-4 mr-2" /> View Source
                </a>
              </Button>
            )}
            <Button
              variant="outline" size="sm"
              onClick={() => reindex()}
              disabled={reindexing || isActive}
            >
              <RefreshCw className={cn("h-4 w-4 mr-2", (reindexing || isActive) && "animate-spin")} />
              Re-index
            </Button>
            <Button
              variant="outline" size="sm"
              onClick={() => setShowDelete(true)}
              className="text-destructive hover:bg-destructive/10 hover:text-destructive border-destructive/30"
            >
              <Trash2 className="h-4 w-4 mr-2" /> Delete
            </Button>
          </div>
        </div>

        {/* Active indexing progress */}
        {isActive && (
          <Card>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-secondary" />
                <span className="text-secondary font-medium capitalize">{repo.index_status}…</span>
                <span className="ml-auto text-sm text-muted-foreground">{indexProgress}%</span>
              </div>
              <Progress value={indexProgress || 15} className="h-2" />
              <p className="text-xs text-muted-foreground">This may take a few minutes depending on repository size.</p>
            </CardContent>
          </Card>
        )}

        {/* Stats row */}
        {st && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Files", value: st.total_files.toLocaleString() },
              { label: "LOC", value: st.total_lines >= 1000 ? `${(st.total_lines/1000).toFixed(1)}k` : st.total_lines.toString() },
              { label: "Commits", value: st.commits.toLocaleString() },
              { label: "Contributors", value: st.contributors.toLocaleString() },
              { label: "Modules", value: st.module_count.toString() },
              { label: "Dependencies", value: st.dependencies.toLocaleString() },
            ].map(({ label, value }) => (
              <Card key={label}>
                <CardContent className="p-4 text-center">
                  <p className="text-xl font-bold">{value}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Tech Stack breakdown */}
        {ts && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: "Languages",       items: ts.languages,       color: "bg-primary/10 text-primary" },
              { title: "Frameworks",      items: ts.frameworks,      color: "bg-secondary/10 text-secondary" },
              { title: "Databases",       items: ts.databases,       color: "bg-accent/10 text-accent" },
              { title: "Infrastructure",  items: ts.infrastructure,  color: "bg-destructive/10 text-destructive" },
              { title: "Package Managers",items: ts.package_managers, color: "bg-muted text-muted-foreground" },
              { title: "Tools",           items: ts.tools,           color: "bg-muted text-muted-foreground" },
            ]
              .filter(({ items }) => items.length > 0)
              .map(({ title, items, color }) => (
                <Card key={title}>
                  <CardContent className="p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">{title}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((item) => (
                        <span key={item} className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
          </div>
        )}

        {/* Health score */}
        {healthLoading && (
          <Card>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-muted-foreground">Health Score</span>
                <Skeleton className="h-8 w-20" />
              </div>
              <Skeleton className="h-2.5 w-full" />
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            </CardContent>
          </Card>
        )}
        {health && (
          <Card>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-muted-foreground">Health Score</span>
                <span className={cn("text-2xl font-bold", healthColor)}>
                  {healthScore}<span className="text-base text-muted-foreground">/100</span>
                </span>
              </div>
              <Progress value={healthScore} className="h-2.5" />
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {Object.entries(health.pillars).map(([key, val]) => (
                  <div key={key} className="text-center rounded-md bg-muted/50 py-2 px-1">
                    <p className="font-semibold text-sm">{val.score}/25</p>
                    <p className="text-xs text-muted-foreground capitalize">{key.replace("_", " ")}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Navigation tabs */}
        <Card className="overflow-hidden">
          <div className="flex overflow-x-auto border-b border-border">
            {TABS.map((tab) => (
              <Link
                key={tab.id}
                href={`/repositories/${id}/${tab.href}`}
                className="flex items-center gap-2 px-5 py-3 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors border-r border-border last:border-r-0 whitespace-nowrap"
              >
                <tab.icon className="h-4 w-4 shrink-0" />
                {tab.label}
              </Link>
            ))}
          </div>
          <div className="p-8 text-center">
            {isDone ? (
              <div className="space-y-3">
                <p className="text-accent font-medium text-lg">✅ Repository ready</p>
                <p className="text-sm text-muted-foreground">Select a tab to explore chat, diagrams, docs, or security findings.</p>
                <div className="flex flex-wrap gap-3 justify-center mt-4">
                  {TABS.map(tab => (
                    <Button key={tab.id} variant="outline" size="sm" asChild>
                      <Link href={`/repositories/${id}/${tab.href}`}>
                        <tab.icon className="h-4 w-4 mr-2" /> {tab.label}
                      </Link>
                    </Button>
                  ))}
                </div>
              </div>
            ) : repo.index_status === "failed" ? (
              <div className="space-y-3">
                <AlertTriangle className="h-8 w-8 text-destructive mx-auto" />
                <p className="text-destructive font-medium">
                  {hasPriorIndex ? "Latest indexing run failed" : "Indexing failed"}
                </p>
                {repo.error_message && <p className="text-xs text-muted-foreground font-mono">{repo.error_message}</p>}
                {hasPriorIndex && (
                  <p className="text-sm text-muted-foreground">
                    Data from the previous successful index is still available.
                  </p>
                )}
                <Button variant="outline" size="sm" onClick={() => reindex()} disabled={reindexing}>
                  {reindexing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Retry indexing
                </Button>
                {hasPriorIndex && (
                  <div className="flex flex-wrap gap-3 justify-center pt-2">
                    {TABS.map(tab => (
                      <Button key={tab.id} variant="outline" size="sm" asChild>
                        <Link href={`/repositories/${id}/${tab.href}`}>
                          <tab.icon className="h-4 w-4 mr-2" /> {tab.label}
                        </Link>
                      </Button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mx-auto" />
                <p className="text-muted-foreground capitalize">{repo.index_status}…</p>
              </div>
            )}
          </div>
        </Card>
      </main>

      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete repository?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong>{repo.name}</strong> and all its indexed data will be permanently deleted.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); deleteRepo(); window.location.href = "/repositories"; }}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
