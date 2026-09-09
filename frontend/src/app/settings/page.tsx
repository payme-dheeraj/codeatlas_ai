"use client";

import { useState } from "react";
import { Settings, Save, Sun, Moon } from "lucide-react";
import { Navbar } from "@/components/navbar";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

const LLM_PROVIDERS = ["ollama", "openai", "anthropic"];

export default function SettingsPage() {
  const { theme, setTheme } = useAppStore();
  const [llmProvider, setLlmProvider] = useState("ollama");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [ollamaModel, setOllamaModel] = useState("llama3.2");
  const [openaiKey, setOpenaiKey] = useState("");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    // In production, persist to backend user preferences endpoint
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-2xl px-4 py-8 space-y-6">
        <div className="flex items-center gap-3">
          <Settings className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Settings</h1>
        </div>

        {/* Appearance */}
        <Card>
          <CardHeader><CardTitle className="text-base">Appearance</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {theme === "dark" ? <Moon className="h-4 w-4 text-muted-foreground" /> : <Sun className="h-4 w-4 text-muted-foreground" />}
                <div>
                  <p className="text-sm font-medium">Dark Mode</p>
                  <p className="text-xs text-muted-foreground">Toggle between dark and light theme</p>
                </div>
              </div>
              <Switch
                checked={theme === "dark"}
                onCheckedChange={(checked) => setTheme(checked ? "dark" : "light")}
              />
            </div>
          </CardContent>
        </Card>

        {/* LLM Config */}
        <Card>
          <CardHeader><CardTitle className="text-base">LLM Configuration</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <Label>Provider</Label>
              <Select value={llmProvider} onValueChange={setLlmProvider}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LLM_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {llmProvider === "ollama" && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="ollama-url">Ollama URL</Label>
                  <Input id="ollama-url" type="url" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ollama-model">Model</Label>
                  <Input id="ollama-model" value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} placeholder="llama3.2" />
                </div>
              </>
            )}

            {llmProvider === "openai" && (
              <div className="space-y-1.5">
                <Label htmlFor="openai-key">OpenAI API Key</Label>
                <Input id="openai-key" type="password" value={openaiKey} onChange={(e) => setOpenaiKey(e.target.value)} placeholder="sk-..." />
              </div>
            )}
          </CardContent>
        </Card>

        <Button onClick={handleSave}>
          <Save className="h-4 w-4 mr-2" />
          {saved ? "Saved!" : "Save Settings"}
        </Button>
      </main>
    </div>
  );
}
