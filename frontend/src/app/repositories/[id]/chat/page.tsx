"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Send, Loader2, Plus, Bot, User as UserIcon, MessageSquare } from "lucide-react";
import { chatApi } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import { Navbar } from "@/components/navbar";
import { cn, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatMessage } from "@/lib/api";

export default function ChatPage({ params }: { params: { id: string } }) {
  const { id: repoId } = params;
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const {
    sessions, setSessions,
    activeSessionId, setActiveSession,
    messages, setMessages, appendMessage,
    isStreaming, setStreaming,
    streamingContent, appendStreamChunk, clearStreamBuffer,
  } = useChatStore();

  // Load sessions
  const { data: sessionList = [] } = useQuery({
    queryKey: ["chat-sessions", repoId],
    queryFn: () => chatApi.listSessions(repoId),
  });

  useEffect(() => {
    if (sessionList.length > 0) {
      setSessions(sessionList);
      if (!activeSessionId) setActiveSession(sessionList[0].id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionList]);

  // Load messages when session changes
  const { data: msgList = [] } = useQuery({
    queryKey: ["chat-messages", activeSessionId],
    queryFn: () => chatApi.getMessages(activeSessionId!),
    enabled: !!activeSessionId,
  });

  useEffect(() => {
    if (msgList.length > 0) setMessages(msgList as ChatMessage[]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [msgList]);

  // Create new session
  const { mutate: createSession, isPending: creating } = useMutation({
    mutationFn: () => chatApi.createSession(repoId),
    onSuccess: (session) => {
      setSessions([session, ...sessions]);
      setActiveSession(session.id);
      setMessages([]);
    },
  });

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming || !activeSessionId) return;
    const content = input.trim();
    setInput("");

    // Optimistically add user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      session_id: activeSessionId,
      role: "user",
      content,
      citations: [],
      created_at: new Date().toISOString(),
    };
    appendMessage(tempUserMsg);
    setStreaming(true);
    clearStreamBuffer();

    const es = chatApi.streamMessage(activeSessionId, content);
    es.onmessage = (evt) => {
      if (evt.data === "[DONE]") {
        es.close();
        setStreaming(false);
        // Reload messages to get proper IDs + citations
        chatApi.getMessages(activeSessionId).then(setMessages);
        clearStreamBuffer();
      } else {
        appendStreamChunk(evt.data);
      }
    };
    es.onerror = () => {
      es.close();
      setStreaming(false);
    };
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const displayMessages = messages.length > 0 ? messages : (msgList as ChatMessage[]);

  return (
    <div className="flex flex-col h-screen bg-background">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        {/* Sessions sidebar */}
        <aside className="w-56 shrink-0 border-r border-border bg-card flex flex-col">
          <div className="p-3 border-b border-border">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => createSession()}
              disabled={creating}
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
              New Session
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {(sessionList.length > 0 ? sessionList : sessions).map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveSession(s.id)}
                className={cn(
                  "w-full text-left px-3 py-3 text-sm border-b border-border/50 hover:bg-muted/50 transition-colors",
                  activeSessionId === s.id && "bg-muted text-foreground"
                )}
              >
                <p className="truncate font-medium">{s.title ?? "New conversation"}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{timeAgo(s.created_at)}</p>
              </button>
            ))}
          </div>
        </aside>

        {/* Chat area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4">
            {displayMessages.length === 0 && !isStreaming && (
              <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-16">
                <div className="rounded-full bg-primary/10 p-4">
                  <MessageSquare className="h-10 w-10 text-primary/60" />
                </div>
                <div className="space-y-1">
                  <p className="font-medium">Start a conversation</p>
                  <p className="text-sm text-muted-foreground max-w-sm">
                    Ask anything about this repository&apos;s code, architecture, or security.
                  </p>
                </div>
              </div>
            )}
            {displayMessages.map((msg) => (
              <div
                key={msg.id}
                className={cn("flex gap-3", msg.role === "user" && "flex-row-reverse")}
              >
                <div
                  className={cn(
                    "flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center",
                    msg.role === "user" ? "bg-primary/20" : "bg-secondary/20"
                  )}
                >
                  {msg.role === "user" ? (
                    <UserIcon className="h-4 w-4 text-primary" />
                  ) : (
                    <Bot className="h-4 w-4 text-secondary" />
                  )}
                </div>
                <div
                  className={cn(
                    "max-w-[75%] rounded-lg px-4 py-3 text-sm",
                    msg.role === "user"
                      ? "bg-primary/10 text-foreground"
                      : "bg-card border border-border"
                  )}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  {msg.citations?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border/50 space-y-1">
                      {msg.citations.map((c, i) => (
                        <p key={i} className="text-xs text-muted-foreground font-mono">
                          {c.file_path}
                          {c.line_start && `:${c.line_start}`}
                          {c.line_end && `-${c.line_end}`}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Streaming response */}
            {isStreaming && streamingContent && (
              <div className="flex gap-3">
                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-secondary/20 flex items-center justify-center">
                  <Bot className="h-4 w-4 text-secondary" />
                </div>
                <div className="max-w-[75%] rounded-lg px-4 py-3 text-sm bg-card border border-border">
                  <p className="whitespace-pre-wrap">{streamingContent}</p>
                  <span className="inline-block w-1.5 h-4 bg-primary animate-pulse ml-0.5 align-middle" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-4">
            <div className="flex items-end gap-3">
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about this codebase… (Enter to send, Shift+Enter for newline)"
                rows={2}
                className="flex-1 max-h-40 scrollbar-thin"
              />
              <Button
                size="icon"
                onClick={sendMessage}
                disabled={!input.trim() || isStreaming || !activeSessionId}
                className="shrink-0 h-[72px]"
              >
                {isStreaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
