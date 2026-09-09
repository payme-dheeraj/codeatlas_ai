"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FolderGit2,
  Shield,
  MessageSquare,
  Plus,
  ArrowRight,
  Activity,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { reposApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { timeAgo, cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function StatCard({
  label,
  value,
  icon: Icon,
  iconClass,
  sub,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  iconClass?: string;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5 flex items-center gap-4">
        <div className={cn("rounded-md p-2.5 bg-muted", iconClass)}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, "success" | "secondary" | "outline" | "destructive"> = {
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
  const labels: Record<string, string> = {
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
  return (
    <Badge variant={variantMap[status] ?? "outline"}>
      {labels[status] ?? status}
    </Badge>
  );
}

export default function DashboardPage() {
  const { data: repos = [], isLoading } = useQuery({
    queryKey: ["repos"],
    queryFn: reposApi.list,
  });

  const DONE_STATUSES = ["complete", "cloned"];
  const ACTIVE_STATUSES = ["cloning", "uploading", "analysing", "parsing", "embedding"];
  const indexedCount = repos.filter((r) => DONE_STATUSES.includes(r.index_status)).length;
  const indexingCount = repos.filter((r) => ACTIVE_STATUSES.includes(r.index_status)).length;
  const failedCount = repos.filter((r) => r.index_status === "failed").length;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            <p className="text-muted-foreground text-sm mt-1">
              AI-powered code intelligence at a glance
            </p>
          </div>
          <Button asChild>
            <Link href="/repositories/new">
              <Plus className="h-4 w-4 mr-2" />
              Import Repository
            </Link>
          </Button>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Repositories"
            value={isLoading ? "—" : repos.length}
            icon={FolderGit2}
            iconClass="text-primary"
          />
          <StatCard
            label="Indexed"
            value={isLoading ? "—" : indexedCount}
            icon={Activity}
            iconClass="text-accent"
          />
          <StatCard
            label="Security Findings"
            value={isLoading ? "—" : failedCount > 0 ? `${failedCount} ⚠️` : "0"}
            icon={Shield}
            iconClass="text-[hsl(var(--severity-high))]"
            sub="across all repos"
          />
          <StatCard
            label="AI Queries"
            value="—"
            icon={MessageSquare}
            iconClass="text-secondary"
            sub="total sessions"
          />
        </div>

        {/* Recent repositories */}
        <Card>
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="font-semibold">Recent Repositories</h2>
            <Link
              href="/repositories"
              className="text-sm text-primary hover:underline flex items-center gap-1"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          {isLoading ? (
            <div className="divide-y divide-border">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="px-5 py-4 flex items-center gap-4">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-4 w-24 ml-auto" />
                </div>
              ))}
            </div>
          ) : repos.length === 0 ? (
            <div className="px-5 py-12 text-center text-muted-foreground">
              <FolderGit2 className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p>No repositories yet.</p>
              <Link
                href="/repositories/new"
                className="mt-3 inline-block text-sm text-primary hover:underline"
              >
                Import your first repository →
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {repos.slice(0, 8).map((repo) => (
                <Link
                  key={repo.id}
                  href={`/repositories/${repo.id}`}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-muted/50 transition-colors"
                >
                  <FolderGit2 className="h-5 w-5 text-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">{repo.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {repo.tech_stack?.primary_language ?? "Unknown"} ·{" "}
                      {repo.stats ? repo.stats.total_files.toLocaleString() : "0"} files
                    </p>
                  </div>
                  <div className="ml-auto flex items-center gap-3 shrink-0">
                    <StatusBadge status={repo.index_status} />
                    <span className="hidden sm:block text-xs text-muted-foreground">
                      {timeAgo(repo.updated_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
