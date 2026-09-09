"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { GitBranch, ArrowLeft, Loader2, AlertCircle, Upload } from "lucide-react";
import Link from "next/link";
import { reposApi } from "@/lib/api";
import { Navbar } from "@/components/navbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

type ImportMode = "url" | "zip";

export default function NewRepositoryPage() {
  const router = useRouter();
  const [mode, setMode] = useState<ImportMode>("url");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const { mutate: createFromUrl, isPending: urlPending } = useMutation({
    mutationFn: () => reposApi.create(url.trim(), name.trim() || undefined, token.trim() || undefined),
    onSuccess: (repo) => router.push(`/repositories/${repo.id}`),
    onError: (err: Error) => setError(err.message),
  });

  const { mutate: uploadZip, isPending: zipPending } = useMutation({
    mutationFn: () => reposApi.uploadZip(zipFile!, name.trim() || undefined),
    onSuccess: (repo) => router.push(`/repositories/${repo.id}`),
    onError: (err: Error) => setError(err.message),
  });

  const isPending = urlPending || zipPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (mode === "url") {
      if (!url.trim()) { setError("Repository URL is required."); return; }
      createFromUrl();
    } else {
      if (!zipFile) { setError("Please select a ZIP file."); return; }
      uploadZip();
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-xl px-4 py-12">
        <Link
          href="/repositories"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to repositories
        </Link>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="rounded-md bg-primary/10 p-2.5">
                <GitBranch className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>Import Repository</CardTitle>
                <CardDescription>Connect a Git repository or upload a ZIP archive for AI analysis</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Mode toggle */}
            <div className="flex rounded-lg border border-border mb-6 overflow-hidden">
              <button
                type="button"
                onClick={() => { setMode("url"); setError(""); }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors ${
                  mode === "url" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/50"
                }`}
              >
                <GitBranch className="h-4 w-4" /> Git URL
              </button>
              <button
                type="button"
                onClick={() => { setMode("zip"); setError(""); }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors ${
                  mode === "zip" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/50"
                }`}
              >
                <Upload className="h-4 w-4" /> ZIP Upload
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {mode === "url" ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="url">
                      Repository URL <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="url"
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://github.com/org/repo.git"
                    />
                    <p className="text-xs text-muted-foreground">
                      Supports GitHub, GitLab, Bitbucket, or any HTTPS/SSH Git URL.
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="token">
                      Access Token <span className="text-muted-foreground font-normal">(optional — private repos)</span>
                    </Label>
                    <Input
                      id="token"
                      type="password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    />
                    <p className="text-xs text-muted-foreground">
                      GitHub / GitLab / Bitbucket personal access token.
                    </p>
                  </div>
                </>
              ) : (
                <div className="space-y-1.5">
                  <Label>ZIP Archive <span className="text-destructive">*</span></Label>
                  <div
                    className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                    onClick={() => fileRef.current?.click()}
                  >
                    {zipFile ? (
                      <>
                        <Upload className="h-8 w-8 mx-auto mb-2 text-primary" />
                        <p className="font-medium text-sm">{zipFile.name}</p>
                        <p className="text-xs text-muted-foreground mt-1">{(zipFile.size / 1024 / 1024).toFixed(1)} MB</p>
                      </>
                    ) : (
                      <>
                        <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
                        <p className="text-sm text-muted-foreground">Click to select a .zip file</p>
                        <p className="text-xs text-muted-foreground mt-1">or drag and drop</p>
                      </>
                    )}
                  </div>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
                  />
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="name">
                  Display Name <span className="text-muted-foreground font-normal">(optional)</span>
                </Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="my-awesome-repo"
                />
              </div>

              {error && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Button type="submit" disabled={isPending} className="w-full">
                {isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Importing…</>
                ) : mode === "zip" ? "Upload & Import" : "Import Repository"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
