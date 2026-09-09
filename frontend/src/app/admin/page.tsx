"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shield, Users, FileText, Clock } from "lucide-react";
import { Navbar } from "@/components/navbar";
import { formatDate } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function fetchAuditLogs() {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const res = await fetch(`${API_BASE}/admin/audit-logs`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Unauthorized");
  return res.json();
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<"audit" | "roles">("audit");

  const { data: logs = [], isLoading, error } = useQuery({
    queryKey: ["audit-logs"],
    queryFn: fetchAuditLogs,
    enabled: activeTab === "audit",
  });

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="flex flex-col items-center justify-center h-64 gap-3 text-destructive">
          <Shield className="h-8 w-8" />
          <p>Access denied — admin role required.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Admin Panel</h1>
        </div>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "audit" | "roles")}>
          <TabsList>
            <TabsTrigger value="audit" className="flex items-center gap-2">
              <FileText className="h-4 w-4" /> Audit Logs
            </TabsTrigger>
            <TabsTrigger value="roles" className="flex items-center gap-2">
              <Users className="h-4 w-4" /> User Roles
            </TabsTrigger>
          </TabsList>

          <TabsContent value="audit">
            <Card className="overflow-hidden">
              <div className="px-5 py-4 border-b border-border flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="font-semibold">Recent Actions</span>
              </div>
              {isLoading ? (
                <div className="divide-y divide-border">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="px-5 py-4 space-y-2">
                      <Skeleton className="h-4 w-64" />
                      <Skeleton className="h-3 w-40" />
                    </div>
                  ))}
                </div>
              ) : logs.length === 0 ? (
                <p className="px-5 py-8 text-center text-muted-foreground">No audit logs yet.</p>
              ) : (
                <div className="divide-y divide-border">
                  {logs.map((log: any) => (
                    <div key={log.id} className="px-5 py-4">
                      <div className="flex items-center gap-3 flex-wrap">
                        <Badge variant="secondary" className="font-mono text-xs">
                          {log.action}
                        </Badge>
                        <span className="text-sm">{log.resource_type}</span>
                        <span className="ml-auto text-xs text-muted-foreground">
                          {formatDate(log.created_at)}
                        </span>
                      </div>
                      {log.response_summary && (
                        <p className="text-xs text-muted-foreground mt-1">{log.response_summary}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="roles">
            <Card>
              <CardContent className="p-8 text-center text-muted-foreground">
                <Users className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p>Role management coming soon.</p>
                <p className="text-xs mt-1">Use the API endpoints directly: PUT /admin/users/:id/role</p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
