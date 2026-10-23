"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, Download, RefreshCw, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import { securityApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { cn, severityColor, timeAgo } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionLoader, Spinner } from "@/components/ui/spinner";
import type { SecurityFinding } from "@/lib/api";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

const SEVERITY_BADGE: Record<string, "destructive" | "warning" | "secondary" | "outline"> = {
  critical: "destructive",
  high: "destructive",
  medium: "warning",
  low: "secondary",
  info: "outline",
};

const SEVERITY_EMOJI: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🔵",
  info: "ℹ️",
};

function FindingCard({ finding }: { finding: SecurityFinding }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-muted/30 transition-colors"
      >
        <Badge variant={SEVERITY_BADGE[finding.severity] ?? "outline"} className="shrink-0 mt-0.5">
          {SEVERITY_EMOJI[finding.severity]} {finding.severity}
        </Badge>
        <div className="flex-1 min-w-0">
          <p className="font-medium">{finding.title}</p>
          {finding.file_path && (
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              {finding.file_path}{finding.start_line ? `:${finding.start_line}` : ""}
            </p>
          )}
        </div>
        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />}
      </button>
      {open && (
        <div className="border-t border-border p-4 space-y-3">
          {finding.description && (
            <p className="text-sm text-muted-foreground">{finding.description}</p>
          )}
          {finding.snippet && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Vulnerable code</p>
              <pre className="text-xs rounded-md bg-muted p-3 overflow-x-auto font-mono leading-relaxed">{finding.snippet}</pre>
            </div>
          )}
          {/* `remediation` is a JSON object from the AI generator, never a string. */}
          {finding.remediation && (
            <div className="rounded-md bg-accent/10 border border-accent/20 p-3 space-y-2">
              <p className="text-sm font-medium text-accent">✅ Remediation</p>
              {finding.remediation.vulnerability && (
                <p className="text-sm text-muted-foreground">{finding.remediation.vulnerability}</p>
              )}
              {finding.remediation.fixed_code && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Suggested fix</p>
                  <pre className="text-xs rounded-md bg-background/60 p-3 overflow-x-auto font-mono leading-relaxed">
                    {finding.remediation.fixed_code}
                  </pre>
                </div>
              )}
              {!!finding.remediation.recommendations?.length && (
                <ul className="list-disc pl-5 space-y-0.5">
                  {finding.remediation.recommendations.map((rec, i) => (
                    <li key={i} className="text-sm text-muted-foreground">{rec}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>Category: <span className="font-mono">{finding.category}</span></span>
            <span>Rule: <span className="font-mono">{finding.rule_id}</span></span>
            <span>Scanner: <span className="font-mono">{finding.scanner}</span></span>
            {finding.cvss_score > 0 && <span>CVSS: {finding.cvss_score}</span>}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function SecurityPage({ params }: { params: { id: string } }) {
  const { id: repoId } = params;
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const queryClient = useQueryClient();

  const { data: scans = [], isLoading: scansLoading } = useQuery({
    queryKey: ["scans", repoId],
    queryFn: () => securityApi.listScans(repoId),
    refetchInterval: (q) =>
      (q.state.data as { status: string }[] | undefined)?.some((s) => s.status === "running") ? 5000 : false,
  });

  const latestScan = scans[0];

  const { data: findings = [], isLoading: findingsLoading } = useQuery({
    queryKey: ["findings", latestScan?.id],
    queryFn: () => securityApi.getFindings(repoId, latestScan!.id),
    enabled: !!latestScan?.id && latestScan.status === "complete",
  });

  const { mutate: triggerScan, isPending: scanning } = useMutation({
    mutationFn: () => securityApi.triggerScan(repoId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scans", repoId] }),
  });

  const { mutate: exportSarif, isPending: exporting } = useMutation({
    mutationFn: async () => {
      if (!latestScan) return;
      const blob = await securityApi.exportSarif(repoId, latestScan.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scan-${latestScan.id}.sarif`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  const filtered = severityFilter === "all"
    ? findings
    : findings.filter((f) => f.severity === severityFilter);

  const counts = SEVERITY_ORDER.reduce((acc, s) => {
    acc[s] = findings.filter((f) => f.severity === s).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="h-6 w-6 text-primary" />
            <div>
              <h1 className="text-xl font-bold">Security Findings</h1>
              {latestScan && (
                <p className="text-xs text-muted-foreground">
                  Last scan: {timeAgo(latestScan.created_at)} · {latestScan.finding_count ?? latestScan.total_findings ?? 0} findings
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {latestScan?.status === "complete" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportSarif()}
                disabled={exporting}
              >
                {exporting ? (
                  <Spinner className="mr-2" />
                ) : (
                  <Download className="h-4 w-4 mr-2" />
                )}
                {exporting ? "Exporting…" : "Export SARIF"}
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => triggerScan()}
              disabled={scanning || latestScan?.status === "running"}
            >
              <RefreshCw className={cn("h-4 w-4 mr-2", (scanning || latestScan?.status === "running") && "animate-spin")} />
              {latestScan?.status === "running" ? "Scanning…" : "Scan Now"}
            </Button>
          </div>
        </div>

        {/* Severity summary */}
        {findings.length > 0 && (
          <div className="grid grid-cols-5 gap-2">
            {SEVERITY_ORDER.map((s) => (
              <Card
                key={s}
                className={cn(
                  "cursor-pointer transition-all",
                  severityFilter === s ? "border-primary bg-primary/10" : "hover:bg-muted/50",
                  counts[s] === 0 && "opacity-40"
                )}
                onClick={() => setSeverityFilter(severityFilter === s ? "all" : s)}
              >
                <CardContent className="p-3 text-center">
                  <p className={cn("text-xl font-bold", severityColor(s))}>{counts[s]}</p>
                  <p className="text-xs text-muted-foreground capitalize mt-0.5">{s}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Findings list */}
        {scansLoading ? (
          <SectionLoader label="Loading security scans…" />
        ) : findingsLoading ? (
          <SectionLoader label="Loading findings…" />
        ) : latestScan?.status === "running" ? (
          <div className="text-center py-16 text-muted-foreground">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-3 text-secondary" />
            <p>Security scan in progress…</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Shield className="h-10 w-10 mx-auto mb-3 opacity-30" />
            <p>{findings.length === 0 ? "No scans run yet. Click \"Scan Now\" to start." : "No findings match the current filter."}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered
              .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
              .map((f) => <FindingCard key={f.id} finding={f} />)
            }
          </div>
        )}
      </main>
    </div>
  );
}
