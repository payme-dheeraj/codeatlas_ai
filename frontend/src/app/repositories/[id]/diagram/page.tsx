"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, RefreshCw, Download, AlertTriangle } from "lucide-react";
import { diagramsApi } from "@/lib/api";
import type { DiagramResponse } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";

const DIAGRAM_TYPES = [
  { id: "architecture", label: "Architecture" },
  { id: "dependency", label: "Dependencies" },
  { id: "sequence", label: "Sequence" },
  { id: "er", label: "ER Diagram" },
  { id: "deployment", label: "Deployment" },
];

export default function DiagramPage({ params }: { params: { id: string } }) {
  const { id: repoId } = params;
  const [activeType, setActiveType] = useState("architecture");
  const [mermaidLoaded, setMermaidLoaded] = useState(false);
  const [polling, setPolling] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const diagramRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  // Load mermaid dynamically
  useEffect(() => {
    import("mermaid").then((m) => {
      m.default.initialize({ startOnLoad: false, theme: "dark" });
      setMermaidLoaded(true);
    });
  }, []);

  const { data: diagrams = [], isLoading } = useQuery({
    queryKey: ["diagrams", repoId],
    queryFn: () => diagramsApi.list(repoId),
    refetchInterval: polling ? 4000 : false,
  });

  const diagramExists = (diagrams as DiagramResponse[]).some((d) => d.diagram_type === activeType);

  const { data: fullDiagram, isLoading: diagramLoading } = useQuery({
    queryKey: ["diagram-detail", repoId, activeType],
    queryFn: () => diagramsApi.get(repoId, activeType),
    enabled: diagramExists,
  });

  const current = fullDiagram ?? (diagrams as DiagramResponse[]).find((d) => d.diagram_type === activeType);

  const queryClient2 = useQueryClient();

  useEffect(() => {
    const found = (diagrams as DiagramResponse[]).find((d) => d.diagram_type === activeType);
    if (polling && found) {
      setPolling(false);
      queryClient2.invalidateQueries({ queryKey: ["diagram-detail", repoId, activeType] });
    }
  }, [diagrams, activeType, polling]);

  const { mutate: generate, isPending: generating } = useMutation({
    mutationFn: () => diagramsApi.generate(repoId, [activeType]),
    onSuccess: () => {
      setPolling(true);
      setTimeout(() => setPolling(false), 120_000);
    },
  });

  // Render mermaid when source changes.
  // NOTE: `mermaid.run()` is deliberately avoided — it stamps the node with
  // `data-processed` and silently skips it on later renders, which left the
  // raw source text visible when switching diagram types.
  useEffect(() => {
    const el = diagramRef.current;
    const source = current?.source_code?.trim();
    if (!mermaidLoaded || !el || !source) return;

    let cancelled = false;
    setRenderError(null);
    el.innerHTML = "";

    import("mermaid")
      .then(async (m) => {
        const mermaid = m.default;
        // Unique id per render so mermaid never reuses a stale DOM node.
        const id = `mermaid-${activeType}-${Date.now()}`;
        const { svg } = await mermaid.render(id, source);
        if (cancelled || !diagramRef.current) return;
        diagramRef.current.innerHTML = svg;
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (diagramRef.current) diagramRef.current.innerHTML = "";
        setRenderError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [mermaidLoaded, current?.source_code, activeType]);

  const handleDownload = () => {
    if (!current) return;
    const blob = new Blob([current.source_code ?? ""], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${activeType}.mmd`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <GitBranch className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold">Diagrams</h1>
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

        {/* Type tabs */}
        <div className="flex gap-2 flex-wrap">
          {DIAGRAM_TYPES.map((t) => {
            const exists = (diagrams as DiagramResponse[]).some((d) => d.diagram_type === t.id);
            return (
              <Button
                key={t.id}
                variant={activeType === t.id ? "default" : "outline"}
                size="sm"
                onClick={() => setActiveType(t.id)}
                className={cn(!exists && "opacity-50")}
              >
                {t.label}
                {exists && <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-accent" />}
              </Button>
            );
          })}
        </div>

        {/* Diagram view */}
        <Card className="min-h-[400px] flex items-center justify-center overflow-auto p-6">
          {isLoading || generating || polling || diagramLoading ? (
            <div className="w-full space-y-3">
              <Skeleton className="h-64 w-full" />
              <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                <Spinner className="h-3 w-3" />
                {generating || polling
                  ? "Generating diagram — this can take a minute…"
                  : "Loading…"}
              </p>
            </div>
          ) : current ? (
            <div className="w-full">
              {renderError && (
                <Alert variant="destructive" className="mb-4 text-left">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription className="space-y-2">
                    <p>This diagram could not be rendered — the generated source is not valid Mermaid.</p>
                    <p className="font-mono text-xs opacity-80">{renderError}</p>
                    <p className="text-xs">Try regenerating it, or inspect the source below.</p>
                  </AlertDescription>
                </Alert>
              )}
              {!mermaidLoaded && !renderError && (
                <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground py-8">
                  <Spinner className="h-3 w-3" /> Preparing renderer…
                </p>
              )}
              <div
                ref={diagramRef}
                className={cn("w-full text-center [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full", renderError && "hidden")}
              />
            </div>
          ) : (
            <div className="text-center text-muted-foreground space-y-3">
              <GitBranch className="h-10 w-10 mx-auto opacity-30" />
              <p>No {activeType} diagram yet.</p>
              <Button variant="ghost" size="sm" onClick={() => generate()}>
                Generate it →
              </Button>
            </div>
          )}
        </Card>

        {/* Raw source */}
        {current?.source_code && (
          <Card>
            <details>
              <summary className="cursor-pointer px-4 py-3 text-sm text-muted-foreground hover:text-foreground select-none flex items-center gap-2">
                View source <Badge variant="outline" className="text-xs">{current.diagram_format}</Badge>
              </summary>
              <pre className="overflow-x-auto p-4 text-xs font-mono border-t border-border">
                {current.source_code}
              </pre>
            </details>
          </Card>
        )}
      </main>
    </div>
  );
}
