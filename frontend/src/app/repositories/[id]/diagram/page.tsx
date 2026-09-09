"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, RefreshCw, Download, Loader2 } from "lucide-react";
import { diagramsApi } from "@/lib/api";
import type { DiagramResponse } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

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

  const { data: fullDiagram } = useQuery({
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

  // Render mermaid when source changes
  useEffect(() => {
    if (!mermaidLoaded || !diagramRef.current || !current?.source_code) return;
    const el = diagramRef.current;
    el.innerHTML = current.source_code;
    import("mermaid").then((m) => {
      m.default.run({ nodes: [el] }).catch(console.error);
    });
  }, [mermaidLoaded, current?.source_code]);

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
          {isLoading || generating ? (
            <div className="w-full space-y-3">
              <Skeleton className="h-64 w-full" />
              <p className="text-xs text-center text-muted-foreground">{generating ? "Generating diagram…" : "Loading…"}</p>
            </div>
          ) : current ? (
            <div ref={diagramRef} className="w-full text-center" />
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
