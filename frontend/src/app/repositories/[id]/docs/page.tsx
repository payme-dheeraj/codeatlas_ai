"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, RefreshCw, Download, Loader2 } from "lucide-react";
import { docsApi } from "@/lib/api";
import type { DocumentResponse } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { cn, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";

const DOC_TYPES = [
  { id: "readme", label: "README" },
  { id: "api_reference", label: "API Reference" },
  { id: "deployment_guide", label: "Deployment Guide" },
  { id: "architecture_decision", label: "ADR" },
  { id: "wiki", label: "Wiki" },
  { id: "changelog", label: "Changelog" },
  { id: "onboarding", label: "Onboarding" },
];

export default function DocsPage({ params }: { params: { id: string } }) {
  const { id: repoId } = params;
  const [activeType, setActiveType] = useState("readme");
  const [polling, setPolling] = useState(false);
  const queryClient = useQueryClient();

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["docs", repoId],
    queryFn: () => docsApi.list(repoId),
    refetchInterval: polling ? 4000 : false,
  });

  const docExists = (docs as DocumentResponse[]).some((d) => d.doc_type === activeType);

  const { data: fullDoc, isLoading: docLoading } = useQuery({
    queryKey: ["doc-detail", repoId, activeType],
    queryFn: () => docsApi.get(repoId, activeType),
    enabled: docExists,
  });

  const current = fullDoc ?? (docs as DocumentResponse[]).find((d) => d.doc_type === activeType);

  useEffect(() => {
    const found = (docs as DocumentResponse[]).find((d) => d.doc_type === activeType);
    if (polling && found) {
      setPolling(false);
      queryClient.invalidateQueries({ queryKey: ["doc-detail", repoId, activeType] });
    }
  }, [docs, activeType, polling]);

  const { mutate: generate, isPending: generating } = useMutation({
    mutationFn: () => docsApi.generate(repoId, [activeType]),
    onSuccess: () => {
      setPolling(true);
      setTimeout(() => setPolling(false), 120_000);
    },
  });

  const handleDownload = () => {
    if (!current) return;
    const blob = new Blob([current.content_md ?? current.content ?? ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${activeType}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileText className="h-6 w-6 text-primary" />
            <div>
              <h1 className="text-xl font-bold">Documentation</h1>
              {current && (
                <p className="text-xs text-muted-foreground">
                  Version {current.version} · Generated {timeAgo(current.created_at)}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {current && (
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="h-4 w-4 mr-2" /> Download
              </Button>
            )}
            <Button size="sm" onClick={() => generate()} disabled={generating}>
              <RefreshCw className={cn("h-4 w-4 mr-2", generating && "animate-spin")} />
              {generating ? "Generating…" : "Generate"}
            </Button>
          </div>
        </div>

        <div className="flex gap-6">
          {/* Doc type nav */}
          <nav className="w-40 shrink-0 space-y-1">
            {DOC_TYPES.map((t) => {
              const exists = (docs as DocumentResponse[]).some((d) => d.doc_type === t.id);
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveType(t.id)}
                  className={cn(
                    "w-full text-left rounded-md px-3 py-2 text-sm transition-colors",
                    activeType === t.id
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    !exists && "opacity-50"
                  )}
                >
                  {t.label}
                  {exists && <span className="float-right h-1.5 w-1.5 rounded-full bg-accent mt-1.5" />}
                </button>
              );
            })}
          </nav>

          {/* Content area */}
          <Card className="flex-1 min-h-[500px]">
            {isLoading || generating || polling || docLoading ? (
              <div className="p-6 space-y-3">
                <Skeleton className="h-6 w-1/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <p className="flex items-center gap-2 text-xs text-muted-foreground pt-2">
                  <Spinner className="h-3 w-3" />
                  {generating || polling
                    ? "Generating documentation — this can take a minute…"
                    : "Loading…"}
                </p>
              </div>
            ) : current ? (
              <div className="p-6 overflow-auto">
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">
                  {current.content_md ?? current.content ?? "(no content)"}
                </pre>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-muted-foreground gap-3">
                <FileText className="h-10 w-10 opacity-30" />
                <p>No {DOC_TYPES.find(t => t.id === activeType)?.label} generated yet.</p>
                <Button variant="ghost" size="sm" onClick={() => generate()}>
                  Generate it →
                </Button>
              </div>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}
