"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderGit2, Plus, RefreshCw, ExternalLink, Search, Trash2 } from "lucide-react";
import { reposApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { timeAgo } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Input } from "@/components/ui/input";
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

const STATUS_VARIANT: Record<string, "success" | "secondary" | "outline" | "destructive"> = {
  complete: "success",
  cloned: "success",
  cloning: "secondary",
  uploading: "secondary",
  analysing: "secondary",
  parsing: "secondary",
  embedding: "secondary",
  pending: "outline",
  failed: "destructive",
};

const STATUS_LABEL: Record<string, string> = {
  complete: "✅ Indexed",
  cloned: "✅ Cloned",
  cloning: "⏳ Cloning",
  uploading: "⏳ Uploading",
  analysing: "⏳ Analysing",
  parsing: "⏳ Parsing",
  embedding: "⏳ Embedding",
  pending: "🕐 Pending",
  failed: "❌ Failed",
};

export default function RepositoriesPage() {
  const [filter, setFilter] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const queryClient = useQueryClient();

  const { data: repos = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["repos"],
    queryFn: reposApi.list,
    refetchInterval: 10_000,
  });

  const { mutate: deleteRepo, isPending: deleting } = useMutation({
    mutationFn: (id: string) => reposApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repos"] });
      setDeleteTarget(null);
    },
  });

  const filtered = repos.filter((r) =>
    r.name.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold">Repositories</h1>
            <p className="text-sm text-muted-foreground mt-1">{repos.length} repositories imported</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Button asChild size="sm">
              <Link href="/repositories/new">
                <Plus className="h-4 w-4 mr-2" /> Import
              </Link>
            </Button>
          </div>
        </div>

        {/* Filter */}
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Filter repositories…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-9"
          />
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => (
              <Card key={i}>
                <CardContent className="p-5 space-y-2">
                  <Skeleton className="h-5 w-48" />
                  <Skeleton className="h-4 w-64" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="p-16 text-center">
              <FolderGit2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-40" />
              <h3 className="font-semibold text-lg mb-2">
                {filter ? "No matches found" : "No repositories yet"}
              </h3>
              <p className="text-muted-foreground text-sm mb-6">
                {filter
                  ? `No repositories match "${filter}"`
                  : "Import a Git repository to get started with AI code analysis."}
              </p>
              {!filter && (
                <Button asChild>
                  <Link href="/repositories/new">
                    <Plus className="h-4 w-4 mr-2" /> Import Repository
                  </Link>
                </Button>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {filtered.map((repo) => (
              <Link
                key={repo.id}
                href={`/repositories/${repo.id}`}
                className="block"
              >
                <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                  <CardContent className="p-5">
                    <div className="flex items-start gap-4">
                      <FolderGit2 className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="font-semibold truncate">{repo.name}</span>
                          <Badge variant={STATUS_VARIANT[repo.index_status] ?? "outline"}>
                            {STATUS_LABEL[repo.index_status] ?? repo.index_status}
                          </Badge>
                          {repo.tech_stack?.primary_language && (
                            <Badge variant="outline" className="text-xs">{repo.tech_stack.primary_language}</Badge>
                          )}
                        </div>
                        {repo.description && (
                          <p className="text-sm text-muted-foreground mt-1 truncate">
                            {repo.description}
                          </p>
                        )}
                        <div className="flex flex-wrap gap-3 mt-2 text-xs text-muted-foreground">
                          {repo.stats && <span>{repo.stats.total_files.toLocaleString()} files</span>}
                          {repo.stats?.total_lines ? <span>{(repo.stats.total_lines / 1000).toFixed(0)}k LOC</span> : null}
                          <span>Updated {timeAgo(repo.updated_at)}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); setDeleteTarget({ id: repo.id, name: repo.name }); }}
                        className="p-1 rounded hover:bg-destructive/10 hover:text-destructive text-muted-foreground transition-colors shrink-0"
                        title="Delete repository"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open: boolean) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete repository?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong>{deleteTarget?.name}</strong> and all its indexed data will be permanently deleted.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); deleteTarget && deleteRepo(deleteTarget.id); }}
              disabled={deleting}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              {deleting && <Spinner className="mr-2 text-destructive-foreground" />}
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
