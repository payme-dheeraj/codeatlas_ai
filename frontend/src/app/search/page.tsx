"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, FileCode, Loader2 } from "lucide-react";
import { searchApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data: results = [], isFetching } = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => searchApi.search(submitted),
    enabled: submitted.length > 2,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(query.trim());
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
        <h1 className="text-2xl font-bold">Code Search</h1>

        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search code, symbols, functions…"
              className="pl-9"
              autoFocus
            />
          </div>
          <Button type="submit" disabled={!query.trim()}>
            <Search className="h-4 w-4 mr-2" /> Search
          </Button>
        </form>

        {isFetching ? (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => (
              <Card key={i}>
                <CardContent className="p-4 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-5/6" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : results.length > 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{results.length} results for &quot;{submitted}&quot;</p>
            {results.map((r) => (
              <Card key={r.id} className="hover:border-primary/50 transition-colors">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileCode className="h-4 w-4 text-primary shrink-0" />
                    <span className="font-mono text-sm text-secondary">{r.file_path}</span>
                    {r.symbol_name && (
                      <Badge variant="outline" className="text-xs">{r.symbol_name}</Badge>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">
                      Score: {r.score.toFixed(3)}
                    </span>
                  </div>
                  <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto font-mono">
                    {r.snippet}
                  </pre>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : submitted && !isFetching ? (
          <Card>
            <CardContent className="py-16 text-center text-muted-foreground">
              <Search className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p>No results found for &quot;{submitted}&quot;</p>
            </CardContent>
          </Card>
        ) : null}
      </main>
    </div>
  );
}
